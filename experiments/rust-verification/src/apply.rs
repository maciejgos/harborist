//! Validate a packaged candidate and explicitly fast-forward one local branch.

use crate::{
    Evidence, Result, git, git_command, git_text,
    record::{Terminal, read_artifact},
    store::{self, Captured},
};
use harborist_verify::{
    review::{Review, Specification},
    workflow::{Outcome, Sha},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    ffi::{OsStr, OsString},
    fs::{self, File, OpenOptions},
    io::{self, BufRead, BufReader, Write},
    os::{fd::AsRawFd, unix::ffi::OsStrExt},
    path::{Path, PathBuf},
    process::{Child, Stdio},
    time::{Duration, Instant},
};
use uuid::Uuid;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    run_id: Uuid,
    branch: String,
    previous_sha: Sha,
    resulting_sha: Sha,
    operation: Operation,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Operation {
    Advanced,
    ObservedNoop,
}

fn exact_commit(repo: &Path, sha: &Sha) -> Result<()> {
    if git_text(repo, &["cat-file", "-t", sha.as_str()])? != "commit"
        || !git_text(repo, &["for-each-ref", &format!("refs/replace/{sha}")])?.is_empty()
    {
        return Err("expected an original Git commit object".into());
    }
    Ok(())
}

pub fn verified(run: &Captured) -> Result<Sha> {
    crate::retirement::cancelled(&crate::retirement::path(&run.directory))?;
    let contract = &run.contract;
    let terminal = Terminal::load(&run.directory, contract.run_id)?;
    if terminal.outcome != "VERIFIED" || terminal.base_sha != contract.base_sha {
        return Err("application requires a VERIFIED Run for this base".into());
    }
    let attempt: harborist_verify::workflow::Attempt =
        serde_json::from_str(&read_artifact(&run.directory, "attempt.json")?)?;
    if attempt != terminal.attempt {
        return Err("packaged Attempt differs from the execution record".into());
    }
    let candidate = terminal.candidate.ok_or("missing verified candidate")?;
    let repo = &contract.repository;
    exact_commit(repo, &contract.base_sha)?;
    exact_commit(repo, &candidate)?;
    let candidate_ref = store::candidate_ref(contract.run_id);
    if git_text(repo, &["rev-parse", "--verify", &candidate_ref])? != candidate.as_str() {
        return Err("Run-owned candidate ref does not match the verified commit".into());
    }
    git_text(
        repo,
        &[
            "merge-base",
            "--is-ancestor",
            contract.base_sha.as_str(),
            candidate.as_str(),
        ],
    )?;

    let inputs = terminal
        .verification_inputs
        .ok_or("Run lacks digests for application evidence")?;
    let raw = read_artifact(&run.directory, "test/evidence.json")?;
    if store::digest(raw.as_bytes()) != inputs.test_sha256 {
        return Err("TEST evidence digest does not match the verified Run".into());
    }
    let test: Evidence = serde_json::from_str(&raw)?;
    let workspace_error: Value = serde_json::from_str(&raw)?;
    if test.candidate != candidate
        || test.source_sha256 != contract.source_sha256
        || !test.passed
        || workspace_error.get("workspace_error") != Some(&Value::Null)
        || test.checks.len() != run.config.checks.len()
        || !test
            .checks
            .iter()
            .zip(&run.config.checks)
            .all(|(check, expected)| {
                check.id == expected.id
                    && check.command == expected.command
                    && check.returncode == Some(0)
                    && !check.timed_out
                    && check.error.is_none()
            })
    {
        return Err("TEST evidence does not prove every frozen check passed".into());
    }
    let spec = Specification::parse(&read_artifact(&run.directory, "design/spec.md")?)?;
    let raw = read_artifact(&run.directory, "review/final.json")?;
    if spec.sha256() != inputs.spec_sha256 || store::digest(raw.as_bytes()) != inputs.review_sha256
    {
        return Err("specification or REVIEW digest does not match the verified Run".into());
    }
    let envelope: crate::native::Output = serde_json::from_str(&raw)?;
    let review = Review::parse(&envelope.result.to_string())?;
    if review
        .receipt(&attempt.candidate(candidate.clone()), &spec)?
        .outcome
        != Outcome::Succeeded
    {
        return Err("REVIEW evidence does not prove every criterion passed".into());
    }
    Ok(candidate)
}

