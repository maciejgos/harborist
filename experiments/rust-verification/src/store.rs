//! Filesystem capture and exclusive admission for a fresh Rust Run.

use crate::{Config, Result, commit, git_text, settings::Execution};
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

pub const VERSION: u32 = 1;
pub const TOTAL_SECONDS: u64 = 1800;
pub const VERIFICATION_RESERVE_SECONDS: u64 = 300;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Contract {
    pub version: u32,
    pub run_id: Uuid,
    pub repository: PathBuf,
    pub base_sha: Sha,
    pub intent_sha256: String,
    pub source_ref: Option<String>,
    pub source_url: Option<String>,
    pub source_sha256: String,
    pub total_seconds: u64,
    pub verification_reserve_seconds: u64,
    pub execution: Option<Execution>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ExecutionContext {
    pub version: u32,
    pub run_id: Uuid,
    pub repository: PathBuf,
    pub runs_root: PathBuf,
}

pub struct Captured {
    pub directory: PathBuf,
    pub contract: Contract,
    pub config: Config,
    pub intent: String,
}

impl Captured {
    pub fn public_contract(&self) -> serde_json::Value {
        use serde_json::json;

        let contract = &self.contract;
        // Derive a stable identity even for captures that predate public contract output.
        let mut hash = Sha256::new();
        hash.update(b"harborist:intent:");
        hash.update(contract.run_id.as_bytes());
        hash.update(contract.intent_sha256.as_bytes());
        let hash = hash.finalize();
        let mut bytes = [0; 16];
        bytes.copy_from_slice(&hash[..16]);
        let artifact_id = uuid::Builder::from_custom_bytes(bytes).into_uuid();
        let mut intent = json!({
            "source_ref": contract.source_ref.as_deref().unwrap_or("file:intent.md"),
            "markdown": self.intent,
            "artifact": {
                "artifact_id": artifact_id,
                "run_id": contract.run_id,
                "kind": "intent",
                "produced_by": "intake",
                "sha256": contract.intent_sha256,
                "size_bytes": self.intent.len(),
                "attempt_id": null,
            },
        });
        if let Some(url) = &contract.source_url {
            intent["source_url"] = json!(url);
        }
        json!({
            "run_id": contract.run_id,
            "intent": intent,
            "base_sha": contract.base_sha,
            "verification": {
                "base_sha": contract.base_sha,
                "source_sha256": contract.source_sha256,
                "config": self.config,
            },
            "execution": contract.execution.as_ref().map(|execution| execution.public_snapshot(
                contract.total_seconds,
                contract.verification_reserve_seconds,
            )),
        })
    }
}

pub fn attempt_candidate_ref(run_id: Uuid, attempt_id: Uuid) -> String {
    format!("refs/harborist/rust-runs/{run_id}/attempts/{attempt_id}/candidate")
}

pub fn candidate_ref(run_id: Uuid) -> String {
    format!("refs/harborist/rust-runs/{run_id}/candidate")
}

pub fn digest(content: &[u8]) -> String {
    format!("{:x}", Sha256::digest(content))
}

pub fn write_new(path: &Path, content: &[u8]) -> io::Result<()> {
    let mut file = File::create_new(path)?;
    file.write_all(content)?;
    file.sync_all()
}

pub fn repository(path: &Path) -> Result<PathBuf> {
    Ok(PathBuf::from(git_text(path, &["rev-parse", "--show-toplevel"])?).canonicalize()?)
}

fn validate_base(repo: &Path, sha: &Sha) -> Result<()> {
    if git_text(repo, &["rev-parse", &format!("{sha}^{{commit}}")])? != sha.as_str() {
        return Err("base must identify the exact commit".into());
    }
    Ok(())
}

pub fn capture(args: &[OsString]) -> Result<Captured> {
    let (repo, base, intent_path, directory, settings) = match args {
        [repo, base, intent, directory] => (repo, base, intent, directory, None),
        [repo, base, intent, directory, flag, settings] if flag == "--settings" => {
            (repo, base, intent, directory, Some(Path::new(settings)))
        }
        _ => return Err("expected REPO BASE_SHA INTENT_FILE NEW_RUN_DIR [--settings FILE]".into()),
    };
    capture_to(Capture {
        repository: Path::new(repo),
        base_sha: commit(base)?,
        source: intent_path,
        directory: Path::new(directory),
        settings,
        run_id: Uuid::new_v4(),
        total_seconds: TOTAL_SECONDS,
        verification_reserve_seconds: VERIFICATION_RESERVE_SECONDS,
    })
}

pub struct Capture<'a> {
    pub repository: &'a Path,
    pub base_sha: Sha,
    pub source: &'a std::ffi::OsStr,
    pub directory: &'a Path,
    pub settings: Option<&'a Path>,
    pub run_id: Uuid,
    pub total_seconds: u64,
    pub verification_reserve_seconds: u64,
}

