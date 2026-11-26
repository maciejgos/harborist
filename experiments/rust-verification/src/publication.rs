//! Explicit publication of the verified commit to a Run-owned GitHub branch.

use crate::{Result, apply, git_text, github, record::read_artifact, store};
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
    previous: Option<Sha>,
}

#[derive(Deserialize, Serialize, Eq, PartialEq)]
struct Branch {
    #[serde(rename = "ref")]
    name: String,
    sha: Sha,
}

#[derive(Deserialize, Serialize)]
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
    timestamp: Option<u64>,
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

fn validate_pull(pull: &Pull, approval: &Approval, branch: &str, head: &Sha) -> Result<()> {
    if pull.number == 0
        || pull.state != "open"
        || &pull.head.sha != head
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PublishRequest {
    approve: Sha,
    expected_attempt: Option<Uuid>,
    destination: String,
    base: String,
    expect_head: Option<Sha>,
}

pub fn browser(directory: &Path, id: Uuid, body: &[u8]) -> Result<serde_json::Value> {
    let request: PublishRequest = serde_json::from_slice(body)?;
    if request.expected_attempt.is_none() {
        return Err("approval must name the expected Attempt".into());
    }
    let run = store::load(directory)?;
    if run.contract.run_id != id {
        return Err("publication must match the requested Run".into());
    }
    Ok(serde_json::json!({"run_id": id, "pull": publish(run, request)?}))
}

fn published(directory: &Path, id: Uuid) -> Result<Option<Receipt>> {
    for number in crate::continuation::numbers(directory)?.into_iter().rev() {
        let attempt_directory = crate::continuation::attempt_path(directory, number);
        let Some(attempt): Option<harborist_verify::workflow::Attempt> =
            read_optional(&attempt_directory.join("attempt.json"))?
        else {
            continue;
        };
        if attempt.run_id() != id {
            return Err("publication Attempt belongs to another Run".into());
        }
        let path = directory
            .join("publication")
            .join(format!("published-{}.json", attempt.id()));
        if let Some(receipt) = read_optional::<Receipt>(&path)? {
            if receipt.approval.attempt != attempt.id() {
                return Err("publication receipt belongs to another Attempt".into());
            }
            return Ok(Some(receipt));
        }
    }
    Ok(None)
}

pub fn delivery(directory: &Path, id: Uuid) -> Result<serde_json::Value> {
    let receipt = published(directory, id)?;
    let publication = receipt.map(|receipt| {
        serde_json::json!({
            "repository": receipt.approval.destination, "base": receipt.approval.base,
            "candidate": receipt.approval.candidate, "attempt": receipt.approval.attempt,
            "previous": receipt.approval.previous, "timestamp": receipt.timestamp, "pull": receipt.pull,
        })
    });
    let mut result = serde_json::json!({"publication": publication});
    if let Some(path) = latest_observation(directory)? {
        let observation: Observation = serde_json::from_slice(&fs::read(&path)?)?;
        if observation.run_id != id {
            return Err("observation does not belong to this Run".into());
        }
        result["observation"] = serde_json::to_value(observation)?;
        result["observation_path"] = serde_json::to_value(path)?;
    }
    Ok(result)
}

pub fn execute(args: &[OsString]) -> Result<()> {
    let (directory, approve, destination, base, expect_head) = match args {
        [directory, approve, destination, base] => (directory, approve, destination, base, None),
        [directory, approve, destination, base, flag, head] if flag == "--expect-head" => (
            directory,
            approve,
            destination,
            base,
            Some(crate::commit(head)?),
        ),
        _ => {
            return Err(
                "expected publish RUN_DIR APPROVED_SHA OWNER/REPO BASE_BRANCH [--expect-head SHA]"
                    .into(),
            );
        }
    };
    let request = PublishRequest {
        destination: destination
            .to_str()
            .ok_or("expected a GitHub repository")?
            .to_owned(),
        base: base.to_str().ok_or("expected a base branch")?.to_owned(),
        approve: crate::commit(approve)?,
        expected_attempt: None,
        expect_head,
    };
    let pull = publish(store::load(Path::new(directory))?, request)?;
    println!("{}", pull.html_url);
    Ok(())
}

fn publish(run: store::Captured, request: PublishRequest) -> Result<Pull> {
    let destination = request.destination.as_str();
    let base = request.base.as_str();
    if destination.len() > 256
        || !github::valid_repository(destination)
        || base.is_empty()
        || base.len() > 256
    {
        return Err("expected a GitHub repository and base branch".into());
    }
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
    let _continuation = crate::continuation::lock(&run.directory)?;
    let verified = apply::verified(&run)?;
    let candidate = verified.candidate;
    if request.approve != candidate {
        return Err("approval must match the full VERIFIED candidate SHA".into());
    }
    if request
        .expected_attempt
        .is_some_and(|id| id != verified.attempt)
    {
        return Err("approval belongs to a different Attempt".into());
    }
    let prior = published(&run.directory, id)?;
    if prior.as_ref().is_some_and(|receipt| {
        receipt.approval.destination != destination || receipt.approval.base != base
    }) {
        return Err("destination differs from existing publication".into());
    }
    let completed = prior
        .as_ref()
        .filter(|receipt| receipt.approval.attempt == verified.attempt);
    let previous = match (&prior, completed) {
        (_, Some(receipt)) => receipt.approval.previous.clone(),
        (Some(receipt), None) => Some(receipt.approval.candidate.clone()),
        (None, None) => None,
    };
    if request.expect_head != previous
        && !completed.is_some_and(|receipt| {
            request.expect_head.as_ref() == Some(&receipt.approval.candidate)
        })
    {
        return Err("expected head differs from the recorded publication".into());
    }
    let approval = Approval {
        destination: destination.to_owned(),
        base: base.to_owned(),
        candidate,
        attempt: verified.attempt,
        previous,
    };
    let pending_path = directory.join(format!("prepared-{}.json", approval.attempt));
    let receipt_path = directory.join(format!("published-{}.json", approval.attempt));
    let pending = match read_optional::<Approval>(&pending_path)? {
        Some(saved) => Some(saved),
        None => read_optional::<Approval>(&directory.join("prepared.json"))?
            .filter(|saved| saved.attempt == approval.attempt),
    };
    if pending.as_ref().is_some_and(|saved| saved != &approval)
        || completed.is_some_and(|saved| saved.approval != approval)
    {
        return Err("approval conflicts with the existing publication".into());
    }
    let url = format!("https://github.com/{destination}.git");
    let observed = remote_head(repo, &url, &reference)?;
    let pushed = observed.as_ref() == Some(&approval.candidate);
    if (pushed && pending.is_none())
        || (!pushed && observed != approval.previous)
        || (completed.is_some() && !pushed)
    {
        return Err("GitHub head changed or is not owned by this publication".into());
    }
    if remote_head(repo, &url, &base_ref)?.is_none() {
        return Err("GitHub base branch does not exist".into());
    }
    let owner = destination.split_once('/').ok_or("missing GitHub owner")?.0;
    let endpoint = format!("repos/{destination}/pulls");
    let lookup = format!("{endpoint}?state=all&head={owner}:{branch}&per_page=2");
    let pull = find_pull(repo, &lookup)?;
    if let Some(pull) = &pull {
        if prior
            .as_ref()
            .is_some_and(|receipt| pull.number != receipt.pull)
            || (prior.is_none() && pending.is_none())
        {
            return Err("existing PR is not owned by this publication".into());
        }
        let head = observed.as_ref().ok_or("published PR has no branch head")?;
        validate_pull(pull, &approval, &branch, head)?;
    } else if prior.is_some() {
        return Err("previously published PR is unavailable".into());
    }
    if completed.is_some() {
        return pull.ok_or_else(|| "previously published PR is unavailable".into());
    }
    if pending.is_none() {
        record(&pending_path, &approval)?;
    }
    if !pushed {
        let expected = approval.previous.as_ref().map_or("", Sha::as_str);
        if let Some(previous) = approval.previous.as_ref() {
            git_text(
                repo,
                &[
                    "merge-base",
                    "--is-ancestor",
                    previous.as_str(),
                    approval.candidate.as_str(),
                ],
            )?;
        }
        let lease = format!("--force-with-lease={reference}:{expected}");
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
    let review = read_artifact(&verified.directory, "review/review.md")?;
    let marker = format!("<!-- harborist-publication:{} -->", approval.attempt);
    let body = format!(
        "body={marker}\n\n## Request\n\n{}\n\nBase: `{}`\n\nCandidate: `{}`\n\n## REVIEW\n\n{}",
        run.intent.chars().take(8000).collect::<String>(),
        run.contract.base_sha,
        approval.candidate,
        review.chars().take(8000).collect::<String>(),
    );
    let pull = if let Some(existing) = pull {
        let current = find_pull(repo, &lookup)?
            .filter(|pull| pull.number == existing.number)
            .ok_or("GitHub PR changed after the branch update")?;
        validate_pull(&current, &approval, &branch, &approval.candidate)?;
        if prior.is_some() {
            let comments = format!("repos/{destination}/issues/{}/comments", current.number);
            let pages: Vec<Vec<Comment>> = api(repo, &comments, &["--paginate", "--slurp"])?;
            if !pages.iter().flatten().any(|comment| {
                comment
                    .body
                    .as_deref()
                    .is_some_and(|body| body.lines().next() == Some(marker.as_str()))
            }) {
                api::<serde_json::Value>(
                    repo,
                    &comments,
                    &["--method", "POST", "--raw-field", &body],
                )?;
            }
        }
        current
    } else {
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
    };
    validate_pull(&pull, &approval, &branch, &approval.candidate)?;
    if remote_head(repo, &url, &reference)?.as_ref() != Some(&approval.candidate) {
        return Err("GitHub head changed before receipt publication".into());
    }
    let timestamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?;
    record(
        &receipt_path,
        &Receipt {
            approval,
            pull: pull.number,
            timestamp: Some(timestamp.as_millis().try_into()?),
        },
    )?;
    Ok(pull)
}

fn find_pull(repo: &Path, lookup: &str) -> Result<Option<Pull>> {
    let mut matches: Vec<Pull> = api(repo, lookup, &[])?;
    if matches.len() > 1 {
        return Err("multiple GitHub PRs use the Run branch".into());
    }
    Ok(matches.pop())
}

#[derive(Deserialize)]
struct Comment {
    body: Option<String>,
}

#[derive(Deserialize)]
struct PullState {
    #[serde(flatten)]
    pull: Pull,
    merged: bool,
    merged_at: Option<String>,
    merge_commit_sha: Option<Sha>,
}

#[derive(Deserialize, Serialize)]
struct Observation {
    run_id: Uuid,
    repository: String,
    observed_at: u64,
    pull: u64,
    url: String,
    state: String,
    head: Sha,
    verified_candidate: Sha,
    head_verified: bool,
    merged_at: Option<String>,
    merge_commit_sha: Option<Sha>,
    checks: CheckPage,
    statuses: StatusPage,
    feedback: Vec<Feedback>,
}

#[derive(Deserialize, Serialize)]
struct CheckPage {
    total_count: u64,
    check_runs: Vec<Check>,
}

#[derive(Deserialize, Serialize)]
struct Check {
    name: String,
    status: String,
    conclusion: Option<String>,
    details_url: Option<String>,
}

#[derive(Deserialize, Serialize)]
struct StatusPage {
    state: String,
    total_count: u64,
    statuses: Vec<Status>,
}

#[derive(Deserialize, Serialize)]
struct Status {
    state: String,
    context: String,
    target_url: Option<String>,
}

#[derive(Deserialize)]
struct RemoteFeedback {
    id: u64,
    user: Option<User>,
    body: Option<String>,
}

#[derive(Deserialize)]
struct User {
    login: String,
}

#[derive(Deserialize, Serialize)]
struct Feedback {
    key: String,
    author: String,
    body: String,
}

fn latest_observation(directory: &Path) -> Result<Option<std::path::PathBuf>> {
    let dir = directory.join("publication/observations");
    let entries = match fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let mut latest = None;
    for entry in entries {
        let entry = entry?;
        let path = entry.path();
        if entry.file_type()?.is_file()
            && path
                .extension()
                .is_some_and(|extension| extension == "json")
            && latest.as_ref().is_none_or(|previous| &path > previous)
        {
            latest = Some(path);
        }
    }
    Ok(latest)
}

pub fn observe(directory: &Path, id: Uuid) -> Result<serde_json::Value> {
    let run = store::load(directory)?;
    if run.contract.run_id != id {
        return Err("observation must match the requested Run".into());
    }
    let receipt = published(directory, id)?.ok_or("Run has no completed GitHub publication")?;
    let destination = receipt.approval.destination;
    if !github::valid_repository(&destination) || receipt.pull == 0 {
        return Err("invalid saved publication destination".into());
    }
    let repo = &run.contract.repository;
    let endpoint = format!("repos/{destination}/pulls/{}", receipt.pull);
    let state: PullState = api(repo, &endpoint, &[])?;
    let pull = &state.pull;
    if pull.number != receipt.pull
        || pull.head.name != format!("harborist/{id}")
        || pull.base.name != receipt.approval.base
        || !pull.html_url.eq_ignore_ascii_case(&format!(
            "https://github.com/{destination}/pull/{}",
            pull.number
        ))
    {
        return Err("GitHub response does not match the published PR".into());
    }
    let commit = format!("repos/{destination}/commits/{}", pull.head.sha);
    let checks: CheckPage = api(repo, &format!("{commit}/check-runs?per_page=50"), &[])?;
    let statuses: StatusPage = api(repo, &format!("{commit}/status?per_page=50"), &[])?;
    if checks.check_runs.len() > 50
        || statuses.statuses.len() > 50
        || checks
            .check_runs
            .iter()
            .any(|check| check.name.chars().count() > 1024)
        || statuses
            .statuses
            .iter()
            .any(|status| status.context.chars().count() > 1024)
    {
        return Err("GitHub returned an invalid check or status page".into());
    }
    let mut feedback = Vec::new();
    for (kind, route) in [
        ("review", format!("pulls/{}/reviews", pull.number)),
        ("inline", format!("pulls/{}/comments", pull.number)),
        ("comment", format!("issues/{}/comments", pull.number)),
    ] {
        let records: Vec<RemoteFeedback> = api(
            repo,
            &format!("repos/{destination}/{route}?per_page=50"),
            &[],
        )?;
        for item in records.into_iter().take(50) {
            if let Some(body) = item.body.filter(|body| {
                !body.trim().is_empty() && !body.starts_with("<!-- harborist-publication:")
            }) {
                feedback.push(Feedback {
                    key: format!("{kind}:{}", item.id),
                    author: item
                        .user
                        .map(|user| user.login)
                        .unwrap_or_else(|| "unknown".to_owned()),
                    body: body.chars().take(4000).collect(),
                });
            }
        }
    }
    let current: PullState = api(repo, &endpoint, &[])?;
    if current.pull.number != pull.number
        || current.pull.head != pull.head
        || current.pull.base != pull.base
        || current.pull.state != pull.state
        || current.merged != state.merged
        || current.merged_at != state.merged_at
        || current.merge_commit_sha != state.merge_commit_sha
    {
        return Err("GitHub PR changed during capture; retry".into());
    }
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?;
    let observed_at = now.as_millis().try_into()?;
    let observation = Observation {
        run_id: id,
        repository: destination,
        observed_at,
        pull: pull.number,
        url: pull.html_url.clone(),
        state: if state.merged {
            "merged".to_owned()
        } else {
            pull.state.clone()
        },
        head: pull.head.sha.clone(),
        head_verified: pull.head.sha == receipt.approval.candidate,
        verified_candidate: receipt.approval.candidate,
        merged_at: state.merged_at,
        merge_commit_sha: if state.merged {
            state.merge_commit_sha
        } else {
            None
        },
        checks,
        statuses,
        feedback,
    };
    let observations = directory.join("publication/observations");
    fs::create_dir_all(&observations)?;
    let path = observations.join(format!("{:020}-{}.json", now.as_micros(), Uuid::new_v4()));
    record(&path, &observation)?;
    Ok(serde_json::json!({"run_id": id, "observation": observation, "observation_path": path}))
}

pub fn status(args: &[OsString]) -> Result<()> {
    let [directory] = args else {
        return Err("expected github-status RUN_DIR".into());
    };
    let run = store::load(Path::new(directory))?;
    println!("{}", observe(&run.directory, run.contract.run_id)?);
    Ok(())
}

pub fn select_feedback(
    directory: &Path,
    id: Uuid,
    candidate: &Sha,
    observation: &Path,
    keys: &[String],
) -> Result<String> {
    if keys.is_empty() || keys.len() > 32 {
        return Err("select between 1 and 32 GitHub feedback IDs".into());
    }
    let parent = directory.join("publication/observations");
    if observation.parent() != Some(parent.as_path()) {
        return Err("select saved GitHub evidence belonging to this Run".into());
    }
    let name = observation
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|_| {
            observation
                .extension()
                .is_some_and(|extension| extension == "json")
        })
        .ok_or("invalid saved GitHub observation name")?;
    let saved: Observation = serde_json::from_str(&read_artifact(&parent, name)?)?;
    if saved.run_id != id || &saved.verified_candidate != candidate {
        return Err("observation belongs to another Run or verified candidate".into());
    }
    let mut selected = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for key in keys {
        if seen.insert(key) {
            let record = saved
                .feedback
                .iter()
                .find(|item| &item.key == key)
                .ok_or_else(|| format!("unknown GitHub feedback ID {key}"))?;
            selected.push(format!("[{key}] {}\n{}", record.author, record.body));
        }
    }
    Ok(format!(
        "GitHub PR {} (observed head {})\n\n{}",
        saved.url,
        saved.head,
        selected.join("\n\n")
    ))
}
