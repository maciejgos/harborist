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

pub fn enqueue(control: &Path, run: store::Captured) -> Result<Delivery> {
    let queue = queue_directory(control)?;
    let path = queue.join(format!("{}.json", run.contract.run_id));
    let record = Delivery {
        run_id: run.contract.run_id,
        directory: run.directory,
        submitted_ns: SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos(),
        state: State::Queued,
        error: None,
        continuation: None,
    };
    let saved = match persist(&queue, &record, false) {
        Ok(()) => record,
        Err(error)
            if error
                .downcast_ref::<io::Error>()
                .is_some_and(|error| error.kind() == io::ErrorKind::AlreadyExists) =>
        {
            let saved = read(&path)?;
            if saved.directory != record.directory {
                return Err("Run ID already belongs to a different directory".into());
            }
            saved
        }
        Err(error) => return Err(error),
    };
    Ok(saved)
}

pub fn continue_run(control: &Path, id: Uuid, body: &[u8]) -> Result<serde_json::Value> {
    let request: continuation::Request = serde_json::from_slice(body)?;
    let queue = queue_directory(control)?;
    let path = queue.join(format!("{id}.json"));
    let observed = read(&path)?;
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

pub fn worker(args: &[OsString]) -> Result<()> {
    let (control, once) = match args {
        [control] => (control, false),
        [control, option] if option == "--once" => (control, true),
        _ => return Err("expected worker CONTROL_DIR [--once]".into()),
    };
    let queue = queue_directory(Path::new(control))?;
    let _guard = lock_worker(&queue)?;
    for mut record in records(&queue)? {
        if record.state == State::Running {
            record.state = if crate::retirement::path(&record.directory).exists() {
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
    loop {
        let next = records(&queue)?
            .into_iter()
            .find(|record| record.state == State::Queued);
        if let Some(mut record) = next {
            let marker = crate::retirement::path(&record.directory);
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

            let execution = store::load(&record.directory).and_then(|capture| {
                if capture.contract.run_id != record.run_id {
                    return Err("saved Run ID does not match delivery".into());
                }
                if let Some(request) = &record.continuation {
                    continuation::run(capture, request)
                } else {
                    foreground::execute(capture)
                }
            });
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
}
