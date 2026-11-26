//! Read-only control projections and a loopback browser adapter.

use crate::{
    Result,
    queue::{self, Delivery, State},
};
use harborist_verify::workflow::{Attempt, Outcome, Receipt, Sha, Stage, Workflow};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    os::{
        fd::AsRawFd,
        unix::{
            fs::{FileTypeExt, OpenOptionsExt, PermissionsExt},
            net::{UnixListener, UnixStream},
        },
    },
    path::{Path, PathBuf},
    time::Duration,
};
use tiny_http::{Header, Method, Request, Response, Server};
use uuid::Uuid;

const JSON: &str = "application/json";
const LIMIT: u64 = 2 * 1024 * 1024;
const MAX_RESPONSE: u64 = 16 * 1024 * 1024;
const ASSETS: [(&str, &str, &[u8]); 4] = [
    (
        "/",
        "text/html; charset=utf-8",
        include_bytes!("../../../src/harborist/web/assets/index.html"),
    ),
    (
        "/app.js",
        "text/javascript; charset=utf-8",
        include_bytes!("../../../src/harborist/web/assets/app.js"),
    ),
    (
        "/style.css",
        "text/css; charset=utf-8",
        include_bytes!("../../../src/harborist/web/assets/style.css"),
    ),
    (
        "/harborist-mark.png",
        "image/png",
        include_bytes!("../../../src/harborist/web/assets/harborist-mark.png"),
    ),
];

#[derive(Deserialize)]
struct Terminal {
    run_id: Uuid,
    base_sha: Sha,
    attempt: Attempt,
    candidate: Option<Sha>,
    outcome: String,
    error: Option<String>,
    receipts: Vec<Receipt>,
}

impl Terminal {
    fn load(delivery: &Delivery) -> Result<Self> {
        let evidence = artifact(delivery, "evidence.json")?;
        let terminal: Self = serde_json::from_str(&evidence)?;
        if terminal.run_id != delivery.run_id
            || terminal.attempt.run_id() != delivery.run_id
            || terminal.attempt.start_sha() != &terminal.base_sha
        {
            return Err("terminal evidence identity mismatch".into());
        }
        let workflow =
            Workflow::replay(terminal.attempt.clone(), terminal.receipts.iter().cloned())?;
        if workflow.next_stage().is_some() {
            return Err("terminal routing evidence is incomplete".into());
        }
        let mut receipts = workflow.receipts().iter().rev();
        if receipts.next().is_none_or(|receipt| {
            receipt.stage != Stage::Package || receipt.outcome != Outcome::Succeeded
        }) {
            return Err("terminal PACKAGE evidence is incomplete".into());
        }
        let previous = receipts.next().ok_or("missing terminal stage receipt")?;
        let expected = match previous.outcome {
            Outcome::Succeeded if previous.stage == Stage::Review => "VERIFIED",
            Outcome::TestFailed => "TEST_FAILED",
            Outcome::ChangesRequired => "CHANGES_REQUIRED",
            Outcome::NeedsClarification => "NEEDS_CLARIFICATION",
            Outcome::NeedsRescoping => "NEEDS_RESCOPING",
            Outcome::Failed => "FAILED",
            _ => return Err("unsupported terminal stage result".into()),
        };
        let candidate = workflow
            .receipts()
            .iter()
            .find(|receipt| receipt.stage == Stage::Build)
            .and_then(|receipt| receipt.candidate.as_ref());
        if terminal.outcome != expected
            || terminal
                .candidate
                .as_ref()
                .map(|sha| terminal.attempt.candidate(sha.clone()))
                .as_ref()
                != candidate
        {
            return Err("terminal outcome or candidate contradicts routing evidence".into());
        }
        Ok(terminal)
    }
}

