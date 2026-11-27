//! Durable delivery state for one local worker.

use crate::{Result, continuation, foreground, store};
use serde::{Deserialize, Serialize};
use std::{
    ffi::{OsStr, OsString},
    fs::{self, DirBuilder, File, OpenOptions},
    io,
    os::{
        fd::AsRawFd,
        unix::fs::{DirBuilderExt, OpenOptionsExt},
    },
    path::{Path, PathBuf},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use uuid::Uuid;

#[derive(Clone, Copy, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum State {
    Queued,
    Running,
    Finished,
    Failed,
    Interrupted,
    Cancelled,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Delivery {
    pub run_id: Uuid,
    pub directory: PathBuf,
    submitted_ns: u128,
    pub state: State,
    pub error: Option<String>,
    pub continuation: Option<continuation::Request>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    python_source: Option<PathBuf>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    workspace: Option<PathBuf>,
}

pub(crate) fn saved(run_id: Uuid, directory: PathBuf) -> Delivery {
    Delivery {
        run_id,
        directory,
        submitted_ns: 0,
        state: State::Queued,
        error: None,
        continuation: None,
        python_source: None,
        workspace: None,
    }
}

pub fn queue_directory(root: &Path) -> Result<PathBuf> {
    DirBuilder::new().recursive(true).mode(0o700).create(root)?;
    let directory = root.canonicalize()?.join("queue");
    DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(&directory)?;
    Ok(directory)
}

pub fn read(path: &Path) -> Result<Delivery> {
    let record: Delivery = serde_json::from_slice(&fs::read(path)?)?;
    let name = format!("{}.json", record.run_id);
    if path.file_name() != Some(OsStr::new(&name)) {
        return Err("delivery file does not match its Run ID".into());
    }
    Ok(record)
}

fn persist(queue: &Path, record: &Delivery, replace: bool) -> Result<()> {
    let pending = queue.join(format!(".{}.pending", Uuid::new_v4()));
    let path = queue.join(format!("{}.json", record.run_id));
    store::write_new(&pending, &serde_json::to_vec_pretty(record)?)?;
    let publish = if replace {
        fs::rename(&pending, &path)
    } else {
        fs::hard_link(&pending, &path)
    };
    if !replace || publish.is_err() {
        fs::remove_file(&pending)?;
    }
    publish?;
    File::open(queue)?.sync_all()?;
    Ok(())
}

pub fn submit(args: &[OsString]) -> Result<()> {
    let [control, directory] = args else {
        return Err("expected submit CONTROL_DIR RUN_DIR".into());
    };
    let run = store::load(Path::new(directory))?;
    let saved = enqueue(Path::new(control), run)?;
    println!("{}", serde_json::to_string(&saved)?);
    Ok(())
}

pub fn submit_python_continuation(args: &[OsString]) -> Result<()> {
    let [control, args @ ..] = args else {
        return Err("expected submit-python-continuation CONTROL_DIR ACTION PYTHON_RUN_DIR NEW_RUST_RUN_DIR EXPECTED_ATTEMPT FEEDBACK [ADDITIONAL_SECONDS]".into());
    };
    let (source, destination, request) = crate::legacy::continuation_arguments(args)?;
    let prepared = crate::legacy::prepare_continuation(&source, &destination, &request)?;
    let queue = queue_directory(Path::new(control))?;
    let record = Delivery {
        run_id: prepared.run_id(),
        directory: prepared.destination.clone(),
        submitted_ns: SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos(),
        state: State::Queued,
        error: None,
        continuation: Some(request),
        python_source: Some(source),
        workspace: None,
    };
    persist(&queue, &record, false)?;
    println!("{}", serde_json::to_string(&record)?);
    Ok(())
}

pub fn enqueue(control: &Path, run: store::Captured) -> Result<Delivery> {
    enqueue_with_workspace(control, run, None)
}

pub fn enqueue_with_workspace(
    control: &Path,
    run: store::Captured,
    workspace: Option<&Path>,
) -> Result<Delivery> {
    let workspace = workspace
        .map(|path| foreground::workspace_path(&run, path))
        .transpose()?;
    let queue = queue_directory(control)?;
    let path = queue.join(format!("{}.json", run.contract.run_id));
    let record = Delivery {
        run_id: run.contract.run_id,
        directory: run.directory,
        submitted_ns: SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos(),
        state: State::Queued,
        error: None,
        continuation: None,
        python_source: None,
        workspace,
    };
    let saved = match persist(&queue, &record, false) {
        Ok(()) => record,
        Err(error)
            if error
                .downcast_ref::<io::Error>()
                .is_some_and(|error| error.kind() == io::ErrorKind::AlreadyExists) =>
        {
            let saved = read(&path)?;
            if saved.directory != record.directory || saved.workspace != record.workspace {
                return Err("Run ID already belongs to a different directory".into());
            }
            saved
        }
        Err(error) => return Err(error),
    };
    Ok(saved)
}

fn historical_marker(queue: &Path, id: Uuid) -> PathBuf {
    queue.join(format!("{id}.retirement"))
}

pub fn cancel(control: &Path, delivery: &Delivery, body: &[u8]) -> Result<serde_json::Value> {
    if delivery.python_source.is_some() {
        crate::retirement::cancel_marker(
            &historical_marker(&queue_directory(control)?, delivery.run_id),
            delivery.run_id,
            body,
        )
    } else {
        crate::retirement::cancel(&delivery.directory, delivery.run_id, body)
    }
}

fn marker(queue: &Path, delivery: &Delivery) -> PathBuf {
    if delivery.python_source.is_some() {
        historical_marker(queue, delivery.run_id)
    } else {
        crate::retirement::path(&delivery.directory)
    }
}

pub fn continue_run(control: &Path, id: Uuid, body: &[u8]) -> Result<serde_json::Value> {
    let request: continuation::Request = serde_json::from_slice(body)?;
    let queue = queue_directory(control)?;
    let path = queue.join(format!("{id}.json"));
    let observed = read(&path)?;
    crate::retirement::cancelled(&marker(&queue, &observed))?;
    if let Some(previous) = &observed.continuation {
        if previous.request_id == request.request_id {
            if previous != &request {
                return Err("continuation request ID has different inputs".into());
            }
            return Ok(serde_json::json!({"run_id": id}));
        }
    }
    let directory = observed.directory;
    let _lock = continuation::lock(&directory)?;
    let mut record = read(&path)?;
    crate::retirement::cancelled(&marker(&queue, &record))?;
    if record.directory != directory {
        return Err("Run directory changed during continuation admission".into());
    }
    let accepted = serde_json::json!({"run_id": id});
    if let Some(previous) = &record.continuation {
        if previous.request_id == request.request_id {
            if previous != &request {
                return Err("continuation request ID has different inputs".into());
            }
            return Ok(accepted);
        }
    }
    let history = queue.join("continuations").join(id.to_string());
    let receipt = |request_id: Uuid| history.join(format!("{request_id}.json"));
    match fs::read(receipt(request.request_id)) {
        Ok(raw) => {
            let previous: continuation::Request = serde_json::from_slice(&raw)?;
            if previous != request {
                return Err("continuation request ID has different inputs".into());
            }
            return Ok(accepted);
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.into()),
    }
    if matches!(
        record.state,
        State::Queued | State::Running | State::Cancelled
    ) {
        return Err("continuation requires an available terminal delivery".into());
    }
    let capture = store::load(&directory)?;
    if capture.contract.run_id != id {
        return Err("saved Run ID does not match continuation request".into());
    }
    continuation::validate(&capture, &request)?;
    if let Some(previous) = &record.continuation {
        fs::create_dir_all(&history)?;
        let path = receipt(previous.request_id);
        match store::write_new(&path, &serde_json::to_vec(previous)?) {
            Ok(()) => File::open(&history)?.sync_all()?,
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                let saved: continuation::Request = serde_json::from_slice(&fs::read(path)?)?;
                if &saved != previous {
                    return Err("continuation history disagrees with the active record".into());
                }
            }
            Err(error) => return Err(error.into()),
        }
    }
    record.continuation = Some(request);
    record.python_source = None;
    record.state = State::Queued;
    record.error = None;
    record.submitted_ns = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    persist(&queue, &record, true)?;
    Ok(accepted)
}

