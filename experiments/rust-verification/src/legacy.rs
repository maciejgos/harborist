//! Read historical Python Run files without changing their layout or lifecycle.

use crate::{Result, continuation, record::read_artifact, store::digest};
use harborist_verify::workflow::{Attempt, Sha};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs, io,
    path::{Path, PathBuf},
};
use uuid::Uuid;

#[derive(Deserialize)]
struct Contract {
    run_id: Uuid,
    base_sha: Sha,
    intent: Intent,
    verification: Value,
}

#[derive(Deserialize)]
struct Intent {
    source_ref: String,
    source_url: Option<String>,
    markdown: String,
    artifact: IntentArtifact,
}

#[derive(Deserialize)]
struct IntentArtifact {
    run_id: Uuid,
    size_bytes: usize,
    sha256: String,
}

#[derive(Deserialize, Serialize, PartialEq)]
struct Snapshot {
    run_id: Uuid,
    lifecycle: Lifecycle,
    outcome: Option<String>,
    failure_reason: Option<String>,
    verification: Option<Value>,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum Lifecycle {
    Created,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Deserialize)]
struct Event {
    event_type: String,
    run: Snapshot,
}

fn snapshot(directory: &Path, id: Uuid) -> Result<Snapshot> {
    let saved: Snapshot = serde_json::from_str(&read_artifact(directory, "run.json")?)?;
    if saved.run_id != id {
        return Err("historical lifecycle belongs to another Run".into());
    }
    if !directory.join("events.jsonl").try_exists()? {
        return if saved.lifecycle == Lifecycle::Created && saved.valid() {
            Ok(saved)
        } else {
            Err("historical lifecycle lacks its journal".into())
        };
    }
    let journal = read_artifact(directory, "events.jsonl")?;
    let mut last = None;
    for line in journal.lines() {
        let event: Event = serde_json::from_str(line)?;
        let life = event.run.lifecycle;
        let valid = matches!(
            (
                last.as_ref().map(|run: &Snapshot| run.lifecycle),
                event.event_type.as_str(),
                life
            ),
            (None, "run_created", Lifecycle::Created)
                | (Some(Lifecycle::Created), "run_started", Lifecycle::Running)
                | (
                    Some(Lifecycle::Running),
                    "run_completed",
                    Lifecycle::Completed
                )
                | (
                    Some(Lifecycle::Created | Lifecycle::Running),
                    "run_failed",
                    Lifecycle::Failed
                )
                | (
                    Some(Lifecycle::Created | Lifecycle::Running),
                    "run_cancelled",
                    Lifecycle::Cancelled
                )
        );
        if !valid || event.run.run_id != id || !event.run.valid() {
            return Err("historical lifecycle journal has an invalid transition".into());
        }
        last = Some(event.run);
    }
    if last.as_ref() != Some(&saved) {
        return Err("historical lifecycle snapshot disagrees with its journal".into());
    }
    Ok(saved)
}

impl Snapshot {
    fn valid(&self) -> bool {
        let outcome = self.outcome.as_deref();
        let verified = outcome == Some("VERIFIED");
        if self.verification.is_some() != verified {
            return false;
        }
        match self.lifecycle {
            Lifecycle::Completed => {
                self.failure_reason.is_none()
                    && matches!(
                        outcome,
                        Some(
                            "VERIFIED"
                                | "NEEDS_CLARIFICATION"
                                | "NEEDS_RESCOPING"
                                | "TEST_FAILED"
                                | "CHANGES_REQUIRED"
                        )
                    )
            }
            Lifecycle::Failed => self.failure_reason.is_some() && outcome.is_none(),
            _ => outcome.is_none() && self.failure_reason.is_none(),
        }
    }
}

