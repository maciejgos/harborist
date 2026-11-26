//! Explicit publication of the verified commit to a Run-owned GitHub branch.

use crate::{
    Result, apply, git_text, github,
    record::{Terminal, read_artifact},
    store,
};
use harborist_verify::workflow::Sha;
use serde::{Deserialize, Serialize};
use std::{
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io,
    os::fd::AsRawFd,
    path::Path,
};
use uuid::Uuid;

#[derive(Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct Approval {
    destination: String,
    base: String,
    candidate: Sha,
    attempt: Uuid,
}

#[derive(Deserialize)]
struct Branch {
    #[serde(rename = "ref")]
    name: String,
    sha: Sha,
}

#[derive(Deserialize)]
struct Pull {
    number: u64,
    html_url: String,
    state: String,
    head: Branch,
    base: Branch,
}

#[derive(Deserialize, Serialize)]
struct Receipt {
    approval: Approval,
    pull: u64,
}

fn api<T: serde::de::DeserializeOwned>(repo: &Path, endpoint: &str, args: &[&str]) -> Result<T> {
    let mut command = vec!["api", "--hostname", "github.com", endpoint];
    command.extend_from_slice(args);
    let capture = github::run(repo, 45, &command)?;
    if capture.returncode != 0 || capture.stdout.truncated {
        return Err("GitHub CLI request failed or returned an oversized response".into());
    }
    Ok(serde_json::from_slice(&capture.stdout.bytes)?)
}

fn remote_head(repo: &Path, url: &str, name: &str) -> Result<Option<Sha>> {
    let response = git_text(repo, &["ls-remote", "--refs", "--", url, name])?;
    if response.is_empty() {
        return Ok(None);
    }
    let parts: Vec<_> = response.split_ascii_whitespace().collect();
    match parts.as_slice() {
        [sha, reference] if *reference == name => Ok(Some(sha.parse()?)),
        _ => Err("unexpected GitHub remote head response".into()),
    }
}

