//! Explicit fresh rework Attempts with immutable predecessor evidence.

use crate::{
    Result,
    foreground::{self, Rework},
    git_text,
    record::{Terminal, read_artifact},
    store,
};
use harborist_verify::workflow::Attempt;
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

pub fn latest(root: &Path) -> Result<u32> {
    let entries = match fs::read_dir(root.join("attempts")) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(0),
        Err(error) => return Err(error.into()),
    };
    let mut number = 0;
    for entry in entries {
        let entry = entry?;
        let name = entry.file_name();
        if let Some(index) = name
            .to_str()
            .filter(|name| name.len() == 6)
            .and_then(|name| name.parse::<u32>().ok())
        {
            if entry.file_type()?.is_dir() && entry.path().join("continuation.json").is_file() {
                number = number.max(index);
            }
        }
    }
    Ok(number)
}

pub fn execute(args: &[OsString]) -> Result<()> {
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
                "expected rework RUN_DIR EXPECTED_ATTEMPT FEEDBACK [ADDITIONAL_SECONDS]".into(),
            );
        }
    };
    let expected = Uuid::parse_str(expected.to_str().ok_or("expected an Attempt UUID")?)?;
    let feedback = feedback.to_str().ok_or("feedback must be UTF-8")?;
    if feedback.chars().count() > 32768 || extra > u32::MAX as u64 {
        return Err("feedback or additional time exceeds the supported limit".into());
    }
    let capture = store::load(Path::new(directory))?;
    let root = &capture.directory;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(root.join("continuation.lock"))?;
    // This descriptor serializes successor admission and execution for the Run.
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    crate::retirement::cancelled(&crate::retirement::path(root))?;
    let number = latest(root)?;
    let previous = attempt_path(root, number);
    let terminal = Terminal::load(&previous, capture.contract.run_id)?;
    if terminal.attempt.id() != expected || terminal.base_sha != capture.contract.base_sha {
        return Err("rework predecessor does not match the latest Attempt".into());
    }
    if !matches!(
        terminal.outcome.as_str(),
        "TEST_FAILED" | "CHANGES_REQUIRED"
    ) {
        return Err("rework requires TEST_FAILED or CHANGES_REQUIRED".into());
    }
    let candidate = terminal
        .candidate
        .ok_or("rework requires a previous candidate")?;
    let reference = if number == 0 {
        store::candidate_ref(capture.contract.run_id)
    } else {
        store::attempt_candidate_ref(capture.contract.run_id, expected)
    };
    if terminal.candidate_ref.as_deref() != Some(reference.as_str())
        || git_text(
            &capture.contract.repository,
            &["rev-parse", "--verify", &reference],
        )? != candidate.as_str()
    {
        return Err("previous Attempt candidate ref does not match".into());
    }
    let spec = read_artifact(&previous, "design/spec.md")?;
    if terminal.spec_sha256.as_deref() != Some(store::digest(spec.as_bytes()).as_str()) {
        return Err("previous Attempt specification digest does not match".into());
    }
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
        return Err("insufficient rework budget; supply an explicit additional time grant".into());
    }
    let context = serde_json::to_string_pretty(&json!({
        "previous_attempt": expected, "previous_candidate": candidate,
        "previous_outcome": terminal.outcome, "feedback": feedback,
        "plan": read_artifact(&previous, "build/plan.md").or_else(|_| read_artifact(&previous, "plan/plan.md"))?,
        "test_evidence": serde_json::from_str::<serde_json::Value>(&read_artifact(&previous, "test/evidence.json")?)?,
        "review": read_artifact(&previous, "review/review.md").ok(),
    }))?;
    let directory = attempt_path(root, number + 1);
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
            "action": "rework", "previous_attempt": expected, "attempt": attempt,
            "spec_sha256": terminal.spec_sha256, "spent_seconds": spent, "granted_seconds": granted,
            "context": serde_json::from_str::<serde_json::Value>(&context)?,
        }))?,
    )?;
    File::open(&directory)?.sync_all()?;
    File::open(
        directory
            .parent()
            .ok_or("missing Attempt directory parent")?,
    )?
    .sync_all()?;
    let result = foreground::execute_attempt(
        capture,
        directory,
        attempt,
        Some(Rework {
            context,
            specification: spec,
            spent_seconds: spent,
            granted_seconds: granted,
        }),
    )?;
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