fn validate_verification(
    contract: &Contract,
    attempt: Option<&Attempt>,
    verification: &Value,
) -> Result<Sha> {
    let attempt = attempt.ok_or("historical verification lacks its Attempt")?;
    let candidate: Sha =
        serde_json::from_value(verification["candidate"]["candidate_sha"].clone())?;
    let identity = json!(attempt.candidate(candidate.clone()));
    if verification["run_id"] != json!(contract.run_id)
        || verification["attempt"] != json!(attempt)
        || verification["candidate"] != identity
        || verification["review"]["candidate"] != identity
        || verification["verification"] != contract.verification
    {
        return Err("historical verification attribution does not match".into());
    }
    let required = contract.verification["config"]["checks"]
        .as_array()
        .ok_or("missing frozen checks")?;
    let captured = verification["checks"]
        .as_array()
        .ok_or("missing verification checks")?;
    if required.is_empty()
        || required.len() != captured.len()
        || !required.iter().zip(captured).all(|(a, b)| {
            a["id"].is_string()
                && a["command"].is_string()
                && a["id"] == b["id"]
                && a["command"] == b["command"]
                && b["passed"] == true
        })
    {
        return Err("historical verification lacks passing mandatory checks".into());
    }
    let criteria = verification["specification"]["criterion_ids"]
        .as_array()
        .ok_or("missing criteria")?;
    let assessed = verification["review"]["criteria"]
        .as_array()
        .ok_or("missing assessments")?;
    let ids = criteria
        .iter()
        .map(Value::as_str)
        .collect::<Option<std::collections::BTreeSet<_>>>()
        .ok_or("invalid required criterion IDs")?;
    let covered = assessed
        .iter()
        .map(|item| {
            (item["status"] == "pass")
                .then(|| item["criterion_id"].as_str())
                .flatten()
        })
        .collect::<Option<std::collections::BTreeSet<_>>>()
        .ok_or("invalid criterion assessments")?;
    if ids.is_empty()
        || ids != covered
        || ids.len() != criteria.len()
        || covered.len() != assessed.len()
    {
        return Err("historical verification lacks passing criterion coverage".into());
    }
    Ok(candidate)
}

pub fn numbers(root: &Path) -> Result<Vec<u32>> {
    let path = root.join("attempts");
    if !path.try_exists()? {
        return Ok(vec![0]);
    }
    if path.canonicalize()? != path {
        return Err("historical Attempt path is not regular".into());
    }
    let mut list = vec![0];
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let number = entry
            .file_name()
            .to_str()
            .and_then(|name| name.parse::<u32>().ok())
            .ok_or("invalid historical Attempt number")?;
        if number == 0
            || !entry.file_type()?.is_dir()
            || entry.file_name() != format!("{number:06}").as_str()
        {
            return Err("invalid historical Attempt directory".into());
        }
        list.push(number);
    }
    list.sort_unstable();
    if list
        .iter()
        .enumerate()
        .any(|(index, number)| index != *number as usize)
    {
        return Err("historical Attempt history has gaps".into());
    }
    Ok(list)
}

pub fn select(root: &Path, number: Option<u32>) -> Result<(u32, PathBuf)> {
    let numbers = numbers(root)?;
    let number = number.unwrap_or(*numbers.last().expect("initial Attempt"));
    if !numbers.contains(&number) {
        return Err("historical Attempt does not exist".into());
    }
    Ok((number, continuation::attempt_path(root, number)))
}

pub fn view(root: &Path, id: Uuid, number: Option<u32>) -> Result<Value> {
    let (number, directory) = select(root, number)?;
    let mut result = json!({
        "version":1, "source":"saved", "submission":{"run_id":id,"runs_root":root.parent()},
        "state": null, "run": null, "attempt_number": number, "stages": {},
        "stage_errors": {}, "artifacts": {}, "package_available": false,
    });
    if let Err(error) = populate(root, &directory, id, number, &mut result) {
        result["run_error"] = json!(error.to_string());
    }
    Ok(result)
}