fn artifact(delivery: &Delivery, name: &str) -> Result<String> {
    if delivery.directory.canonicalize()? != delivery.directory {
        return Err("Run directory does not match the recorded path".into());
    }
    let path = delivery.directory.join(name);
    let parent = path.parent().ok_or("missing artifact directory")?;
    if parent.canonicalize()? != parent {
        return Err("artifact directory does not match its recorded path".into());
    }
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    if !file.metadata()?.is_file() {
        return Err("artifact must be a regular file".into());
    }
    let mut data = Vec::new();
    file.take(LIMIT + 1).read_to_end(&mut data)?;
    if data.len() as u64 > LIMIT {
        return Err("artifact exceeds the 2 MiB viewing limit".into());
    }
    Ok(String::from_utf8(data)?)
}

fn project(delivery: Delivery) -> Value {
    let state = match delivery.state {
        State::Queued => "QUEUED",
        State::Running => "RUNNING",
        State::Finished => "FINISHED",
        State::Failed => "FAILED",
        State::Interrupted => "INTERRUPTED",
    };
    let mut view = json!({
        "version": 1, "source": "service", "state": state,
        "submission": {"run_id": delivery.run_id, "runs_root": delivery.directory.parent()},
        "stages": {}, "stage_errors": {}, "attempt_number": 0, "package_available": false,
        "artifacts": {}, "run": null, "error": delivery.error,
    });
    if delivery.state == State::Finished || delivery.directory.join("evidence.json").is_file() {
        match Terminal::load(&delivery) {
            Ok(terminal) => {
                let lifecycle = if terminal.outcome == "FAILED" {
                    "FAILED"
                } else {
                    "COMPLETED"
                };
                view["run"] = json!({
                    "run_id": terminal.run_id, "lifecycle": lifecycle,
                    "outcome": (lifecycle == "COMPLETED").then_some(&terminal.outcome),
                    "failure_reason": terminal.error,
                });
                if terminal.outcome == "VERIFIED" {
                    view["candidate_sha"] = json!(terminal.candidate);
                }
                for receipt in &terminal.receipts {
                    let stage = json!(receipt.stage);
                    let key = stage.as_str().expect("stage serializes as a string");
                    let (state, reason) = match receipt.outcome {
                        Outcome::Succeeded => ("completed", None),
                        Outcome::Failed => ("failed", None),
                        Outcome::TestFailed => ("failed", Some("TEST_FAILED")),
                        Outcome::ChangesRequired => ("completed", Some("CHANGES_REQUIRED")),
                        Outcome::NeedsClarification => ("completed", Some("NEEDS_CLARIFICATION")),
                        Outcome::NeedsRescoping => ("completed", Some("NEEDS_RESCOPING")),
                        Outcome::Cancelled => ("cancelled", None),
                    };
                    view["stages"][key] = json!({"stage": key, "state": state, "reason": reason});
                }
                view["attempt_id"] = json!(terminal.attempt.id());
                view["package_available"] = json!(true);
                view["artifacts"] = json!({
                    "report.md": delivery.directory.join("report.md"),
                    "evidence.json": delivery.directory.join("evidence.json"),
                });
            }
            Err(error) => view["run_error"] = json!(error.to_string()),
        }
    }
    view
}

enum Route {
    Health,
    Runs,
    Run(Uuid),
    Attempts(Uuid),
    Attempt(Uuid),
    Artifact(Uuid, ArtifactName),
}

enum ArtifactName {
    Report,
    Evidence,
    Specification,
    TestLog { index: u16, stderr: bool },
}

impl ArtifactName {
    fn parse(name: &str, attempt: bool) -> Option<Self> {
        match name {
            "report.md" => Some(Self::Report),
            "evidence.json" => Some(Self::Evidence),
            "spec.md" if attempt => Some(Self::Specification),
            _ if attempt => {
                let (index, stream) = name.strip_prefix("test-")?.split_once('-')?;
                if index.len() != 4 || !index.bytes().all(|byte| byte.is_ascii_digit()) {
                    return None;
                }
                let stderr = match stream {
                    "stdout" => false,
                    "stderr" => true,
                    _ => return None,
                };
                Some(Self::TestLog {
                    index: index.parse().ok()?,
                    stderr,
                })
            }
            _ => None,
        }
    }