pub fn validate_budget(total: u64, reserve: u64) -> Result<()> {
    if reserve == 0 || reserve >= total || total > u32::MAX as u64 {
        return Err("total time must exceed a positive verification reserve".into());
    }
    Ok(())
}

pub fn capture_to(request: Capture<'_>) -> Result<Captured> {
    let Capture {
        repository: path,
        base_sha,
        source,
        directory,
        settings,
        run_id,
        total_seconds,
        verification_reserve_seconds,
    } = request;
    validate_budget(total_seconds, verification_reserve_seconds)?;
    let repo = repository(path)?;
    let directory = new_directory(directory, &repo)?;
    validate_base(&repo, &base_sha)?;
    let frozen = crate::verification_source(&repo, &base_sha)?;
    let config = Config::parse(&frozen)?;
    let (intent, source_ref, source_url) = match source.to_str() {
        Some(text) if text.starts_with("github:") || text.starts_with("https://") => {
            let selector = crate::github::selector(text)?;
            let (intent, url) = crate::github::capture(&repo, &selector)?;
            (intent, Some(selector), Some(url))
        }
        text => {
            let path = text
                .and_then(|text| text.strip_prefix("file:"))
                .map(Path::new)
                .unwrap_or_else(|| Path::new(source))
                .canonicalize()?;
            (
                fs::read_to_string(&path)?,
                Some(format!("file:{}", path.display())),
                None,
            )
        }
    };
    if intent.trim().is_empty() {
        return Err("intent must contain text".into());
    }
    let execution = Execution::load(&repo, settings)?;
    let contract = Contract {
        version: VERSION,
        run_id,
        repository: repo,
        base_sha,
        intent_sha256: digest(intent.as_bytes()),
        source_ref,
        source_url,
        source_sha256: digest(&frozen),
        total_seconds,
        verification_reserve_seconds,
        execution,
    };
    save(&directory, &contract, &intent, &frozen)?;
    Ok(Captured {
        directory,
        contract,
        config,
        intent,
    })
}

pub fn new_directory(directory: &Path, repo: &Path) -> Result<PathBuf> {
    let parent = directory
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()?;
    let directory = parent.join(directory.file_name().ok_or("missing Run directory name")?);
    if directory.starts_with(repo) {
        return Err("Run directory must be outside the source checkout".into());
    }
    Ok(directory)
}

pub fn save(directory: &Path, contract: &Contract, intent: &str, frozen: &[u8]) -> Result<()> {
    fs::create_dir(directory)?;
    write_new(&directory.join("intent.md"), intent.as_bytes())?;
    write_new(&directory.join("harborist.yaml"), frozen)?;
    let context = ExecutionContext {
        version: 1,
        run_id: contract.run_id,
        repository: contract.repository.clone(),
        runs_root: directory.parent().ok_or("missing Run parent")?.to_owned(),
    };
    write_new(
        &directory.join("execution-context.json"),
        &serde_json::to_vec_pretty(&context)?,
    )?;
    // Publish the contract only after its referenced inputs are complete.
    write_new(
        &directory.join(".contract.pending"),
        &serde_json::to_vec_pretty(contract)?,
    )?;
    fs::rename(
        directory.join(".contract.pending"),
        directory.join("contract.json"),
    )?;
    File::open(directory)?.sync_all()?;
    File::open(directory.parent().ok_or("missing Run parent")?)?.sync_all()?;
    Ok(())
}

pub fn load(path: &Path) -> Result<Captured> {
    let capture = load_frozen(path)?;
    let contract = &capture.contract;
    let directory = &capture.directory;
    let repo = repository(&contract.repository)?;
    if repo != contract.repository || directory.starts_with(&repo) {
        return Err("Run checkout or directory does not match the saved context".into());
    }
    validate_base(&repo, &contract.base_sha)?;
    Ok(capture)
}

pub fn load_frozen(path: &Path) -> Result<Captured> {
    let directory = path.canonicalize()?;
    let contract: Contract = serde_json::from_slice(&fs::read(directory.join("contract.json"))?)?;
    if contract.version != VERSION {
        return Err("unsupported Run contract version".into());
    }
    validate_budget(
        contract.total_seconds,
        contract.verification_reserve_seconds,
    )?;
    let intent = fs::read_to_string(directory.join("intent.md"))?;
    let frozen = fs::read(directory.join("harborist.yaml"))?;
    if digest(intent.as_bytes()) != contract.intent_sha256
        || digest(&frozen) != contract.source_sha256
    {
        return Err("captured input digest mismatch".into());
    }
    if let Some(execution) = &contract.execution {
        execution.validate()?;
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
    crate::retirement::cancelled(&crate::retirement::path(&capture.directory))?;
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