fn populate(
    root: &Path,
    directory: &Path,
    id: Uuid,
    number: u32,
    result: &mut Value,
) -> Result<()> {
    let original = read_artifact(root, "contract.json")?;
    let raw = read_artifact(directory, "contract.json")?;
    if serde_json::from_str::<Value>(&original)? != serde_json::from_str::<Value>(&raw)? {
        return Err("historical Attempt changed the frozen contract".into());
    }
    let contract: Contract = serde_json::from_str(&raw)?;
    let intent = &contract.intent;
    if contract.run_id != id
        || intent.artifact.run_id != id
        || contract.verification["base_sha"] != json!(contract.base_sha)
        || intent.artifact.size_bytes != intent.markdown.len()
        || intent.artifact.sha256 != digest(intent.markdown.as_bytes())
        || read_artifact(directory, "intent.md")? != intent.markdown
    {
        return Err("historical contract or intent does not match this Run".into());
    }
    result["title"] = json!(
        intent
            .markdown
            .lines()
            .find(|line| !line.trim().is_empty())
            .unwrap_or("Untitled request")
            .trim()
            .trim_start_matches(['#', ' '])
            .chars()
            .take(200)
            .collect::<String>()
    );
    if let Some(url) = &intent.source_url {
        if crate::github::selector(url).is_ok() {
            result["source_url"] = json!(url);
            result["source_ref"] = json!(intent.source_ref);
        }
    }
    let saved = snapshot(directory, id)?;
    let attempt: Option<Attempt> = if directory.join("attempt.json").try_exists()? {
        Some(serde_json::from_str(&read_artifact(
            directory,
            "attempt.json",
        )?)?)
    } else {
        None
    };
    if let Some(attempt) = &attempt {
        if attempt.run_id() != id || (number == 0 && attempt.start_sha() != &contract.base_sha) {
            return Err("historical Attempt attribution does not match".into());
        }
    }
    if let Some(verification) = &saved.verification {
        result["candidate_sha"] = json!(validate_verification(
            &contract,
            attempt.as_ref(),
            verification
        )?);
    }
    let terminal = matches!(
        saved.lifecycle,
        Lifecycle::Completed | Lifecycle::Failed | Lifecycle::Cancelled
    );
    result["run"] = json!(saved);
    result["attempt_id"] = json!(attempt.as_ref().map(Attempt::id));
    for name in ["report.md", "evidence.json"] {
        if terminal && read_artifact(directory, name).is_ok() {
            result["artifacts"][name] = json!(directory.join(name));
        }
    }
    result["package_available"] = json!(
        result["artifacts"]
            .as_object()
            .is_some_and(|files| files.len() == 2)
    );
    result["has_specification"] = json!(specification(directory).is_ok());
    Ok(())
}

fn specification(directory: &Path) -> Result<String> {
    let name = if directory.join("frozen-spec.md").try_exists()? {
        "frozen-spec.md"
    } else {
        "design/spec.md"
    };
    read_artifact(directory, name)
}

pub fn artifact(root: &Path, id: Uuid, number: Option<u32>, name: &str) -> Result<Value> {
    let (_, directory) = select(root, number)?;
    let view = view(root, id, number)?;
    if !matches!(
        view["run"]["lifecycle"].as_str(),
        Some("COMPLETED" | "FAILED" | "CANCELLED")
    ) {
        return Err("historical terminal artifacts are unavailable".into());
    }
    let content = match name {
        "report.md" | "evidence.json" => read_artifact(&directory, name)?,
        "spec.md" => specification(&directory)?,
        _ => return Err("unsupported historical artifact".into()),
    };
    Ok(json!({"name": name, "content": content}))
}

pub fn locate(root: &Path, id: Uuid) -> Result<PathBuf> {
    let directory = root.join(id.to_string());
    let metadata = fs::symlink_metadata(&directory)?;
    if !metadata.is_dir() || !directory.join("run.json").is_file() {
        return Err("historical Run does not exist".into());
    }
    Ok(directory)
}

pub fn ids(root: &Path) -> Result<Vec<Uuid>> {
    let entries = match fs::read_dir(root) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(error.into()),
    };
    let mut ids = Vec::new();
    for entry in entries {
        let entry = entry?;
        if let Some(id) = entry
            .file_name()
            .to_str()
            .and_then(|name| Uuid::parse_str(name).ok())
        {
            if entry.file_type()?.is_dir() && entry.path().join("run.json").is_file() {
                ids.push(id);
            }
        }
    }
    ids.sort_unstable();
    Ok(ids)
}

pub fn default_root() -> Option<PathBuf> {
    let home = PathBuf::from(std::env::var_os("HOME")?);
    let current = home.join(".harborist");
    let previous = home.join(".shipyard");
    Some(
        if !current.exists() && previous.is_dir() {
            previous
        } else {
            current
        }
        .join("runs"),
    )
}
