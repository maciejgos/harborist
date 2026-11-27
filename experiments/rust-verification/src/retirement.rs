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
    retire(directory, id, &request.reason, None)
}

pub fn validate_reason(reason: &str) -> Result<&str> {
    let reason = reason.trim();
    if reason.is_empty() || reason.chars().count() > 1000 {
        return Err("retirement requires a reason of 1 to 1000 characters".into());
    }
    Ok(reason)
}

pub fn existing(
    directory: &Path,
    id: Uuid,
    reason: &str,
    replacement: Option<Uuid>,
) -> Result<Option<serde_json::Value>> {
    existing_marker(&path(directory), id, reason, replacement)
}

fn existing_marker(
    marker: &Path,
    id: Uuid,
    reason: &str,
    replacement: Option<Uuid>,
) -> Result<Option<serde_json::Value>> {
    let raw = match fs::read(marker) {
        Ok(raw) => raw,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let previous: serde_json::Value = serde_json::from_slice(&raw)?;
    if previous["run_id"] != serde_json::json!(id)
        || previous["reason"] != reason
        || previous["replacement"] != serde_json::json!(replacement)
    {
        return Err("Run already has a different retirement record".into());
    }
    Ok(Some(previous))
}

pub fn retire(
    directory: &Path,
    id: Uuid,
    reason: &str,
    replacement: Option<Uuid>,
) -> Result<serde_json::Value> {
    let reason = validate_reason(reason)?;
    if store::load(directory)?.contract.run_id != id {
        return Err("cancellation must match the requested Run".into());
    }
    record(&path(directory), id, reason, replacement)
}

pub fn cancel_marker(marker: &Path, id: Uuid, body: &[u8]) -> Result<serde_json::Value> {
    let request: Request = serde_json::from_slice(body)?;
    record(marker, id, validate_reason(&request.reason)?, None)
}

fn record(
    marker: &Path,
    id: Uuid,
    reason: &str,
    replacement: Option<Uuid>,
) -> Result<serde_json::Value> {
    let directory = marker.parent().ok_or("missing retirement marker parent")?;
    let timestamp: u64 = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_millis()
        .try_into()?;
    let retirement = serde_json::json!({
        "run_id": id, "reason": reason, "timestamp": timestamp,
        "actor": "operator", "replacement": replacement, "attempt": null, "stage": null,
    });
    let pending = directory.join(format!(".retirement-{}.pending", Uuid::new_v4()));
    store::write_new(&pending, &serde_json::to_vec(&retirement)?)?;
    let linked = fs::hard_link(&pending, marker);
    fs::remove_file(pending)?;
    match linked {
        Ok(()) => {
            File::open(directory)?.sync_all()?;
            Ok(retirement)
        }
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
            existing_marker(marker, id, reason, replacement)?
                .ok_or_else(|| "retirement record disappeared".into())
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
