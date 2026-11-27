//! Read-only control projections and a loopback browser adapter.

use crate::{
    Result,
    queue::{self, Delivery, State},
    record::{Terminal, read_artifact},
    workspace,
};
use harborist_verify::workflow::{Outcome, Stage};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs::{self, File},
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
const MAX_REQUEST: usize = 64 * 1024;
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

fn project_latest(delivery: Delivery) -> Result<Value> {
    let number = crate::continuation::latest(&delivery.directory)?;
    Ok(project(delivery, number))
}

fn project(delivery: Delivery, number: u32) -> Value {
    let attempt = crate::continuation::attempt_path(&delivery.directory, number);
    let state = match delivery.state {
        State::Queued => "QUEUED",
        State::Running => "RUNNING",
        State::Finished => "FINISHED",
        State::Failed => "FAILED",
        State::Interrupted => "INTERRUPTED",
        State::Cancelled => "CANCELLED",
    };
    let mut view = json!({
        "version": 1, "source": "service", "state": state,
        "submission": {"run_id": delivery.run_id, "runs_root": delivery.directory.parent()},
        "stages": {}, "stage_errors": {}, "attempt_number": number, "package_available": false,
        "artifacts": {}, "run": null, "error": delivery.error,
    });
    if let Ok(raw) = read_artifact(&delivery.directory, "contract.json") {
        if let Ok(contract) = serde_json::from_str::<crate::store::Contract>(&raw) {
            if contract.run_id == delivery.run_id {
                view["repository"] = json!(contract.repository);
                view["source_ref"] = json!(contract.source_ref);
                view["source_url"] = json!(contract.source_url);
                if let Ok(intent) = read_artifact(&delivery.directory, "intent.md") {
                    if crate::store::digest(intent.as_bytes()) == contract.intent_sha256 {
                        view["title"] = json!(
                            intent
                                .lines()
                                .find(|line| !line.trim().is_empty())
                                .unwrap_or("Untitled request")
                                .trim()
                                .trim_start_matches(['#', ' '])
                                .chars()
                                .take(200)
                                .collect::<String>()
                        );
                    }
                }
            }
        }
    }
    if let Ok(record) = read_artifact(&delivery.directory, "retirement.json")
        .and_then(|data| Ok(serde_json::from_str::<Value>(&data)?))
    {
        if record["run_id"] == json!(delivery.run_id) {
            view["retirement"] = record;
            if matches!(delivery.state, State::Queued | State::Cancelled) {
                view["state"] = json!("CANCELLED");
                view["run"] =
                    json!({"run_id": delivery.run_id, "lifecycle": "CANCELLED", "outcome": null});
            }
        }
    }
    if let Ok(Some(lost)) = crate::continuation::interruption(&attempt) {
        if lost.attempt.run_id() == delivery.run_id {
            view["attempt_id"] = json!(lost.attempt.id());
            view["run"] = json!({
                "run_id": delivery.run_id, "lifecycle": "FAILED", "outcome": null,
                "failure_reason": "EXECUTION_FAILED",
            });
        }
    }
    if attempt.join("evidence.json").is_file() || (number == 0 && delivery.state == State::Finished)
    {
        match Terminal::load(&attempt, delivery.run_id) {
            Ok(terminal) => {
                let lifecycle = match terminal.outcome.as_str() {
                    "FAILED" => "FAILED",
                    "CANCELLED" => "CANCELLED",
                    _ => "COMPLETED",
                };
                view["run"] = json!({
                    "run_id": terminal.run_id, "lifecycle": lifecycle,
                    "outcome": (lifecycle == "COMPLETED").then_some(&terminal.outcome),
                    "failure_reason": terminal.failure_reason.as_ref().or(terminal.error.as_ref()),
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
                    "report.md": attempt.join("report.md"),
                    "evidence.json": attempt.join("evidence.json"),
                });
            }
            Err(error) => view["run_error"] = json!(error.to_string()),
        }
    }
    view
}

