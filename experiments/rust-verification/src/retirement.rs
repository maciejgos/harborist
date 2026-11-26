//! Durable operator cancellation, shared across the service and worker.

use crate::{Result, store};
use serde::Deserialize;
use std::{
    fs::{self, File},
    io,
    path::{Path, PathBuf},
};
use uuid::Uuid;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    reason: String,
}

pub fn path(directory: &Path) -> PathBuf {
    directory.join("retirement.json")
}

pub fn cancelled(marker: &Path) -> io::Result<()> {
    if marker.try_exists()? {
        return Err(io::Error::new(io::ErrorKind::Interrupted, "Run cancelled"));
    }
    Ok(())
}

pub fn cancel(directory: &Path, id: Uuid, body: &[u8]) -> Result<serde_json::Value> {
    let request: Request = serde_json::from_slice(body)?;
    let reason = request.reason.trim();
    if reason.is_empty() || reason.chars().count() > 1000 {
        return Err("cancellation requires a reason of 1 to 1000 characters".into());
    }
    if store::load(directory)?.contract.run_id != id {
        return Err("cancellation must match the requested Run".into());
    }
    let marker = path(directory);
    let timestamp: u64 = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_millis()
        .try_into()?;
    let retirement = serde_json::json!({
        "run_id": id, "reason": reason, "timestamp": timestamp,
        "actor": "operator", "replacement": null, "attempt": null, "stage": null,
    });
    let pending = directory.join(format!(".retirement-{}.pending", Uuid::new_v4()));
    store::write_new(&pending, &serde_json::to_vec(&retirement)?)?;
    let linked = fs::hard_link(&pending, &marker);
    fs::remove_file(pending)?;
    match linked {
        Ok(()) => {
            File::open(directory)?.sync_all()?;
            Ok(retirement)
        }
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
            let previous: serde_json::Value = serde_json::from_slice(&fs::read(marker)?)?;
            if previous["run_id"] != serde_json::json!(id)
                || previous["reason"] != reason
                || !previous["replacement"].is_null()
            {
                return Err("Run already has a different retirement record".into());
            }
            Ok(previous)
        }
        Err(error) => Err(error.into()),
    }
}

pub fn execute(args: &[std::ffi::OsString]) -> Result<()> {
    let [directory, reason] = args else {
        return Err("expected cancel RUN_DIR REASON".into());
    };
    let run = store::load(Path::new(directory))?;
    let reason = reason
        .to_str()
        .ok_or("expected a UTF-8 cancellation reason")?;
    let body = serde_json::to_vec(&serde_json::json!({"reason": reason}))?;
    println!("{}", cancel(&run.directory, run.contract.run_id, &body)?);
    Ok(())
}
