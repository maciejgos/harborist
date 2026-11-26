//! Explicit fresh rework Attempts with immutable predecessor evidence.

use crate::{
    Result,
    foreground::{self, Rework},
    git_text,
    record::{Terminal, read_artifact},
    store,
};
use harborist_verify::workflow::{Attempt, Sha};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
};
use uuid::Uuid;

pub fn attempt_path(root: &Path, number: u32) -> PathBuf {
    if number == 0 {
        root.to_owned()
    } else {
        root.join("attempts").join(format!("{number:06}"))
    }
}

pub fn numbers(root: &Path) -> Result<Vec<u32>> {
    let entries = match fs::read_dir(root.join("attempts")) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(vec![0]),
        Err(error) => return Err(error.into()),
    };
    let mut numbers = vec![0];
    for entry in entries {
        let entry = entry?;
        let name = entry.file_name();
        if let Some(index) = name
            .to_str()
            .filter(|name| name.len() == 6)
            .and_then(|name| name.parse::<u32>().ok())
        {
            if index > 0
                && entry.file_type()?.is_dir()
                && entry.path().join("continuation.json").is_file()
            {
                numbers.push(index);
            }
        }
    }
    numbers.sort_unstable();
    Ok(numbers)
}

pub fn latest(root: &Path) -> Result<u32> {
    Ok(numbers(root)?.last().copied().unwrap_or(0))
}

pub fn selected_ref(run_id: Uuid, attempt_id: Uuid, number: u32) -> String {
    if number == 0 {
        store::candidate_ref(run_id)
    } else {
        store::attempt_candidate_ref(run_id, attempt_id)
    }
}

pub fn lock(root: &Path) -> Result<File> {
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(root.join("continuation.lock"))?;
    // Keep the lock until the caller finishes selecting or executing an Attempt.
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(file)
}

#[derive(Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub request_id: Uuid,
    action: String,
    expected_attempt_id: Uuid,
    #[serde(default)]
    feedback: String,
    #[serde(default)]
    additional_seconds: u64,
}

struct Prepared {
    directory: PathBuf,
    candidate: Sha,
    rework: Rework,
}

#[derive(Deserialize, Serialize)]
pub struct Interruption {
    pub attempt: Attempt,
    granted_seconds: u64,
}

#[derive(Deserialize)]
struct Admission {
    request_id: Uuid,
    attempt: Attempt,
    granted_seconds: u64,
}

