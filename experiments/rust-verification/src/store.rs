//! Filesystem capture and exclusive admission for a fresh Rust Run.

use crate::{Config, Result, commit, git, git_text};
use harborist_verify::workflow::{Attempt, Sha};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    ffi::OsString,
    fs::{self, File},
    io::{self, Write},
    path::{Path, PathBuf},
};
use uuid::Uuid;

const VERSION: u32 = 1;
pub const TOTAL_SECONDS: u64 = 1800;
pub const VERIFICATION_RESERVE_SECONDS: u64 = 300;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Contract {
    version: u32,
    pub run_id: Uuid,
    pub repository: PathBuf,
    pub base_sha: Sha,
    intent_sha256: String,
    pub source_sha256: String,
    total_seconds: u64,
    verification_reserve_seconds: u64,
}

pub struct Captured {
    pub directory: PathBuf,
    pub contract: Contract,
    pub config: Config,
    pub intent: String,
}

fn digest(content: &[u8]) -> String {
    format!("{:x}", Sha256::digest(content))
}

pub fn write_new(path: &Path, content: &[u8]) -> io::Result<()> {
    let mut file = File::create_new(path)?;
    file.write_all(content)?;
    file.sync_all()
}

fn repository(path: &Path) -> Result<PathBuf> {
    Ok(PathBuf::from(git_text(path, &["rev-parse", "--show-toplevel"])?).canonicalize()?)
}

fn validate_base(repo: &Path, sha: &Sha) -> Result<()> {
    if git_text(repo, &["rev-parse", &format!("{sha}^{{commit}}")])? != sha.as_str() {
        return Err("base must identify the exact commit".into());
    }
    Ok(())
}

pub fn capture(args: &[OsString]) -> Result<Captured> {
    let [repo, base, intent_path, directory] = args else {
        return Err("expected REPO BASE_SHA INTENT_FILE NEW_RUN_DIR".into());
    };
    let repo = repository(Path::new(repo))?;
    let directory = Path::new(directory);
    let parent = directory
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()?;
    let directory = parent.join(directory.file_name().ok_or("missing Run directory name")?);
    if directory.starts_with(&repo) {
        return Err("Run directory must be outside the source checkout".into());
    }
    let base_sha = commit(base)?;
    validate_base(&repo, &base_sha)?;
    let frozen = git(
        &repo,
        &[
            "show".as_ref(),
            format!("{base_sha}:harborist.yaml").as_ref(),
        ],
    )?;
    let config = Config::parse(&frozen)?;
    let intent = fs::read_to_string(intent_path)?;
    if intent.trim().is_empty() {
        return Err("intent must contain text".into());
    }
    let contract = Contract {
        version: VERSION,
        run_id: Uuid::new_v4(),
        repository: repo,
        base_sha,
        intent_sha256: digest(intent.as_bytes()),
        source_sha256: digest(&frozen),
        total_seconds: TOTAL_SECONDS,
        verification_reserve_seconds: VERIFICATION_RESERVE_SECONDS,
    };
    fs::create_dir(&directory)?;
    write_new(&directory.join("intent.md"), intent.as_bytes())?;
    write_new(&directory.join("harborist.yaml"), &frozen)?;
    // Publish the contract only after its referenced inputs are complete.
    write_new(
        &directory.join(".contract.pending"),
        &serde_json::to_vec_pretty(&contract)?,
    )?;
    fs::rename(
        directory.join(".contract.pending"),
        directory.join("contract.json"),
    )?;
    File::open(&directory)?.sync_all()?;
    File::open(parent)?.sync_all()?;
    Ok(Captured {
        directory,
        contract,
        config,
        intent,
    })
}

pub fn load(path: &Path) -> Result<Captured> {
    let directory = path.canonicalize()?;
    let contract: Contract = serde_json::from_slice(&fs::read(directory.join("contract.json"))?)?;
    if contract.version != VERSION
        || contract.total_seconds != TOTAL_SECONDS
        || contract.verification_reserve_seconds != VERIFICATION_RESERVE_SECONDS
    {
        return Err("unsupported Run contract version or budget".into());
    }
    let repo = repository(&contract.repository)?;
    if repo != contract.repository || directory.starts_with(&repo) {
        return Err("Run checkout or directory does not match the saved context".into());
    }
    validate_base(&repo, &contract.base_sha)?;
    let intent = fs::read_to_string(directory.join("intent.md"))?;
    let frozen = fs::read(directory.join("harborist.yaml"))?;
    if digest(intent.as_bytes()) != contract.intent_sha256
        || digest(&frozen) != contract.source_sha256
    {
        return Err("captured input digest mismatch".into());
    }
    let config = Config::parse(&frozen)?;
    Ok(Captured {
        directory,
        contract,
        config,
        intent,
    })
}

pub fn admit(capture: &Captured) -> Result<Attempt> {
    let attempt = Attempt::new(capture.contract.run_id, capture.contract.base_sha.clone());
    let written = write_new(
        &capture.directory.join("attempt.json"),
        &serde_json::to_vec_pretty(&attempt)?,
    );
    if written
        .as_ref()
        .is_err_and(|error| error.kind() == io::ErrorKind::AlreadyExists)
    {
        return Err("Run already admitted; existing execution records are retained".into());
    }
    written?;
    File::open(&capture.directory)?.sync_all()?;
    Ok(attempt)
}