    fn read(self, delivery: &Delivery, terminal: &Terminal) -> Result<Value> {
        let (name, path) = match self {
            Self::Report => ("report.md".into(), "report.md".into()),
            Self::Evidence => ("evidence.json".into(), "evidence.json".into()),
            Self::Specification => ("spec.md".into(), "design/spec.md".into()),
            Self::TestLog { index, stderr } => {
                if !terminal.receipts.iter().any(|receipt| {
                    receipt.stage == Stage::Test
                        && matches!(receipt.outcome, Outcome::Succeeded | Outcome::TestFailed)
                }) {
                    return Err("validated TEST capture is unavailable".into());
                }
                let stream = if stderr { "stderr" } else { "stdout" };
                (
                    format!("test-{index:04}-{stream}"),
                    format!("test/{index:04}.{stream}.log"),
                )
            }
        };
        Ok(json!({"name": name, "content": artifact(delivery, &path)?}))
    }
}

impl Route {
    fn parse(path: &str) -> Option<Self> {
        let parts: Vec<_> = path.split('/').collect();
        match parts.as_slice() {
            ["", "health"] => Some(Self::Health),
            ["", "runs"] => Some(Self::Runs),
            ["", "runs", id] => Some(Self::Run(Uuid::parse_str(id).ok()?)),
            ["", "runs", id, "attempts"] => Some(Self::Attempts(Uuid::parse_str(id).ok()?)),
            ["", "runs", id, "attempts", "0"] => Some(Self::Attempt(Uuid::parse_str(id).ok()?)),
            ["", "runs", id, "artifacts", name] => Some(Self::Artifact(
                Uuid::parse_str(id).ok()?,
                ArtifactName::parse(name, false)?,
            )),
            ["", "runs", id, "attempts", "0", "artifacts", name] => Some(Self::Artifact(
                Uuid::parse_str(id).ok()?,
                ArtifactName::parse(name, true)?,
            )),
            _ => None,
        }
    }
}

fn serve_route(queue_root: &Path, route: Route) -> Result<Value> {
    let get = |id: Uuid| queue::read(&queue_root.join(format!("{id}.json")));
    match route {
        Route::Health => Ok(json!({"version": 1, "stopping": false})),
        Route::Runs => Ok(
            json!({"runs": queue::records(queue_root)?.into_iter().map(project).collect::<Vec<_>>()}),
        ),
        Route::Run(id) => Ok(project(get(id)?)),
        Route::Attempts(id) => {
            get(id)?;
            Ok(json!({"attempts": [0]}))
        }
        Route::Attempt(id) => {
            let delivery = get(id)?;
            let specification = artifact(&delivery, "design/spec.md").is_ok();
            let mut view = project(delivery);
            view["has_specification"] = json!(specification);
            Ok(view)
        }
        Route::Artifact(id, name) => {
            let delivery = get(id)?;
            let terminal = Terminal::load(&delivery)?;
            name.read(&delivery, &terminal)
        }
    }
}

fn respond(request: Request, status: u16, mime: &str, body: Vec<u8>) {
    let header = |key: &str, value: &str| {
        Header::from_bytes(key.as_bytes(), value.as_bytes()).expect("static header")
    };
    let response = Response::from_data(body)
        .with_status_code(status)
        .with_header(header("Content-Type", mime))
        .with_header(header("Cache-Control", "no-store"))
        .with_header(header("X-Content-Type-Options", "nosniff"));
    let _ = request.respond(response);
}

fn respond_json(request: Request, status: u16, value: Value) {
    respond(request, status, JSON, value.to_string().into_bytes());
}

fn error_response(request: Request, status: u16, error: impl ToString) {
    respond_json(request, status, json!({"error": error.to_string()}));
}

fn socket_path(control: &Path) -> PathBuf {
    control.join("service.sock")
}

