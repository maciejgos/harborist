//! Loopback endpoint for the authenticated Sandbox host protocol.

use crate::{Result, process::Capture, sandbox::TransferDirectory, sandbox_runtime::Runtime};
use base64::{Engine, engine::general_purpose::URL_SAFE};
use serde::{Deserialize, Serialize};
use std::{
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::{self, BufRead, BufReader, Read, Write},
    net::{TcpListener, TcpStream},
    os::{fd::AsRawFd, unix::fs::PermissionsExt},
    path::Path,
    process::{Command, Stdio},
    sync::Arc,
    time::Duration,
};

const MAX_INPUT: usize = 64 * 1024 * 1024;
const MAX_BODY: usize = 4 * MAX_INPUT.div_ceil(3) + 128 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Operation {
    args: Vec<String>,
    timeout: f64,
    limit: usize,
    #[serde(default)]
    input_bytes: String,
}

#[derive(Serialize)]
struct Output {
    returncode: i32,
    timed_out: bool,
    stdout: String,
    stderr: String,
    stdout_truncated: bool,
    stderr_truncated: bool,
}

fn authorized(supplied: &[u8], expected: &[u8]) -> bool {
    supplied.len() == expected.len()
        && supplied
            .iter()
            .zip(expected)
            .fold(0, |difference, (left, right)| difference | (left ^ right))
            == 0
}