fn branch_sha(repo: &Path, branch: &str, reference: &str) -> Result<Sha> {
    if branch.starts_with('-') || branch.contains("@{") || branch.is_empty() {
        return Err("expected an existing local branch name".into());
    }
    git_text(repo, &["check-ref-format", reference])?;
    if !git_text(repo, &["for-each-ref", "--format=%(symref)", reference])?.is_empty() {
        return Err("symbolic target branches are unsupported".into());
    }
    let sha = git_text(repo, &["show-ref", "--verify", "--hash", reference])?.parse()?;
    exact_commit(repo, &sha)?;
    Ok(sha)
}

fn checked_out(repo: &Path, reference: &str) -> Result<bool> {
    let bytes = git(
        repo,
        &[
            "worktree".as_ref(),
            "list".as_ref(),
            "--porcelain".as_ref(),
            "-z".as_ref(),
        ],
    )?;
    let branch = format!("branch {reference}");
    let mut selected = false;
    for group in bytes
        .split(|byte| *byte == 0)
        .collect::<Vec<_>>()
        .split(|field| field.is_empty())
    {
        if !group.contains(&branch.as_bytes()) {
            continue;
        }
        let path = group
            .iter()
            .find_map(|field| field.strip_prefix(b"worktree "))
            .ok_or("target worktree has no path")?;
        let path = Path::new(OsStr::from_bytes(path));
        if selected
            || path.canonicalize()? != repo
            || group
                .iter()
                .any(|field| field.starts_with(b"locked") || field.starts_with(b"prunable"))
        {
            return Err("target branch is occupied by another or unavailable worktree".into());
        }
        selected = true;
    }
    Ok(selected)
}

