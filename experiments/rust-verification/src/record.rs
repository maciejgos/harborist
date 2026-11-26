//! Validated, bounded reads of terminal workflow evidence.

use crate::Result;
use harborist_verify::workflow::{Attempt, Outcome, Receipt, Sha, Stage, Workflow};
use serde::{Deserialize, Serialize};
use std::{
    fs::{File, OpenOptions},
    io::Read,
    os::unix::fs::OpenOptionsExt,
    path::Path,
};
use uuid::Uuid;

const LIMIT: u64 = 2 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct VerificationInputs {
    pub spec_sha256: String,
    pub test_sha256: String,
    pub review_sha256: String,
}

#[derive(Deserialize)]
pub struct Terminal {
    pub run_id: Uuid,
    pub base_sha: Sha,
    pub start_sha: Option<Sha>,
    pub spec_sha256: Option<String>,
    pub spent_seconds: Option<u64>,
    #[serde(default)]
    pub granted_seconds: u64,
    pub candidate_ref: Option<String>,
    pub attempt: Attempt,
    pub candidate: Option<Sha>,
    pub outcome: String,
    pub error: Option<String>,
    pub failure_reason: Option<String>,
    pub receipts: Vec<Receipt>,
    pub verification_inputs: Option<VerificationInputs>,
}

impl Terminal {
    pub fn load(directory: &Path, run_id: Uuid) -> Result<Self> {
        let evidence = read_artifact(directory, "evidence.json")?;
        let terminal: Self = serde_json::from_str(&evidence)?;
        if terminal.run_id != run_id
            || terminal.attempt.run_id() != run_id
            || terminal.attempt.start_sha()
                != terminal.start_sha.as_ref().unwrap_or(&terminal.base_sha)
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
            Outcome::Cancelled => "CANCELLED",
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

pub fn open_artifact(directory: &Path, name: &str) -> Result<File> {
    if directory.canonicalize()? != directory {
        return Err("Run directory does not match the recorded path".into());
    }
    let path = directory.join(name);
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
    Ok(file)
}

pub fn read_artifact(directory: &Path, name: &str) -> Result<String> {
    let file = open_artifact(directory, name)?;
    let mut data = Vec::new();
    file.take(LIMIT + 1).read_to_end(&mut data)?;
    if data.len() as u64 > LIMIT {
        return Err("artifact exceeds the 2 MiB viewing limit".into());
    }
    Ok(String::from_utf8(data)?)
}