pub fn interruption(directory: &Path) -> Result<Option<Interruption>> {
    match fs::read(directory.join("interruption.json")) {
        Ok(raw) => Ok(Some(serde_json::from_slice(&raw)?)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

pub fn record_worker_loss(root: &Path, run_id: Uuid, request: Option<&Request>) -> Result<()> {
    let number = latest(root)?;
    let directory = attempt_path(root, number);
    if directory.join("evidence.json").try_exists()? {
        return Ok(());
    }
    let attempt: Attempt = match fs::read(directory.join("attempt.json")) {
        Ok(raw) => serde_json::from_slice(&raw)?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error.into()),
    };
    if attempt.run_id() != run_id {
        return Err("interrupted Attempt belongs to another Run".into());
    }
    let grants = match (number, request) {
        (0, None) => 0,
        (0, Some(_)) | (_, None) => return Ok(()),
        (_, Some(request)) => {
            let admission: Admission =
                serde_json::from_str(&read_artifact(&directory, "continuation.json")?)?;
            if admission.request_id != request.request_id || admission.attempt != attempt {
                return Ok(());
            }
            admission.granted_seconds
        }
    };
    let record = Interruption {
        attempt,
        granted_seconds: grants,
    };
    match store::write_new(
        &directory.join("interruption.json"),
        &serde_json::to_vec(&record)?,
    ) {
        Ok(()) => File::open(&directory)?.sync_all()?,
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => (),
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

#[derive(Deserialize, Serialize)]
struct DesignCheckpoint {
    attempt: Attempt,
    sha256: String,
}

pub fn checkpoint_design(directory: &Path, attempt: &Attempt, sha256: &str) -> Result<()> {
    let record = DesignCheckpoint {
        attempt: attempt.clone(),
        sha256: sha256.to_owned(),
    };
    store::write_new(
        &directory.join("design-checkpoint.json"),
        &serde_json::to_vec(&record)?,
    )?;
    File::open(directory)?.sync_all()?;
    Ok(())
}

fn worker_loss(
    capture: &store::Captured,
    directory: &Path,
    lost: Interruption,
    extra: u64,
) -> Result<Terminal> {
    if extra == 0 {
        return Err("interrupted execution requires an explicit additional time grant".into());
    }
    let spec_sha256 = match fs::read(directory.join("design-checkpoint.json")) {
        Ok(raw) => {
            let saved: DesignCheckpoint = serde_json::from_slice(&raw)?;
            if saved.attempt != lost.attempt {
                return Err("DESIGN checkpoint belongs to another Attempt".into());
            }
            Some(saved.sha256)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => None,
        Err(error) => return Err(error.into()),
    };
    let spent = capture
        .contract
        .total_seconds
        .checked_add(lost.granted_seconds)
        .ok_or("time budget overflow")?;
    Ok(Terminal {
        run_id: lost.attempt.run_id(),
        base_sha: capture.contract.base_sha.clone(),
        start_sha: Some(lost.attempt.start_sha().clone()),
        attempt: lost.attempt,
        spec_sha256,
        spent_seconds: Some(spent),
        granted_seconds: lost.granted_seconds,
        candidate_ref: None,
        candidate: None,
        outcome: "FAILED".to_owned(),
        error: None,
        failure_reason: Some("EXECUTION_FAILED".to_owned()),
        receipts: Vec::new(),
        verification_inputs: None,
    })
}

pub fn validate(capture: &store::Captured, request: &Request) -> Result<()> {
    prepare(capture, request).map(|_| ())
}

fn prepare(capture: &store::Captured, request: &Request) -> Result<Prepared> {
    if !matches!(request.action.as_str(), "rework" | "recover") {
        return Err("unsupported continuation action".into());
    }
    let expected = request.expected_attempt_id;
    let feedback = &request.feedback;
    let extra = request.additional_seconds;
    if feedback.chars().count() > 32768 || extra > u32::MAX as u64 {
        return Err("feedback or additional time exceeds the supported limit".into());
    }
    let root = &capture.directory;
    crate::retirement::cancelled(&crate::retirement::path(root))?;
    let number = latest(root)?;
    let previous = attempt_path(root, number);
    let terminal = if !previous.join("evidence.json").try_exists()? && request.action == "recover" {
        let lost = interruption(&previous)?
            .ok_or("no terminal evidence or recorded worker interruption")?;
        worker_loss(capture, &previous, lost, extra)?
    } else {
        Terminal::load(&previous, capture.contract.run_id)?
    };
    if terminal.run_id != capture.contract.run_id
        || terminal.attempt.id() != expected
        || terminal.base_sha != capture.contract.base_sha
    {
        return Err("continuation predecessor does not match the latest Attempt".into());
    }
    if request.action == "rework" {
        if !matches!(
            terminal.outcome.as_str(),
            "TEST_FAILED" | "CHANGES_REQUIRED"
        ) || terminal.candidate.is_none()
        {
            return Err(
                "rework requires TEST_FAILED or CHANGES_REQUIRED and a previous candidate".into(),
            );
        }
    } else if terminal.outcome != "FAILED"
        || !matches!(
            terminal.failure_reason.as_deref(),
            Some(
                "EXECUTION_FAILED"
                    | "INVALID_STAGE_OUTPUT"
                    | "CREDENTIAL_UNAVAILABLE"
                    | "CREDENTIAL_REJECTED"
            )
        )
    {
        return Err("failure is not eligible for explicit recovery".into());
    }
    let candidate = if let Some(candidate) = terminal.candidate {
        let reference = selected_ref(capture.contract.run_id, expected, number);
        if terminal.candidate_ref.as_deref() != Some(reference.as_str())
            || git_text(
                &capture.contract.repository,
                &["rev-parse", "--verify", &reference],
            )? != candidate.as_str()
        {
            return Err("previous Attempt candidate ref does not match".into());
        }
        candidate
    } else {
        terminal.attempt.start_sha().clone()
    };
    let spec = if let Some(expected) = terminal.spec_sha256 {
        let spec = read_artifact(&previous, "design/spec.md")?;
        if expected != store::digest(spec.as_bytes()) {
            return Err("previous Attempt specification digest does not match".into());
        }
        Some(spec)
    } else if request.action == "recover" {
        None
    } else {
        return Err("rework requires a frozen specification".into());
    };
    let spent = terminal
        .spent_seconds
        .ok_or("previous Attempt has no recorded spending")?;
    let granted = terminal
        .granted_seconds
        .checked_add(extra)
        .ok_or("time grant overflow")?;
    let total = capture
        .contract
        .total_seconds
        .checked_add(granted)
        .ok_or("time budget overflow")?;
    if total > u32::MAX as u64
        || total.saturating_sub(spent) <= capture.contract.verification_reserve_seconds
    {
        return Err(
            "insufficient continuation budget; supply an explicit additional time grant".into(),
        );
    }
    let context = serde_json::to_string_pretty(&json!({
        "previous_attempt": expected, "previous_candidate": candidate,
        "previous_outcome": terminal.outcome, "feedback": feedback,
        "plan": read_artifact(&previous, "build/plan.md").or_else(|_| read_artifact(&previous, "plan/plan.md")).ok(),
        "test_evidence": read_artifact(&previous, "test/evidence.json").ok().map(|raw| serde_json::from_str::<serde_json::Value>(&raw)).transpose()?,
        "review": read_artifact(&previous, "review/review.md").ok(),
    }))?;
    let directory = attempt_path(root, number + 1);
    Ok(Prepared {
        directory,
        candidate,
        rework: Rework {
            context,
            specification: spec,
            spent_seconds: spent,
            granted_seconds: granted,
        },
    })
}

pub fn run(capture: store::Captured, request: &Request) -> Result<serde_json::Value> {
    let _lock = lock(&capture.directory)?;
    let Prepared {
        directory,
        candidate,
        rework,
    } = prepare(&capture, request)?;
    fs::create_dir_all(
        directory
            .parent()
            .ok_or("missing Attempt directory parent")?,
    )?;
    fs::create_dir(&directory)?;
    let attempt = Attempt::new(capture.contract.run_id, candidate);
    store::write_new(
        &directory.join("attempt.json"),
        &serde_json::to_vec(&attempt)?,
    )?;
    store::write_new(
        &directory.join("continuation.json"),
        &serde_json::to_vec_pretty(&json!({
            "action": request.action, "previous_attempt": request.expected_attempt_id, "request_id": request.request_id, "attempt": attempt,
            "spec_sha256": rework.specification.as_ref().map(|spec| store::digest(spec.as_bytes())), "spent_seconds": rework.spent_seconds, "granted_seconds": rework.granted_seconds,
            "context": serde_json::from_str::<serde_json::Value>(&rework.context)?,
        }))?,
    )?;
    File::open(&directory)?.sync_all()?;
    File::open(
        directory
            .parent()
            .ok_or("missing Attempt directory parent")?,
    )?
    .sync_all()?;
    foreground::execute_attempt(capture, directory, attempt, Some(rework))
}

pub fn execute(action: &str, args: &[OsString]) -> Result<()> {
    let (directory, expected, feedback, extra) = match args {
        [directory, expected, feedback] => (directory, expected, feedback, 0),
        [directory, expected, feedback, extra] => (
            directory,
            expected,
            feedback,
            extra.to_str().ok_or("invalid time grant")?.parse::<u64>()?,
        ),
        _ => {
            return Err(
                "expected rework or recover RUN_DIR EXPECTED_ATTEMPT FEEDBACK [ADDITIONAL_SECONDS]"
                    .into(),
            );
        }
    };
    let request = Request {
        request_id: Uuid::new_v4(),
        action: action.to_owned(),
        expected_attempt_id: Uuid::parse_str(expected.to_str().ok_or("expected an Attempt UUID")?)?,
        feedback: feedback
            .to_str()
            .ok_or("feedback must be UTF-8")?
            .to_owned(),
        additional_seconds: extra,
    };
    let result = run(store::load(Path::new(directory))?, &request)?;
    println!("{result}");
    if result["outcome"] != "VERIFIED" {
        return Err(result["error"]
            .as_str()
            .or_else(|| result["outcome"].as_str())
            .unwrap_or("rework failed")
            .to_owned()
            .into());
    }
    Ok(())
}