fn read_optional<T: serde::de::DeserializeOwned>(path: &Path) -> Result<Option<T>> {
    match fs::read(path) {
        Ok(bytes) => Ok(Some(serde_json::from_slice(&bytes)?)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn record(path: &Path, value: &impl Serialize) -> Result<()> {
    let dir = path.parent().ok_or("missing publication directory")?;
    let pending = dir.join(format!(".{}.pending", Uuid::new_v4()));
    store::write_new(&pending, &serde_json::to_vec_pretty(value)?)?;
    let result = fs::hard_link(&pending, path);
    fs::remove_file(pending)?;
    result?;
    File::open(dir)?.sync_all()?;
    Ok(())
}

fn validate_pull(pull: &Pull, approval: &Approval, branch: &str) -> Result<()> {
    if pull.number == 0
        || pull.state != "open"
        || pull.head.sha != approval.candidate
        || pull.head.name != branch
        || pull.base.name != approval.base
        || !pull.html_url.eq_ignore_ascii_case(&format!(
            "https://github.com/{}/pull/{}",
            approval.destination, pull.number
        ))
    {
        return Err("GitHub PR does not match the approved head and base".into());
    }
    Ok(())
}

pub fn execute(args: &[OsString]) -> Result<()> {
    let [directory, approve, destination, base] = args else {
        return Err("expected publish RUN_DIR APPROVED_SHA OWNER/REPO BASE_BRANCH".into());
    };
    let destination = destination.to_str().ok_or("expected a GitHub repository")?;
    if destination.len() > 256 || !github::valid_repository(destination) {
        return Err("expected a GitHub repository in owner/repo form".into());
    }
    let base = base.to_str().ok_or("expected a base branch")?;
    let approved = crate::commit(approve)?;
    let run = store::load(Path::new(directory))?;
    let repo = &run.contract.repository;
    let base_ref = format!("refs/heads/{base}");
    git_text(repo, &["check-ref-format", &base_ref])?;
    let id = run.contract.run_id;
    let branch = format!("harborist/{id}");
    let reference = format!("refs/heads/{branch}");
    if base == branch {
        return Err("PR base must differ from the Run branch".into());
    }
    let directory = run.directory.join("publication");
    fs::create_dir_all(&directory)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(directory.join("publication.lock"))?;
    // The lock serializes publication and receipt changes for this Run.
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let candidate = apply::verified(&run)?;
    if approved != candidate {
        return Err("approval must match the full VERIFIED candidate SHA".into());
    }
    let terminal = Terminal::load(&run.directory, id)?;
    let approval = Approval {
        destination: destination.to_owned(),
        base: base.to_owned(),
        candidate,
        attempt: terminal.attempt.id(),
    };
    let pending_path = directory.join("prepared.json");
    let receipt_path = directory.join(format!("published-{}.json", approval.attempt));
    let pending: Option<Approval> = read_optional(&pending_path)?;
    let prior: Option<Receipt> = read_optional(&receipt_path)?;
    if pending.as_ref().is_some_and(|saved| saved != &approval)
        || prior
            .as_ref()
            .is_some_and(|saved| saved.approval != approval)
    {
        return Err("approval conflicts with the existing publication".into());
    }
    let url = format!("https://github.com/{destination}.git");
    let observed = remote_head(repo, &url, &reference)?;
    if observed
        .as_ref()
        .is_some_and(|head| head != &approval.candidate)
        || (observed.is_some() && pending.is_none())
    {
        return Err("GitHub head changed or is not owned by this publication".into());
    }
    if remote_head(repo, &url, &base_ref)?.is_none() {
        return Err("GitHub base branch does not exist".into());
    }
    let owner = destination.split_once('/').ok_or("missing GitHub owner")?.0;
    let endpoint = format!("repos/{destination}/pulls");
    let lookup = format!("{endpoint}?state=all&head={owner}:{branch}&per_page=2");
    let mut matches: Vec<Pull> = api(repo, &lookup, &[])?;
    if matches.len() > 1 {
        return Err("multiple GitHub PRs use the Run branch".into());
    }
    let pull = matches.pop();
    if let Some(pull) = &pull {
        if pending.is_none() || observed.is_none() {
            return Err("existing PR is not owned by this publication".into());
        }
        validate_pull(pull, &approval, &branch)?;
    }
    if let Some(prior) = prior {
        let pull = pull
            .filter(|pull| pull.number == prior.pull)
            .ok_or("previously published PR is unavailable")?;
        println!("{}", pull.html_url);
        return Ok(());
    }
    if pending.is_none() {
        record(&pending_path, &approval)?;
    }
    if observed.is_none() {
        let lease = format!("--force-with-lease={reference}:");
        let update = format!("{}:{reference}", approval.candidate);
        git_text(
            repo,
            &[
                "-c",
                "push.followTags=false",
                "push",
                "--no-verify",
                &lease,
                "--",
                &url,
                &update,
            ],
        )?;
    }
    let pull = match pull {
        Some(pull) => pull,
        None => {
            let review = read_artifact(&run.directory, "review/review.md")?;
            let body = format!(
                "body=<!-- harborist-publication:{} -->\n\n## Request\n\n{}\n\nBase: `{}`\n\nCandidate: `{}`\n\n## REVIEW\n\n{}",
                approval.attempt,
                run.intent.chars().take(8000).collect::<String>(),
                run.contract.base_sha,
                approval.candidate,
                review.chars().take(8000).collect::<String>(),
            );
            api(
                repo,
                &endpoint,
                &[
                    "--method",
                    "POST",
                    "--raw-field",
                    &format!("title=Harborist Run {id}"),
                    "--raw-field",
                    &format!("base={base}"),
                    "--raw-field",
                    &format!("head={branch}"),
                    "--raw-field",
                    &body,
                ],
            )?
        }
    };
    validate_pull(&pull, &approval, &branch)?;
    if remote_head(repo, &url, &reference)?.as_ref() != Some(&approval.candidate) {
        return Err("GitHub head changed before receipt publication".into());
    }
    record(
        &receipt_path,
        &Receipt {
            approval,
            pull: pull.number,
        },
    )?;
    println!("{}", pull.html_url);
    Ok(())
}
