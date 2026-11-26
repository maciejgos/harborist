//! Saved defaults and idempotent browser capture for the local control plane.

use crate::{Config, Result, git, git_text, queue, settings::Execution, store};
use harborist_verify::workflow::Sha;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    ffi::OsStr,
    fs::{self, File},
    io,
    path::{Path, PathBuf},
};
use uuid::Uuid;

fn default_ref() -> String {
    "HEAD".to_owned()
}
fn default_total() -> u64 {
    store::TOTAL_SECONDS
}
fn default_reserve() -> u64 {
    store::VERIFICATION_RESERVE_SECONDS
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Workspace {
    id: Uuid,
    name: String,
    repository: PathBuf,
    settings: Option<PathBuf>,
    #[serde(default = "default_ref", rename = "ref")]
    reference: String,
    #[serde(default = "default_total")]
    timeout: u64,
    #[serde(default = "default_reserve")]
    verification_reserve: u64,
    github_repository: Option<String>,
}

#[derive(Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct CaptureRequest {
    request_id: Uuid,
    source: String,
    repository: PathBuf,
    settings: Option<PathBuf>,
    #[serde(default = "default_ref", rename = "ref")]
    reference: String,
    #[serde(default = "default_total")]
    timeout: u64,
    #[serde(default = "default_reserve")]
    verification_reserve: u64,
}

fn normalize(path: &Path) -> Result<PathBuf> {
    if path.is_absolute() {
        return Ok(path.to_owned());
    }
    if let Ok(relative) = path.strip_prefix("~") {
        let home = std::env::var_os("HOME").ok_or("home directory is unavailable")?;
        return Ok(PathBuf::from(home).join(relative));
    }
    Err("enter an absolute path or a path starting with ~/".into())
}

fn base(repo: &Path, reference: &str) -> Result<Sha> {
    if reference.trim().is_empty() || reference.chars().count() > 256 {
        return Err("invalid base Git ref".into());
    }
    let resolved = git_text(
        repo,
        &[
            "rev-parse",
            "--verify",
            "--end-of-options",
            &format!("{reference}^{{commit}}"),
        ],
    )?;
    Ok(resolved.parse()?)
}

pub fn list(control: &Path) -> Result<Value> {
    let mut workspaces = Vec::new();
    match fs::read_dir(control.join("workspaces")) {
        Ok(entries) => {
            for entry in entries {
                let path = entry?.path();
                if path.extension() == Some(OsStr::new("json")) {
                    let workspace: Workspace = serde_json::from_slice(&fs::read(&path)?)?;
                    if path.file_stem().and_then(OsStr::to_str) != Some(&workspace.id.to_string()) {
                        return Err("Workspace identity mismatch".into());
                    }
                    workspaces.push(workspace);
                }
            }
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.into()),
    }
    workspaces.sort_by_key(|workspace| (workspace.name.to_lowercase(), workspace.id));
    Ok(json!({"workspaces": workspaces}))
}

pub fn save(control: &Path, body: &[u8]) -> Result<Value> {
    let mut workspace: Workspace = serde_json::from_slice(body)?;
    workspace.name = workspace.name.trim().to_owned();
    workspace.reference = workspace.reference.trim().to_owned();
    if workspace.name.is_empty()
        || workspace.name.chars().count() > 100
        || workspace
            .github_repository
            .as_ref()
            .is_some_and(|value| value.len() > 256 || !crate::github::valid_repository(value))
    {
        return Err("enter a Workspace name and valid optional GitHub repository".into());
    }
    store::validate_budget(workspace.timeout, workspace.verification_reserve)?;
    workspace.repository = store::repository(&normalize(&workspace.repository)?)?;
    let sha = base(&workspace.repository, &workspace.reference)?;
    let yaml = git(
        &workspace.repository,
        &["show".as_ref(), format!("{sha}:harborist.yaml").as_ref()],
    )?;
    Config::parse(&yaml)?;
    workspace.settings = workspace.settings.as_deref().map(normalize).transpose()?;
    Execution::load(&workspace.repository, workspace.settings.as_deref())?;
    if workspace.github_repository.is_none() {
        workspace.github_repository =
            git_text(&workspace.repository, &["remote", "get-url", "origin"])
                .ok()
                .and_then(|remote| {
                    let repository = [
                        "https://github.com/",
                        "git@github.com:",
                        "ssh://git@github.com/",
                    ]
                    .into_iter()
                    .find_map(|prefix| remote.strip_prefix(prefix))?
                    .trim_end_matches('/');
                    let repository = repository.strip_suffix(".git").unwrap_or(repository);
                    crate::github::valid_repository(repository).then(|| repository.to_owned())
                });
    }
    let directory = control.join("workspaces");
    fs::create_dir_all(&directory)?;
    let pending = directory.join(format!(".{}.pending", Uuid::new_v4()));
    store::write_new(&pending, &serde_json::to_vec(&workspace)?)?;
    let saved = fs::rename(&pending, directory.join(format!("{}.json", workspace.id)));
    if saved.is_err() {
        fs::remove_file(pending)?;
    }
    saved?;
    File::open(directory)?.sync_all()?;
    Ok(serde_json::to_value(workspace)?)
}

pub fn capture(control: &Path, body: &[u8]) -> Result<Value> {
    let request: CaptureRequest = serde_json::from_slice(body)?;
    let captured = capture_saved(control, request, &control.join("workspace-requests"))?;
    let record = queue::enqueue(control, captured)?;
    Ok(json!({"run_id": record.run_id}))
}