pub fn delivery(args: &[OsString]) -> Result<()> {
    let [control, id] = args else {
        return Err("expected delivery CONTROL_DIR RUN_UUID".into());
    };
    let id = Uuid::parse_str(id.to_str().ok_or("expected a Run UUID")?)?;
    let path = Path::new(control).join("queue").join(format!("{id}.json"));
    println!("{}", serde_json::to_string(&read(&path)?)?);
    Ok(())
}

pub fn records(queue: &Path) -> Result<Vec<Delivery>> {
    let mut records = Vec::new();
    for entry in fs::read_dir(queue)? {
        let path = entry?.path();
        if path.extension().is_some_and(|suffix| suffix == "json") {
            records.push(read(&path)?);
        }
    }
    records.sort_unstable_by_key(|record| (record.submitted_ns, record.run_id));
    Ok(records)
}

fn lock_worker(queue: &Path) -> Result<File> {
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .mode(0o600)
        .open(queue.join("worker.lock"))?;
    // The lock is held for the lifetime of this descriptor.
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(file)
}

fn execute(queue: &Path, record: &Delivery) -> Result<serde_json::Value> {
    if let Some(source) = &record.python_source {
        let request = record
            .continuation
            .as_ref()
            .ok_or("historical delivery lacks continuation request")?;
        let prepared = crate::legacy::prepare_continuation(source, &record.directory, request)?;
        if prepared.run_id() != record.run_id {
            return Err("historical Run ID does not match delivery".into());
        }
        return prepared.execute(request, Some(marker(queue, record)));
    }
    let capture = store::load(&record.directory)?;
    if capture.contract.run_id != record.run_id {
        return Err("saved Run ID does not match delivery".into());
    }
    if let Some(request) = &record.continuation {
        continuation::run(capture, request)
    } else {
        foreground::execute_with_workspace(capture, record.workspace.as_deref())
    }
}

