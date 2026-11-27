//! Client for the local Docker Sandboxes host helper.

use crate::{
    Result,
    process::{Capture, Stream},
};
use base64::{Engine, engine::general_purpose::URL_SAFE};
use serde::{Deserialize, Serialize};
use std::{
    io::{self, BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    path::Path,
    time::{Duration, Instant},
};

#[derive(Serialize)]
struct Request<'a> {
    args: &'a [&'a str],
    timeout: u64,
    limit: usize,
    input_bytes: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Response {
    returncode: i32,
    timed_out: bool,
    stdout: String,
    stderr: String,
    stdout_truncated: bool,
    stderr_truncated: bool,
}

struct Connection<'a> {
    socket: TcpStream,
    cancellation: Option<&'a Path>,
    deadline: Instant,
}

impl Connection<'_> {
    fn transfer(
        &mut self,
        mut operation: impl FnMut(&mut TcpStream) -> io::Result<usize>,
    ) -> io::Result<usize> {
        loop {
            if let Some(marker) = self.cancellation {
                crate::retirement::cancelled(marker).map_err(|error| {
                    if error.kind() == io::ErrorKind::Interrupted {
                        // Standard buffered I/O retries Interrupted internally.
                        io::Error::new(io::ErrorKind::ConnectionAborted, error)
                    } else {
                        error
                    }
                })?;
            }
            if Instant::now() >= self.deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Docker sandbox host helper deadline expired",
                ));
            }
            match operation(&mut self.socket) {
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut
                    ) =>
                {
                    ()
                }
                result => return result,
            }
        }
    }
}

impl Read for Connection<'_> {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.transfer(|socket| socket.read(output))
    }
}

impl Write for Connection<'_> {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        self.transfer(|socket| socket.write(data))
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

pub fn invoke(
    host: &str,
    args: &[&str],
    timeout: u64,
    limit: usize,
    input: &[u8],
) -> Result<Capture> {
    invoke_cancellable(host, args, timeout, limit, input, None)
}

pub fn invoke_cancellable(
    host: &str,
    args: &[&str],
    timeout: u64,
    limit: usize,
    input: &[u8],
    cancellation: Option<&Path>,
) -> Result<Capture> {
    let result = invoke_inner(host, args, timeout, limit, input, cancellation);
    if let Some(marker) = cancellation {
        crate::retirement::cancelled(marker)?;
    }
    result
}

fn invoke_inner(
    host: &str,
    args: &[&str],
    timeout: u64,
    limit: usize,
    input: &[u8],
    cancellation: Option<&Path>,
) -> Result<Capture> {
    if let Some(marker) = cancellation {
        crate::retirement::cancelled(marker)?;
    }
    if !(1..=3600).contains(&timeout)
        || !(1..=16 * 1024 * 1024).contains(&limit)
        || input.len() > 64 * 1024 * 1024
        || args.is_empty()
        || args.len() > 1024
    {
        return Err("invalid Docker sandbox host helper request limits".into());
    }
    if host.starts_with('-')
        || !host
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b':'))
    {
        return Err("invalid Docker sandbox host helper hostname".into());
    }
    let port: u16 = std::env::var("HARBORIST_SANDBOX_PORT")?.parse()?;
    let token_path = std::env::var_os("HARBORIST_SANDBOX_TOKEN_FILE")
        .ok_or("missing Docker sandbox host helper token file")?;
    let mut token = String::new();
    std::fs::File::open(token_path)?
        .take(4097)
        .read_to_string(&mut token)?;
    let token = token.trim();
    if token.is_empty() || token.len() > 4096 || !token.bytes().all(|byte| byte.is_ascii_graphic())
    {
        return Err("invalid Docker sandbox host helper token".into());
    }
    let payload = serde_json::to_vec(&Request {
        args,
        timeout,
        limit,
        input_bytes: URL_SAFE.encode(input),
    })?;
    let address = (host, port)
        .to_socket_addrs()?
        .next()
        .ok_or("Docker sandbox host helper has no address")?;
    let socket = TcpStream::connect_timeout(&address, Duration::from_secs(5))?;
    let mut socket = Connection {
        socket,
        cancellation,
        deadline: Instant::now() + Duration::from_secs(timeout + 10),
    };
    let interval = Some(Duration::from_millis(100));
    socket.socket.set_read_timeout(interval)?;
    socket.socket.set_write_timeout(interval)?;
    write!(
        socket,
        "POST /v1/sandbox HTTP/1.1\r\nHost: {host}:{port}\r\nAuthorization: Bearer {token}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        payload.len()
    )?;
    socket.write_all(&payload)?;
    let mut reader = BufReader::new(socket);
    let mut headers = (&mut reader).take(8192);
    let mut line = String::new();
    headers.read_line(&mut line)?;
    if line.split_ascii_whitespace().nth(1) != Some("200") {
        return Err("Docker sandbox host helper rejected the operation".into());
    }
    let mut length = None;
    loop {
        line.clear();
        if headers.read_line(&mut line)? == 0 {
            return Err("incomplete Docker sandbox host helper response headers".into());
        }
        if line == "\r\n" {
            break;
        }
        let (name, value) = line
            .split_once(':')
            .ok_or("invalid sandbox response header")?;
        if name.eq_ignore_ascii_case("Content-Length") {
            if length.replace(value.trim().parse::<usize>()?).is_some() {
                return Err("duplicate Docker sandbox host helper response length".into());
            }
        } else if name.eq_ignore_ascii_case("Transfer-Encoding") {
            return Err("unsupported Docker sandbox host helper response framing".into());
        }
    }
    let length = length
        .filter(|length| *length <= 8 * limit.div_ceil(3) + 1024)
        .ok_or("Docker sandbox host helper response exceeds its limit or has no length")?;
    let mut raw = vec![0; length];
    reader.read_exact(&mut raw)?;
    let response: Response = serde_json::from_slice(&raw)?;
    let stdout = URL_SAFE.decode(response.stdout)?;
    let stderr = URL_SAFE.decode(response.stderr)?;
    if stdout.len().max(stderr.len()) > limit {
        return Err("Docker sandbox host helper output exceeds its limit".into());
    }
    Ok(Capture {
        returncode: response.returncode,
        timed_out: response.timed_out,
        stdout: Stream {
            bytes: stdout,
            truncated: response.stdout_truncated,
        },
        stderr: Stream {
            bytes: stderr,
            truncated: response.stderr_truncated,
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn cancellation_interrupts_pending_response_and_closes_connection() {
        let transfer = crate::sandbox::TransferDirectory::create().unwrap();
        let marker = transfer.0.join("retirement.json");
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let socket = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
        socket
            .set_read_timeout(Some(Duration::from_millis(25)))
            .unwrap();
        let (mut peer, _) = listener.accept().unwrap();
        peer.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
        std::thread::scope(|scope| {
            let cancelled = &marker;
            scope.spawn(move || {
                std::thread::sleep(Duration::from_millis(50));
                std::fs::write(cancelled, b"{}").unwrap();
                assert_eq!(peer.read(&mut [0]).unwrap(), 0);
            });
            let mut connection = Connection {
                socket,
                cancellation: Some(&marker),
                deadline: Instant::now() + Duration::from_secs(2),
            };
            assert_eq!(
                connection.read_exact(&mut [0]).unwrap_err().kind(),
                io::ErrorKind::ConnectionAborted
            );
        });
    }
}