fn capture_saved(
    control: &Path,
    request: CaptureRequest,
    receipts: &Path,
) -> Result<store::Captured> {
    if request.request_id.get_version_num() != 4 || request.source.chars().count() > 4096 {
        return Err("invalid capture request identity or source".into());
    }
    store::validate_budget(request.timeout, request.verification_reserve)?;
    let source: std::ffi::OsString =
        if request.source.starts_with("github:") || request.source.starts_with("https://") {
            crate::github::selector(&request.source)?.into()
        } else {
            let source = request
                .source
                .strip_prefix("file:")
                .unwrap_or(&request.source);
            normalize(Path::new(source))?.into_os_string()
        };
    let repo = normalize(&request.repository)?;
    let settings = request.settings.as_deref().map(normalize).transpose()?;
    let runs = control.join("runs");
    fs::create_dir_all(&runs)?;
    fs::create_dir_all(receipts)?;
    let directory = runs.join(request.request_id.to_string());
    let receipt = receipts.join(format!("{}.json", request.request_id));
    match fs::read(&receipt) {
        Ok(bytes) if serde_json::from_slice::<CaptureRequest>(&bytes)? != request => {
            return Err("request ID was already used with different inputs".into());
        }
        Ok(_) => (),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            if directory.exists() {
                return Err("request ID already belongs to a saved Run".into());
            }
            store::write_new(&receipt, &serde_json::to_vec(&request)?)?;
            File::open(receipts)?.sync_all()?;
        }
        Err(error) => return Err(error.into()),
    }
    let captured = if directory.join("contract.json").exists() {
        store::load(&directory)?
    } else {
        store::capture_to(store::Capture {
            repository: &repo,
            base_sha: base(&repo, &request.reference)?,
            source: &source,
            directory: &directory,
            settings: settings.as_deref(),
            run_id: request.request_id,
            total_seconds: request.timeout,
            verification_reserve_seconds: request.verification_reserve,
        })?
    };
    if captured.contract.run_id != request.request_id {
        return Err("saved Run does not match capture request".into());
    }
    Ok(captured)
}

pub fn supersede(control: &Path, original: &queue::Delivery, body: &[u8]) -> Result<Value> {
    let mut payload: Value = serde_json::from_slice(body)?;
    let reason = payload
        .as_object_mut()
        .and_then(|fields| fields.remove("reason"))
        .and_then(|reason| reason.as_str().map(str::to_owned))
        .ok_or("supersession requires a reason")?;
    let reason = crate::retirement::validate_reason(&reason)?;
    let request: CaptureRequest = serde_json::from_value(payload)?;
    let replacement = request.request_id;
    if replacement == original.run_id {
        return Err("replacement must be a distinct Run".into());
    }
    let previous = crate::retirement::existing(
        &original.directory,
        original.run_id,
        reason,
        Some(replacement),
    )?;
    let receipts = control
        .join("supersession-requests")
        .join(original.run_id.to_string());
    let captured = capture_saved(control, request, &receipts)?;
    if previous.is_none()
        && (captured.directory.join("attempt.json").try_exists()?
            || crate::retirement::path(&captured.directory).try_exists()?
            || control
                .join("queue")
                .join(format!("{replacement}.json"))
                .try_exists()?)
    {
        return Err("replacement must be a fresh captured Run".into());
    }
    let record = crate::retirement::retire(
        &original.directory,
        original.run_id,
        reason,
        Some(replacement),
    )?;
    queue::enqueue(control, captured)?;
    Ok(record)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TicketRequest {
    request_id: Uuid,
    source: String,
    workspace_id: Uuid,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct TicketSnapshot {
    workspace_id: Uuid,
    capture: CaptureRequest,
}

pub fn queue_ticket(control: &Path, body: &[u8]) -> Result<Value> {
    let request: TicketRequest = serde_json::from_slice(body)?;
    if request.request_id.get_version_num() != 4 || request.source.chars().count() > 320 {
        return Err("invalid ticket request identity or source".into());
    }
    let source = request.source.trim();
    let source = format!(
        "github:{}",
        source.strip_prefix("github:").unwrap_or(source)
    );
    let source = crate::github::selector(&source)?;
    let receipts = control.join("ticket-requests");
    let receipt = receipts.join(format!("{}.json", request.request_id));
    let saved = match fs::read(receipt.as_path()) {
        Ok(raw) => {
            let saved: TicketSnapshot = serde_json::from_slice(&raw)?;
            if saved.workspace_id != request.workspace_id
                || saved.capture.request_id != request.request_id
                || saved.capture.source != source
            {
                return Err(
                    "request ID was already used with a different ticket or Workspace".into(),
                );
            }
            saved
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let path = control
                .join("workspaces")
                .join(format!("{}.json", request.workspace_id));
            let workspace: Workspace = serde_json::from_slice(&fs::read(path)?)?;
            if workspace.id != request.workspace_id {
                return Err("Workspace identity mismatch".into());
            }
            let saved = TicketSnapshot {
                workspace_id: workspace.id,
                capture: CaptureRequest {
                    request_id: request.request_id,
                    source,
                    repository: workspace.repository,
                    settings: workspace.settings,
                    reference: workspace.reference,
                    timeout: workspace.timeout,
                    verification_reserve: workspace.verification_reserve,
                },
            };
            fs::create_dir_all(&receipts)?;
            store::write_new(&receipt, &serde_json::to_vec(&saved)?)?;
            File::open(receipts)?.sync_all()?;
            saved
        }
        Err(error) => return Err(error.into()),
    };
    capture(control, &serde_json::to_vec(&saved.capture)?)
}