enum Route {
    Health,
    Workspaces,
    Runs,
    Run(Uuid),
    GitHub(Uuid),
    Attempts(Uuid),
    Attempt(Uuid, u32),
    Artifact(Uuid, Option<u32>, ArtifactName),
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

    fn read(self, directory: &Path, terminal: &Terminal) -> Result<Value> {
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
        Ok(json!({"name": name, "content": read_artifact(directory, &path)?}))
    }
}

impl Route {
    fn parse(path: &str) -> Option<Self> {
        let parts: Vec<_> = path.split('/').collect();
        match parts.as_slice() {
            ["", "health"] => Some(Self::Health),
            ["", "workspaces"] => Some(Self::Workspaces),
            ["", "runs"] => Some(Self::Runs),
            ["", "runs", id] => Some(Self::Run(Uuid::parse_str(id).ok()?)),
            ["", "runs", id, "github"] => Some(Self::GitHub(Uuid::parse_str(id).ok()?)),
            ["", "runs", id, "attempts"] => Some(Self::Attempts(Uuid::parse_str(id).ok()?)),
            ["", "runs", id, "attempts", number] => Some(Self::Attempt(
                Uuid::parse_str(id).ok()?,
                number.parse().ok()?,
            )),
            ["", "runs", id, "artifacts", name] => Some(Self::Artifact(
                Uuid::parse_str(id).ok()?,
                None,
                ArtifactName::parse(name, false)?,
            )),
            ["", "runs", id, "attempts", number, "artifacts", name] => Some(Self::Artifact(
                Uuid::parse_str(id).ok()?,
                Some(number.parse().ok()?),
                ArtifactName::parse(name, true)?,
            )),
            _ => None,
        }
    }
}

fn serve_route(queue_root: &Path, legacy_root: Option<&Path>, route: Route) -> Result<Value> {
    if let Some(root) = legacy_root {
        let id = match &route {
            Route::Run(id)
            | Route::GitHub(id)
            | Route::Attempts(id)
            | Route::Attempt(id, _)
            | Route::Artifact(id, _, _) => Some(*id),
            _ => None,
        };
        if let Some(id) = id {
            if !queue_root.join(format!("{id}.json")).try_exists()? {
                return serve_history(root, id, route);
            }
        }
    }
    let get = |id: Uuid| queue::read(&queue_root.join(format!("{id}.json")));
    match route {
        Route::Health => Ok(json!({"version": 1, "stopping": false})),
        Route::Workspaces => {
            workspace::list(queue_root.parent().ok_or("missing control directory")?)
        }
        Route::Runs => {
            let deliveries = queue::records(queue_root)?;
            let mut views = Vec::new();
            if let Some(root) = legacy_root {
                for id in crate::legacy::ids(root)? {
                    if !deliveries.iter().any(|delivery| delivery.run_id == id) {
                        views.push(serve_history(root, id, Route::Run(id))?);
                    }
                }
            }
            views.extend(
                deliveries
                    .into_iter()
                    .map(project_latest)
                    .collect::<Result<Vec<_>>>()?,
            );
            Ok(json!({"runs": views}))
        }
        Route::Run(id) => project_latest(get(id)?),
        Route::GitHub(id) => crate::publication::delivery(&get(id)?.directory, id),
        Route::Attempts(id) => {
            Ok(json!({"attempts": crate::continuation::numbers(&get(id)?.directory)?}))
        }
        Route::Attempt(id, number) => {
            let delivery = get(id)?;
            let directory = select_attempt(&delivery.directory, Some(number))?;
            let specification = read_artifact(&directory, "design/spec.md").is_ok();
            let mut view = project(delivery, number);
            view["has_specification"] = json!(specification);
            Ok(view)
        }
        Route::Artifact(id, number, name) => {
            let delivery = get(id)?;
            let directory = select_attempt(&delivery.directory, number)?;
            let terminal = Terminal::load(&directory, delivery.run_id)?;
            name.read(&directory, &terminal)
        }
    }
}