fn disconnected(reader: &BufReader<TcpStream>) -> bool {
    let mut descriptor = libc::pollfd {
        fd: reader.get_ref().as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // Once the whole request arrives, any new data or EOF ends the request.
    !reader.buffer().is_empty() || unsafe { libc::poll(&mut descriptor, 1, 0) } != 0
}

fn request_body(reader: &mut BufReader<TcpStream>, expected: &[u8]) -> Result<Option<Vec<u8>>> {
    let mut headers = (&mut *reader).take(8192);
    let mut line = String::new();
    headers.read_line(&mut line)?;
    if !matches!(
        line.as_str(),
        "POST /v1/sandbox HTTP/1.0\r\n" | "POST /v1/sandbox HTTP/1.1\r\n"
    ) {
        return Ok(None);
    }
    let mut length = None;
    let mut authorization = None;
    loop {
        line.clear();
        if headers.read_line(&mut line)? == 0 {
            return Err("incomplete host helper request headers".into());
        }
        if line == "\r\n" {
            break;
        }
        let (name, value) = line.split_once(':').ok_or("invalid host helper header")?;
        if name.eq_ignore_ascii_case("Content-Length") {
            if length.replace(value.trim().parse::<usize>()?).is_some() {
                return Err("duplicate host helper request length".into());
            }
        } else if name.eq_ignore_ascii_case("Authorization") {
            if authorization
                .replace(authorized(value.trim().as_bytes(), expected))
                .is_some()
            {
                return Ok(None);
            }
        } else if name.eq_ignore_ascii_case("Transfer-Encoding") {
            return Err("unsupported host helper request framing".into());
        }
    }
    if authorization != Some(true) {
        return Ok(None);
    }
    let length = length
        .filter(|length| (1..=MAX_BODY).contains(length))
        .ok_or("invalid host helper request length")?;
    let mut body = vec![0; length];
    drop(headers);
    reader.read_exact(&mut body)?;
    Ok(Some(body))
}

fn dispatch(
    bytes: &[u8],
    runtime: &Runtime,
    executable: &Path,
    directory: &Path,
    disconnected: impl Fn() -> bool,
) -> Result<Vec<u8>> {
    let operation: Operation = serde_json::from_slice(bytes)?;
    if !(operation.timeout > 0.0 && operation.timeout <= 3600.0) {
        return Err("invalid host helper timeout".into());
    }
    let input = URL_SAFE.decode(operation.input_bytes)?;
    let args: Vec<_> = operation.args.iter().map(String::as_str).collect();
    let result = runtime.execute(
        &args,
        operation.timeout.ceil() as u64,
        operation.limit,
        &input,
        |args, seconds, limit, input, cancellable| {
            run(executable, directory, args, seconds, limit, input, || {
                if cancellable && disconnected() {
                    Err(io::Error::new(
                        io::ErrorKind::Interrupted,
                        "sandbox worker disconnected",
                    ))
                } else {
                    Ok(())
                }
            })
        },
        &disconnected,
    )?;
    Ok(serde_json::to_vec(&Output {
        returncode: result.returncode,
        timed_out: result.timed_out,
        stdout: URL_SAFE.encode(result.stdout.bytes),
        stderr: URL_SAFE.encode(result.stderr.bytes),
        stdout_truncated: result.stdout.truncated,
        stderr_truncated: result.stderr.truncated,
    })?)
}

fn run(
    executable: &Path,
    directory: &Path,
    args: &[&str],
    timeout: u64,
    limit: usize,
    input: &[u8],
    check: impl Fn() -> io::Result<()>,
) -> Result<Capture> {
    let mut command = Command::new(executable);
    command
        .arg("--no-input")
        .args(args)
        .current_dir(directory)
        .stdin(Stdio::null());
    for name in [
        "SSH_AUTH_SOCK",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ] {
        command.env_remove(name);
    }
    let transfer = if input.is_empty() {
        None
    } else {
        Some(TransferDirectory::create()?)
    };
    if let Some(transfer) = &transfer {
        let path = transfer.0.join("stdin");
        crate::store::write_new(&path, input)?;
        command.stdin(File::open(path)?);
    }
    Ok(crate::process::capture_until(
        &mut command,
        Duration::from_secs(timeout),
        limit,
        check,
    )?)
}

pub fn serve(args: &[OsString]) -> Result<()> {
    let (directory, port, executable) = match args {
        [directory, port] => (directory, port, Path::new("sbx")),
        [directory, port, flag, executable] if flag == "--sbx" => {
            (directory, port, Path::new(executable))
        }
        _ => return Err("expected sandbox-host DIRECTORY PORT [--sbx EXECUTABLE]".into()),
    };
    let port: u16 = port.to_str().ok_or("invalid sandbox host port")?.parse()?;
    fs::create_dir_all(directory)?;
    let directory = Path::new(directory).canonicalize()?;
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700))?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(directory.join("helper.lock"))?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut token = String::new();
    File::open(directory.join("token"))?
        .take(4097)
        .read_to_string(&mut token)?;
    let token = token.trim();
    if !(32..=4096).contains(&token.len()) || !token.bytes().all(|byte| byte.is_ascii_graphic()) {
        return Err("invalid sandbox host token".into());
    }
    let authorization = format!("Bearer {token}");
    let runtime = Arc::new(Runtime::new(&directory));
    let authorization = Arc::new(authorization);
    let server = TcpListener::bind(("127.0.0.1", port))?;
    for socket in server.incoming() {
        let socket = socket?;
        let (runtime, authorization, directory, executable) = (
            Arc::clone(&runtime),
            Arc::clone(&authorization),
            directory.clone(),
            executable.to_owned(),
        );
        std::thread::Builder::new().spawn(move || {
            let _ = handle(
                socket,
                &runtime,
                authorization.as_bytes(),
                &executable,
                &directory,
            );
        })?;
    }
    Ok(())
}

fn handle(
    stream: TcpStream,
    runtime: &Runtime,
    authorization: &[u8],
    executable: &Path,
    directory: &Path,
) -> Result<()> {
    stream.set_read_timeout(Some(Duration::from_secs(10)))?;
    stream.set_write_timeout(Some(Duration::from_secs(10)))?;
    let mut reader = BufReader::new(stream);
    let result = request_body(&mut reader, authorization).and_then(|body| {
        body.map(|body| {
            dispatch(&body, runtime, executable, directory, || {
                disconnected(&reader)
            })
        })
        .transpose()
    });
    let (status, body) = match result {
        Ok(Some(body)) => ("200 OK", body),
        Ok(None) => ("403 Forbidden", Vec::new()),
        Err(_) => ("400 Bad Request", Vec::new()),
    };
    let mut stream = reader.into_inner();
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    stream.write_all(&body)?;
    Ok(())
}