fn clean_checkout(repo: &Path) -> Result<()> {
    if !git_text(
        repo,
        &[
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignored",
        ],
    )?
    .is_empty()
        || crate::hidden_index_flags(repo)?
    {
        return Err("application requires a clean checkout and normal index tracking".into());
    }
    for marker in [
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
        "BISECT_LOG",
        "BISECT_START",
    ] {
        let path = git_text(repo, &["rev-parse", "--git-path", marker])?;
        match fs::symlink_metadata(repo.join(path)) {
            Ok(_) => return Err(format!("Git operation in progress ({marker})").into()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => (),
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

struct Transaction(Child);

impl Drop for Transaction {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn expect_reply(reader: &mut BufReader<std::process::ChildStdout>, expected: &str) -> Result<()> {
    let deadline = Instant::now() + Duration::from_secs(10);
    let mut line = String::new();
    loop {
        if reader.buffer().is_empty() {
            let mut poll = libc::pollfd {
                fd: reader.get_ref().as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let millis = deadline
                .saturating_duration_since(Instant::now())
                .as_millis() as i32;
            // The child owns the pipe and this poll descriptor lives through the call.
            if unsafe { libc::poll(&mut poll, 1, millis) } <= 0 {
                return Err("Git ref transaction did not respond before the deadline".into());
            }
        }
        line.clear();
        if reader.read_line(&mut line)? == 0 {
            return Err("Git refused the expected-old ref transaction".into());
        }
        if line.trim_end() == expected {
            return Ok(());
        }
    }
}

fn advance(
    repo: &Path,
    reference: &str,
    candidate_ref: &str,
    previous: &Sha,
    candidate: &Sha,
) -> Result<()> {
    let options = ["-c", "core.hooksPath=/dev/null"];
    let checkout = checked_out(repo, reference)?;
    if checkout {
        clean_checkout(repo)?;
    }
    let mut transaction = Transaction(
        git_command(repo)
            .args(options)
            .args(["update-ref", "--no-deref", "--stdin"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?,
    );
    let mut input = transaction
        .0
        .stdin
        .take()
        .ok_or("missing Git transaction input")?;
    let mut output = BufReader::new(
        transaction
            .0
            .stdout
            .take()
            .ok_or("missing Git transaction output")?,
    );
    write!(
        input,
        "start\nverify {candidate_ref} {candidate}\nupdate {reference} {candidate} {previous}\nprepare\n"
    )?;
    input.flush()?;
    expect_reply(&mut output, "prepare: ok")?;
    if checked_out(repo, reference)? != checkout {
        return Err("branch worktree occupancy changed during application".into());
    }
    if checkout {
        clean_checkout(repo)?;
        git_text(
            repo,
            &[
                options[0],
                options[1],
                "read-tree",
                "-u",
                "-m",
                previous.as_str(),
                candidate.as_str(),
            ],
        )?;
    }
    input.write_all(b"commit\n")?;
    drop(input);
    expect_reply(&mut output, "commit: ok")?;
    if !transaction.0.wait()?.success() {
        return Err("Git transaction failed; inspect the retained checkout".into());
    }
    if checkout {
        clean_checkout(repo)?;
    }
    Ok(())
}

fn read_receipt(path: &Path) -> Result<Option<Receipt>> {
    match fs::read(path) {
        Ok(raw) => Ok(Some(serde_json::from_slice(&raw)?)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn publish(directory: &Path, path: &Path, receipt: &Receipt) -> Result<()> {
    let pending = directory.join(format!(".{}.pending", Uuid::new_v4()));
    store::write_new(&pending, &serde_json::to_vec_pretty(receipt)?)?;
    let result = fs::hard_link(&pending, path);
    fs::remove_file(&pending)?;
    result?;
    File::open(directory)?.sync_all()?;
    Ok(())
}

pub fn execute(args: &[OsString]) -> Result<()> {
    let [directory, branch] = args else {
        return Err("expected apply RUN_DIR BRANCH".into());
    };
    let branch = branch.to_str().ok_or("expected a UTF-8 branch name")?;
    let captured = store::load(Path::new(directory))?;
    let candidate = verified(&captured)?;
    let repo = &captured.contract.repository;
    let reference = format!("refs/heads/{branch}");
    let key = store::digest(branch.as_bytes());
    let directory = captured.directory.join("applications");
    fs::create_dir_all(&directory)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(directory.join(format!("{key}.lock")))?;
    // This descriptor owns the per-Run, per-target application reservation.
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let previous = branch_sha(repo, branch, &reference)?;
    let (path, prepared): (PathBuf, PathBuf) = (
        directory.join(format!("{key}.json")),
        directory.join(format!("{key}.prepared")),
    );
    if let Some(receipt) = read_receipt(&path)? {
        if receipt.run_id != captured.contract.run_id
            || receipt.branch != branch
            || receipt.resulting_sha != candidate
            || previous != candidate
        {
            return Err(
                "application receipt or target disagrees with the verified candidate".into(),
            );
        }
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    let mut receipt = Receipt {
        run_id: captured.contract.run_id,
        branch: branch.to_owned(),
        previous_sha: previous.clone(),
        resulting_sha: candidate.clone(),
        operation: Operation::ObservedNoop,
    };
    if previous != candidate {
        git_text(
            repo,
            &[
                "merge-base",
                "--is-ancestor",
                previous.as_str(),
                candidate.as_str(),
            ],
        )
        .map_err(|_| "target is ahead of or diverged from the verified candidate")?;
        if checked_out(repo, &reference)? {
            clean_checkout(repo)?;
        }
        receipt.operation = Operation::Advanced;
        if let Some(saved) = read_receipt(&prepared)? {
            if saved.run_id != receipt.run_id
                || saved.branch != receipt.branch
                || saved.previous_sha != previous
                || saved.resulting_sha != candidate
            {
                return Err("target differs from the previously prepared application".into());
            }
        } else {
            publish(&directory, &prepared, &receipt)?;
        }
        let candidate_ref = store::candidate_ref(captured.contract.run_id);
        advance(repo, &reference, &candidate_ref, &previous, &candidate)
            .map_err(|error| format!("Cannot advance target: {error}. Inspect the retained checkout and prepared receipt."))?;
    }
    if branch_sha(repo, branch, &reference)? != candidate {
        return Err("target changed before receipt publication".into());
    }
    publish(&directory, &path, &receipt)?;
    if branch_sha(repo, branch, &reference)? != candidate {
        return Err("target changed after receipt publication".into());
    }
    println!("{}", serde_json::to_string(&receipt)?);
    Ok(())
}