pub fn service(args: &[OsString]) -> Result<()> {
    let [control] = args else {
        return Err("expected service CONTROL_DIR".into());
    };
    let control = Path::new(control);
    let queue_root = queue::queue_directory(control)?;
    let guard = File::options()
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o600)
        .open(control.join("reader.lock"))?;
    // Exclusive ownership protects the socket path during stale-socket cleanup.
    if unsafe { libc::flock(guard.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let path = socket_path(control);
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.file_type().is_socket() => {
            if UnixStream::connect(&path).is_ok() {
                return Err("a control service is already listening".into());
            }
            fs::remove_file(&path)?;
        }
        Ok(_) => return Err("service socket path belongs to a different file".into()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.into()),
    }
    let listener = UnixListener::bind(&path)?;
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    let server = Server::from_listener(listener, None).map_err(|error| error.to_string())?;
    for request in server.incoming_requests() {
        let route = Route::parse(request.url());
        match (request.method(), route) {
            (&Method::Get, Some(route)) => match serve_route(&queue_root, route) {
                Ok(value) => respond_json(request, 200, value),
                Err(error) => error_response(request, 404, error),
            },
            (&Method::Get, None) => error_response(request, 404, "Unknown control route"),
            _ => error_response(request, 405, "Read-only control service"),
        }
    }
    Ok(())
}

fn proxy(control: &Path, route: &str) -> Result<(u16, Vec<u8>)> {
    let mut stream = UnixStream::connect(socket_path(control))?;
    let timeout = Some(Duration::from_secs(5));
    stream.set_read_timeout(timeout)?;
    stream.set_write_timeout(timeout)?;
    write!(
        stream,
        "GET {route} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n"
    )?;
    let mut raw = Vec::new();
    stream.take(MAX_RESPONSE + 1).read_to_end(&mut raw)?;
    if raw.len() as u64 > MAX_RESPONSE {
        return Err("control response exceeds the viewing limit".into());
    }
    let end = raw
        .windows(4)
        .position(|bytes| bytes == b"\r\n\r\n")
        .ok_or("invalid control response headers")?;
    let headers = std::str::from_utf8(&raw[..end])?;
    let status = headers
        .lines()
        .next()
        .and_then(|line| line.split_ascii_whitespace().nth(1))
        .ok_or("invalid control response status")?
        .parse()?;
    let body = raw.split_off(end + 4);
    serde_json::from_slice::<Value>(&body)?;
    Ok((status, body))
}

pub fn web(args: &[OsString]) -> Result<()> {
    let [control, port] = args else {
        return Err("expected web CONTROL_DIR PORT".into());
    };
    let control = Path::new(control);
    let port: u16 = port.to_str().ok_or("expected a port")?.parse()?;
    if port == 0 {
        return Err("expected a nonzero loopback port".into());
    }
    let allowed = [format!("127.0.0.1:{port}"), format!("localhost:{port}")];
    let server = Server::http(("127.0.0.1", port)).map_err(|error| error.to_string())?;
    for request in server.incoming_requests() {
        let hosts: Vec<_> = request
            .headers()
            .iter()
            .filter(|header| header.field.equiv("Host"))
            .collect();
        if !matches!(hosts.as_slice(), [host] if allowed.iter().any(|value| value == host.value.as_str()))
        {
            error_response(request, 403, "Loopback host required");
            continue;
        }
        if request.method() != &Method::Get {
            error_response(request, 405, "Read-only browser monitor");
            continue;
        }
        let path = request.url().split('?').next().unwrap_or_default();
        if let Some(route) = path.strip_prefix("/api") {
            if Route::parse(route).is_none() {
                error_response(request, 404, "Unknown API route");
            } else {
                match proxy(control, route) {
                    Ok((status, body)) => respond(request, status, JSON, body),
                    Err(error) => error_response(request, 503, error),
                }
            }
            continue;
        }
        let page = if matches!(path, "/runs" | "/evidence")
            || matches!(Route::parse(path), Some(Route::Run(_)))
        {
            "/"
        } else {
            path
        };
        if let Some((_, mime, body)) = ASSETS.iter().find(|(name, _, _)| name == &page) {
            respond(request, 200, mime, body.to_vec());
        } else {
            error_response(request, 404, "Unknown page");
        }
    }
    Ok(())
}