fn serve_history(root: &Path, id: Uuid, route: Route) -> Result<Value> {
    let native = root.join(id.to_string());
    if !native.join("run.json").try_exists()? && native.join("contract.json").try_exists()? {
        let capture = crate::store::load_frozen(&native)?;
        if capture.contract.run_id != id {
            return Err("saved Run ID does not match its directory".into());
        }
        return match route {
            Route::Runs | Route::Health | Route::Workspaces => {
                Err("saved Rust Run route is unavailable".into())
            }
            Route::GitHub(_) => crate::publication::delivery(&capture.directory, id),
            Route::Attempts(_) => {
                Ok(json!({"attempts": crate::continuation::numbers(&capture.directory)?}))
            }
            Route::Run(_) => saved_attempt_view(id, &capture.directory, None),
            Route::Attempt(_, number) => saved_attempt_view(id, &capture.directory, Some(number)),
            Route::Artifact(_, number, name) => {
                let directory = select_attempt(&capture.directory, number)?;
                let terminal = Terminal::load(&directory, id)?;
                name.read(&directory, &terminal)
            }
        };
    }
    let directory = crate::legacy::locate(root, id)?;
    match route {
        Route::Run(_) => crate::legacy::view(&directory, id, None),
        Route::Attempts(_) => Ok(json!({"attempts": crate::legacy::numbers(&directory)?})),
        Route::Attempt(_, number) => crate::legacy::view(&directory, id, Some(number)),
        Route::Artifact(_, number, name) => {
            let name = match name {
                ArtifactName::Report => "report.md",
                ArtifactName::Evidence => "evidence.json",
                ArtifactName::Specification => "spec.md",
                ArtifactName::TestLog { .. } => {
                    return Err("unsupported historical test log".into());
                }
            };
            crate::legacy::artifact(&directory, id, number, name)
        }
        _ => Err("historical Run route is unavailable".into()),
    }
}

fn saved_attempt_view(id: Uuid, root: &Path, number: Option<u32>) -> Result<Value> {
    let directory = select_attempt(root, number)?;
    let number = number.map_or_else(|| crate::continuation::latest(root), Ok)?;
    let mut view = project(queue::saved(id, root.to_owned()), number);
    view["source"] = json!("saved");
    view["state"] = Value::Null;
    view["has_specification"] = json!(read_artifact(&directory, "design/spec.md").is_ok());
    if view["run"].is_null() && view["run_error"].is_null() {
        let lifecycle = if directory.join("attempt.json").is_file() {
            "RUNNING"
        } else {
            "CREATED"
        };
        view["run"] = json!({"run_id": id, "lifecycle": lifecycle, "outcome": null});
    }
    Ok(view)
}

fn select_attempt(root: &Path, number: Option<u32>) -> Result<PathBuf> {
    let numbers = crate::continuation::numbers(root)?;
    let selected = number.unwrap_or_else(|| numbers.last().copied().unwrap_or(0));
    if !numbers.contains(&selected) {
        return Err("Attempt does not exist".into());
    }
    Ok(crate::continuation::attempt_path(root, selected))
}

fn header<'a>(request: &'a Request, name: &str) -> Option<&'a str> {
    let mut values = request
        .headers()
        .iter()
        .filter(|header| header.field.as_str().as_str().eq_ignore_ascii_case(name));
    let first = values.next()?;
    if values.next().is_some() {
        return None;
    }
    Some(first.value.as_str())
}

