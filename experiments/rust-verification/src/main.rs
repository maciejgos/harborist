mod process;

use serde::{Deserialize, Deserializer, Serialize, de};
use serde_yaml::Value;
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::error::Error;
use std::ffi::OsStr;
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Config {
    version: Value,
    checks: Vec<Check>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Check {
    #[serde(deserialize_with = "strict_string")]
    id: String,
    #[serde(deserialize_with = "strict_string")]
    command: String,
}

fn strict_string<'de, D: Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<String, D::Error> {
    match Value::deserialize(deserializer)? {
        Value::String(value) => Ok(value),
        _ => Err(de::Error::custom("expected a YAML string")),
    }
}

impl Config {
    fn parse(bytes: &[u8]) -> Result<Self> {
        let config: Self = serde_yaml::from_slice(bytes)?;
        if config.version.as_u64() != Some(1) || config.checks.is_empty() {
            return Err("expected version 1 and at least one check".into());
        }
        let mut ids = HashSet::new();
        for check in &config.checks {
            if check.id.is_empty() || check.id.trim() != check.id || !ids.insert(&check.id) {
                return Err("expected a unique, nonempty, trimmed check ID".into());
            }
            if check.command.trim().is_empty() {
                return Err("expected a nonempty command".into());
            }
        }
        Ok(config)
    }
}

#[derive(Serialize)]
struct CheckResult {
    id: String,
    command: String,
    returncode: Option<i32>,
    timed_out: bool,
    error: Option<String>,
    stdout_path: PathBuf,
    stderr_path: PathBuf,
    stdout_truncated: bool,
    stderr_truncated: bool,
}

#[derive(Serialize)]
struct Evidence {
    candidate: String,
    source_sha256: String,
    passed: bool,
    checks: Vec<CheckResult>,
}

fn run_checks(config: Config, workspace: &Path, logs: &Path) -> Result<Vec<CheckResult>> {
    let deadline = Instant::now() + Duration::from_secs(15);
    let workspace = workspace.canonicalize()?;
    fs::create_dir(logs)?;
    let logs = logs.canonicalize()?;
    config
        .checks
        .into_iter()
        .enumerate()
        .map(|(index, check)| {
            let mut result = CheckResult {
                id: check.id,
                command: check.command,
                returncode: None,
                timed_out: false,
                error: None,
                stdout_path: logs.join(format!("{index:04}.stdout.log")),
                stderr_path: logs.join(format!("{index:04}.stderr.log")),
                stdout_truncated: false,
                stderr_truncated: false,
            };
            let mut stdout = File::create_new(&result.stdout_path)?;
            let mut stderr = File::create_new(&result.stderr_path)?;
            let allowance = deadline
                .saturating_duration_since(Instant::now())
                .min(Duration::from_secs(2));
            if allowance.is_zero() {
                result.timed_out = true;
                result.error = Some("Shared TEST deadline exhausted before invocation".into());
            } else {
                match process::capture(&result.command, &workspace, allowance, 65536) {
                    Ok(capture) => {
                        stdout.write_all(&capture.stdout.bytes)?;
                        stderr.write_all(&capture.stderr.bytes)?;
                        result.returncode = Some(capture.returncode);
                        result.timed_out = capture.timed_out;
                        result.stdout_truncated = capture.stdout.truncated;
                        result.stderr_truncated = capture.stderr.truncated;
                    }
                    Err(error) => result.error = Some(error.to_string()),
                }
            }
            Ok(result)
        })
        .collect()
}

fn git(repo: &Path, args: &[&OsStr]) -> Result<Vec<u8>> {
    let output = Command::new("git")
        .arg("-C")
        .arg(repo)
        .args(args)
        .output()?;
    if !output.status.success() {
        return Err(format!("git failed: {}", String::from_utf8_lossy(&output.stderr)).into());
    }
    Ok(output.stdout)
}

fn commit(value: &OsStr) -> Result<&str> {
    let value = value.to_str().ok_or("expected a Git SHA")?;
    if !matches!(value.len(), 40 | 64)
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err("expected a full lowercase Git SHA".into());
    }
    Ok(value)
}

fn execute() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let [repo, base, candidate, workspace, logs] = args.as_slice() else {
        return Err(
            "usage: harborist-verify REPO BASE_SHA CANDIDATE_SHA NEW_CHECKOUT NEW_LOG_DIR".into(),
        );
    };
    let repo = Path::new(repo);
    let base = commit(base)?;
    let candidate = commit(candidate)?;
    let workspace = Path::new(workspace);
    let logs = Path::new(logs);
    // Absolute paths give Git and the verifier the same interpretation of arguments.
    if !workspace.is_absolute() || !logs.is_absolute() {
        return Err("checkout and log paths must be absolute".into());
    }
    let candidate_commit = git(
        repo,
        &[
            "rev-parse".as_ref(),
            format!("{candidate}^{{commit}}").as_ref(),
        ],
    )?;
    if String::from_utf8(candidate_commit)?.trim_end() != candidate {
        return Err("expected the exact candidate commit SHA".into());
    }
    match fs::symlink_metadata(workspace) {
        Ok(_) => return Err("checkout path already exists".into()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.into()),
    }
    let source = git(
        repo,
        &["show".as_ref(), format!("{base}:harborist.yaml").as_ref()],
    )?;
    let config = Config::parse(&source)?;
    git(
        repo,
        &[
            "worktree".as_ref(),
            "add".as_ref(),
            "--detach".as_ref(),
            workspace.as_os_str(),
            candidate.as_ref(),
        ],
    )?;
    let checks = run_checks(config, workspace, logs);
    let cleanup = git(
        repo,
        &[
            "worktree".as_ref(),
            "remove".as_ref(),
            "--force".as_ref(),
            workspace.as_os_str(),
        ],
    );
    cleanup?;
    let checks = checks?;
    let evidence = Evidence {
        candidate: candidate.to_owned(),
        source_sha256: format!("{:x}", Sha256::digest(source)),
        passed: checks
            .iter()
            .all(|check| check.returncode == Some(0) && !check.timed_out && check.error.is_none()),
        checks,
    };
    serde_json::to_writer(io::stdout().lock(), &evidence)?;
    Ok(())
}

fn main() {
    if let Err(error) = execute() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_block_yaml_and_preserves_command_text() {
        let config =
            Config::parse(b"version: 1\nchecks:\n  - id: lint\n    command: '  true  '\n").unwrap();
        assert_eq!(config.checks[0].command, "  true  ");
    }

    #[test]
    fn rejects_duplicate_ids_and_quoted_versions() {
        assert!(
            Config::parse(
                b"version: 1\nchecks: [{id: lint, command: 'true'}, {id: lint, command: 'true'}]\n"
            )
            .is_err()
        );
        assert!(Config::parse(b"version: '1'\nchecks: [{id: lint, command: 'true'}]\n").is_err());
    }
}
