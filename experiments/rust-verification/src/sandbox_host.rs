//! Client for the local Docker Sandboxes host helper.

use crate::{
    Result,
    process::{Capture, Stream},
};
use base64::{Engine, engine::general_purpose::URL_SAFE};
use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    time::Duration,
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

pub fn invoke(
    host: &str,
    args: &[&str],
    timeout: u64,
    limit: usize,
    input: &[u8],
) -> Result<Capture> {
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
    let mut socket = TcpStream::connect_timeout(&address, Duration::from_secs(5))?;
    socket.set_read_timeout(Some(Duration::from_secs(timeout + 10)))?;
    socket.set_write_timeout(Some(Duration::from_secs(10)))?;
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