fn request_body(request: &mut Request) -> Result<Vec<u8>> {
    let length = header(request, "Content-Length")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|&length| length > 0 && length <= MAX_REQUEST)
        .ok_or("expected a bounded JSON body")?;
    if request
        .headers()
        .iter()
        .any(|header| header.field.equiv("Transfer-Encoding"))
        || header(request, "Content-Type").and_then(|value| value.split(';').next()) != Some(JSON)
    {
        return Err("expected a bounded JSON body".into());
    }
    let mut body = vec![0; length];
    request.as_reader().read_exact(&mut body)?;
    Ok(body)
}

fn run_command_route(route: &str) -> Option<(Uuid, &str)> {
    let (id, action) = route.strip_prefix("/workspace/runs/")?.split_once('/')?;
    matches!(
        action,
        "publish" | "observe" | "cancel" | "supersede" | "continue"
    )
    .then_some((Uuid::parse_str(id).ok()?, action))
}

fn is_write(route: &str) -> bool {
    matches!(
        route,
        "/workspaces" | "/workspace/runs" | "/tickets/list" | "/tickets/queue"
    ) || run_command_route(route).is_some()
        || crate::integrations::is_write(route)
}

fn command(control: &Path, route: &str, request: &mut Request) -> Result<Value> {
    let body = request_body(request)?;
    if crate::integrations::is_write(route) {
        return crate::integrations::write(control, route, &body);
    }
    if let Some((id, action)) = run_command_route(route) {
        if action == "continue" {
            return queue::continue_run(control, id, &body);
        }
        if action == "cancel" {
            return cancel_run(control, id, &body);
        }
        let delivery = queue::read(&control.join("queue").join(format!("{id}.json")))?;
        if action == "supersede" {
            return workspace::supersede(control, &delivery, &body);
        }
        if matches!(delivery.state, State::Queued | State::Running) {
            return Err("publication requires a terminal Run".into());
        }
        if action == "observe" {
            let payload: Value = serde_json::from_slice(&body)?;
            if !payload.as_object().is_some_and(serde_json::Map::is_empty) {
                return Err("GitHub observation expects an empty request".into());
            }
            return crate::publication::observe(&delivery.directory, id);
        }
        return crate::publication::browser(&delivery.directory, id, &body);
    }
    match route {
        "/workspaces" => workspace::save(control, &body),
        "/workspace/runs" => workspace::capture(control, &body),
        "/tickets/list" => crate::github::list(control, &body),
        "/tickets/queue" => workspace::queue_ticket(control, &body),
        _ => Err("unknown control command".into()),
    }
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct CancelRequest {
    reason: String,
    runs_dir: Option<PathBuf>,
}

fn cancel_run(control: &Path, id: Uuid, body: &[u8]) -> Result<Value> {
    let request: CancelRequest = serde_json::from_slice(body)?;
    let root = request
        .runs_dir
        .map(|root| root.canonicalize())
        .transpose()?;
    let body = serde_json::to_vec(&json!({"reason": request.reason}))?;
    let path = control.join("queue").join(format!("{id}.json"));
    match queue::read(&path) {
        Ok(delivery) => {
            if root
                .as_deref()
                .is_some_and(|root| delivery.directory.parent() != Some(root))
            {
                return Err("saved Run does not match the requested Runs root".into());
            }
            queue::cancel(control, &delivery, &body)
        }
        Err(error)
            if error
                .downcast_ref::<io::Error>()
                .is_some_and(|error| error.kind() == io::ErrorKind::NotFound) =>
        {
            let root = root
                .or_else(crate::legacy::default_root)
                .ok_or("missing Runs root")?;
            crate::retirement::cancel(&root.join(id.to_string()), id, &body)
        }
        Err(error) => Err(error),
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
        .with_header(header("X-Content-Type-Options", "nosniff"))
        .with_header(header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"));
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

pub fn require_service(control: &Path) -> Result<()> {
    UnixStream::connect(socket_path(control))
        .map_err(|error| format!("local Harborist service unavailable: {error}"))?;
    Ok(())
}

pub fn service(args: &[OsString]) -> Result<()> {
    let (control, legacy_root) = match args {
        [control] => (control, crate::legacy::default_root()),
        [control, option, root] if option == "--runs-dir" => (control, Some(PathBuf::from(root))),
        _ => return Err("expected service CONTROL_DIR [--runs-dir DIRECTORY]".into()),
    };
    serve(Path::new(control), legacy_root, false)
}

static STOPPING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

extern "C" fn stop_signal(_: libc::c_int) {
    STOPPING.store(true, std::sync::atomic::Ordering::Relaxed);
}

pub fn serve_managed(control: &Path) -> Result<()> {
    use std::sync::atomic::Ordering::Relaxed;
    STOPPING.store(false, Relaxed);
    let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
    action.sa_sigaction = stop_signal as *const () as usize;
    unsafe {
        libc::sigemptyset(&mut action.sa_mask);
        if libc::sigaction(libc::SIGTERM, &action, std::ptr::null_mut()) != 0
            || libc::sigaction(libc::SIGINT, &action, std::ptr::null_mut()) != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    serve(control, crate::legacy::default_root(), true)
}

fn serve(control: &Path, legacy_root: Option<PathBuf>, managed: bool) -> Result<()> {
    let legacy_root = legacy_root
        .map(|path| -> Result<PathBuf> {
            if path.try_exists()? {
                Ok(path.canonicalize()?)
            } else {
                Ok(path)
            }
        })
        .transpose()?;
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
    let outcome = std::thread::scope(|scope| -> Result<()> {
        use std::sync::atomic::Ordering::Relaxed;
        let worker = managed.then(|| {
            scope.spawn(|| {
                let result = queue::work(control, false, || STOPPING.load(Relaxed))
                    .map_err(|error| error.to_string());
                STOPPING.store(true, Relaxed);
                result
            })
        });
        let result = (|| -> Result<()> {
            loop {
                if managed && STOPPING.load(Relaxed) {
                    break;
                }
                let Some(mut request) =
                    server.recv_timeout(std::time::Duration::from_millis(100))?
                else {
                    continue;
                };
                if managed && request.method() == &Method::Post && request.url() == "/shutdown" {
                    STOPPING.store(true, Relaxed);
                    respond_json(request, 200, json!({"stopping": true}));
                    continue;
                }
                if request.method() == &Method::Post && is_write(request.url()) {
                    let route = request.url().to_owned();
                    match command(control, &route, &mut request) {
                        Ok(value) => respond_json(request, 200, value),
                        Err(error) => error_response(request, 400, error),
                    }
                    continue;
                }
                if request.method() == &Method::Get && crate::integrations::is_read(request.url()) {
                    match crate::integrations::read(control, request.url()) {
                        Ok(value) => respond_json(request, 200, value),
                        Err(error) => error_response(request, 404, error),
                    }
                    continue;
                }
                let route = Route::parse(request.url());
                match (request.method(), route) {
                    (&Method::Get, Some(route)) => {
                        match serve_route(&queue_root, legacy_root.as_deref(), route) {
                            Ok(value) => respond_json(request, 200, value),
                            Err(error) => error_response(request, 404, error),
                        }
                    }
                    (&Method::Get, None) => error_response(request, 404, "Unknown control route"),
                    _ => error_response(request, 405, "Read-only control service"),
                }
            }
            Ok(())
        })();
        if let Some(worker) = worker {
            STOPPING.store(true, Relaxed);
            worker.join().map_err(|_| "Harborist worker panicked")??;
        }
        result
    });
    drop(server);
    match fs::remove_file(&path) {
        Ok(()) => (),
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.into()),
    }
    outcome
}

pub fn read(control: &Path, route: &str) -> Result<Value> {
    request(control, route, None)
}

pub fn write(control: &Path, route: &str, payload: &Value) -> Result<Value> {
    let bytes = serde_json::to_vec(payload)?;
    request(control, route, Some(&bytes))
}

fn request(control: &Path, route: &str, payload: Option<&[u8]>) -> Result<Value> {
    let (status, body) = proxy(control, route, payload)?;
    let response: Value = serde_json::from_slice(&body)?;
    if status != 200 {
        return Err(response["error"]
            .as_str()
            .unwrap_or("control request failed")
            .to_owned()
            .into());
    }
    Ok(response)
}

fn proxy(control: &Path, route: &str, body: Option<&[u8]>) -> Result<(u16, Vec<u8>)> {
    let mut stream = UnixStream::connect(socket_path(control))?;
    let timeout = Some(Duration::from_secs(match (body, route) {
        (Some(_), "/tickets/list" | "/tickets/queue") => 180,
        (Some(_), _) => 45,
        (None, _) => 5,
    }));
    stream.set_read_timeout(timeout)?;
    stream.set_write_timeout(timeout)?;
    if let Some(body) = body {
        write!(
            stream,
            "POST {route} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
            body.len()
        )?;
        stream.write_all(body)?;
    } else {
        write!(
            stream,
            "GET {route} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        )?;
    }
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
    let (control, port, listener) = match args {
        [control, port] => (control, port, "127.0.0.1"),
        [control, port, flag] if flag == "--container-listener" => (control, port, "0.0.0.0"),
        _ => return Err("expected web CONTROL_DIR PORT [--container-listener]".into()),
    };
    let control = Path::new(control);
    let port: u16 = port.to_str().ok_or("expected a port")?.parse()?;
    if port == 0 {
        return Err("expected a nonzero loopback port".into());
    }
    let allowed = [format!("127.0.0.1:{port}"), format!("localhost:{port}")];
    let server = Server::http((listener, port)).map_err(|error| error.to_string())?;
    eprintln!("Harborist workspace at http://127.0.0.1:{port}");
    for mut request in server.incoming_requests() {
        let Some(host) =
            header(&request, "Host").filter(|host| allowed.iter().any(|value| value == host))
        else {
            error_response(request, 403, "Loopback host required");
            continue;
        };
        let path = request
            .url()
            .split('?')
            .next()
            .unwrap_or_default()
            .to_owned();
        if request.method() == &Method::Post {
            if let Some(route) = path.strip_prefix("/api").filter(|route| is_write(route)) {
                if header(&request, "Origin") != Some(format!("http://{host}").as_str())
                    || header(&request, "X-Harborist-Workspace") != Some("1")
                {
                    error_response(request, 403, "Same-origin workspace request required");
                } else {
                    match request_body(&mut request) {
                        Ok(body) => match proxy(control, route, Some(&body)) {
                            Ok((status, body)) => respond(request, status, JSON, body),
                            Err(error) => error_response(request, 503, error),
                        },
                        Err(error) => error_response(request, 400, error),
                    }
                }
                continue;
            }
        }
        if request.method() != &Method::Get {
            error_response(request, 405, "Unsupported browser command");
            continue;
        }
        if let Some(route) = path.strip_prefix("/api") {
            if Route::parse(route).is_none() && !crate::integrations::is_read(route) {
                error_response(request, 404, "Unknown API route");
            } else {
                match proxy(control, route, None) {
                    Ok((status, body)) => respond(request, status, JSON, body),
                    Err(error) => error_response(request, 503, error),
                }
            }
            continue;
        }
        let page = if matches!(
            path.as_str(),
            "/runs" | "/evidence" | "/workspaces" | "/tickets" | "/integrations" | "/settings"
        ) || matches!(Route::parse(&path), Some(Route::Run(_)))
        {
            "/"
        } else {
            path.as_str()
        };
        if let Some((_, mime, body)) = ASSETS.iter().find(|(name, _, _)| name == &page) {
            respond(request, 200, mime, body.to_vec());
        } else {
            error_response(request, 404, "Unknown page");
        }
    }
    Ok(())
}