pub fn worker(args: &[OsString]) -> Result<()> {
    let (control, once) = match args {
        [control] => (control, false),
        [control, option] if option == "--once" => (control, true),
        _ => return Err("expected worker CONTROL_DIR [--once]".into()),
    };
    work(Path::new(control), once, || false)
}

pub(crate) fn work(control: &Path, once: bool, stopping: impl Fn() -> bool) -> Result<()> {
    let queue = queue_directory(control)?;
    let _guard = lock_worker(&queue)?;
    for mut record in records(&queue)? {
        if record.state == State::Running {
            record.state = if marker(&queue, &record).exists() {
                State::Cancelled
            } else {
                State::Interrupted
            };
            if record.state == State::Interrupted {
                continuation::record_worker_loss(
                    &record.directory,
                    record.run_id,
                    record.continuation.as_ref(),
                )?;
            }
            record.error = Some("Previous worker stopped during delivery".into());
            persist(&queue, &record, true)?;
        }
    }
    while !stopping() {
        let next = records(&queue)?
            .into_iter()
            .find(|record| record.state == State::Queued);
        if let Some(mut record) = next {
            let marker = marker(&queue, &record);
            if marker.try_exists()? {
                record.state = State::Cancelled;
                persist(&queue, &record, true)?;
                if once {
                    return Ok(());
                }
                continue;
            }
            record.state = State::Running;
            persist(&queue, &record, true)?;

            let execution = execute(&queue, &record);
            match execution {
                _ if marker.try_exists()? => record.state = State::Cancelled,
                Ok(_) => record.state = State::Finished,
                Err(error) => {
                    record.state = State::Failed;
                    record.error = Some(error.to_string());
                }
            }
            persist(&queue, &record, true)?;
        } else if !once {
            thread::sleep(Duration::from_millis(250));
        }
        if once {
            return Ok(());
        }
    }
    Ok(())
}
