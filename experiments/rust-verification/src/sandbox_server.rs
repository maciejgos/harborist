//! Loopback endpoint for the authenticated Sandbox host protocol.

use crate::{Result, process::Capture, sandbox::TransferDirectory, sandbox_runtime::Runtime};
use base64::{Engine, engine::general_purpose::URL_SAFE};
use serde::{Deserialize, Serialize};
use std::{
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::Read,
    os::{fd::AsRawFd, unix::fs::PermissionsExt},
    path::Path,
    process::{Command, Stdio},
    time::Duration,
};
use tiny_http::{Method, Request, Response, Server};

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

fn authorized(request: &Request, expected: &[u8]) -> bool {
    let mut headers = request
        .headers()
        .iter()
        .filter(|header| header.field.equiv("Authorization"));
    let Some(header) = headers.next() else {
        return false;
    };
    let supplied = header.value.as_bytes();
    headers.next().is_none()
        && supplied.len() == expected.len()
        && supplied
            .iter()
            .zip(expected)
            .fold(0, |difference, (left, right)| difference | (left ^ right))
            == 0
}

fn dispatch(
    request: &mut Request,
    runtime: &Runtime,
    executable: &Path,
    directory: &Path,
) -> Result<Vec<u8>> {
    let length = request
        .body_length()
        .filter(|length| (1..=MAX_BODY).contains(length))
        .ok_or("invalid host helper request length")?;
    if request
        .headers()
        .iter()
        .any(|header| header.field.equiv("Transfer-Encoding"))
    {
        return Err("unsupported host helper request framing".into());
    }
    let mut bytes = Vec::new();
    request
        .as_reader()
        .take(length as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() != length {
        return Err("incomplete host helper request".into());
    }
    let operation: Operation = serde_json::from_slice(&bytes)?;
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
        |args, seconds, limit, input| run(executable, directory, args, seconds, limit, input),
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
    Ok(crate::process::capture_command(
        &mut command,
        Duration::from_secs(timeout),
        limit,
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
    let runtime = Runtime::new(&directory);
    let server = Server::http(("127.0.0.1", port)).map_err(|error| error.to_string())?;
    for mut request in server.incoming_requests() {
        let (status, body) = if request.method() != &Method::Post
            || request.url() != "/v1/sandbox"
            || !authorized(&request, authorization.as_bytes())
        {
            (403, Vec::new())
        } else {
            match dispatch(&mut request, &runtime, executable, &directory) {
                Ok(body) => (200, body),
                Err(_) => (400, Vec::new()),
            }
        };
        let _ = request.respond(Response::from_data(body).with_status_code(status));
    }
    Ok(())
}
