//! GitHub Issue transport through the authenticated system gh executable.

use crate::{Result, process};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    path::Path,
    process::{Command, Stdio},
    time::Duration,
};

pub fn valid_repository(value: &str) -> bool {
    let Some((owner, repo)) = value.split_once('/') else {
        return false;
    };
    owner
        .as_bytes()
        .first()
        .is_some_and(u8::is_ascii_alphanumeric)
        && owner
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
        && !matches!(repo, "" | "." | "..")
        && repo
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
}

fn valid_number(value: &str) -> bool {
    value
        .as_bytes()
        .first()
        .is_some_and(|first| matches!(first, b'1'..=b'9'))
        && value.bytes().all(|byte| byte.is_ascii_digit())
}

fn split_url(url: &str) -> Option<(&str, &str)> {
    let (repository, number) = url
        .strip_prefix("https://github.com/")?
        .rsplit_once("/issues/")?;
    (valid_repository(repository) && valid_number(number)).then_some((repository, number))
}

pub fn selector(source: &str) -> Result<String> {
    let pair = if let Some(raw) = source.strip_prefix("github:") {
        raw.split_once('#')
    } else {
        split_url(source.trim_end_matches('/'))
    };
    match pair {
        Some((repository, number)) if valid_repository(repository) && valid_number(number) => {
            Ok(format!("github:{repository}#{number}"))
        }
        _ => Err("expected github:owner/repo#positive-issue-number or a GitHub Issue URL".into()),
    }
}

pub fn run(cwd: &Path, allowance: u64, args: &[&str]) -> Result<process::Capture> {
    let capture = process::capture_command(
        Command::new("gh")
            .args(args)
            .current_dir(cwd)
            .env("GH_PROMPT_DISABLED", "1")
            .stdin(Stdio::null()),
        Duration::from_secs(allowance),
        2 * 1024 * 1024,
    )?;
    if capture.timed_out {
        return Err("GitHub CLI timed out".into());
    }
    Ok(capture)
}

fn issue_json(cwd: &Path, args: &[&str]) -> Result<Vec<u8>> {
    let capture = run(cwd, 30, args)?;
    if capture.returncode != 0 {
        return Err(
            "GitHub CLI request failed; check gh authentication and repository access".into(),
        );
    }
    if capture.stdout.truncated {
        return Err("GitHub CLI response exceeded the capture limit".into());
    }
    Ok(capture.stdout.bytes)
}

#[derive(Deserialize)]
struct Label {
    name: String,
}

fn labels(values: Vec<Label>) -> BTreeSet<String> {
    values.into_iter().map(|label| label.name).collect()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Issue {
    title: String,
    body: String,
    labels: Vec<Label>,
    url: String,
}

pub fn capture(cwd: &Path, source: &str) -> Result<(String, String)> {
    let (_, tail) = source.split_once(':').ok_or("invalid GitHub selector")?;
    let (repo, number) = tail.split_once('#').ok_or("invalid GitHub selector")?;
    if !valid_repository(repo) || !valid_number(number) {
        return Err("invalid GitHub Issue selector".into());
    }
    let issue: Issue = serde_json::from_slice(&issue_json(
        cwd,
        &[
            "issue",
            "view",
            number,
            "--repo",
            repo,
            "--json",
            "title,body,labels,url",
        ],
    )?)?;
    if !split_url(&issue.url).is_some_and(|(_, actual)| actual == number) {
        return Err("GitHub returned an invalid canonical Issue URL".into());
    }
    let intent = format!(
        "# {}\n\nLabels: {}\n\n{}",
        issue.title,
        serde_json::to_string(&labels(issue.labels))?,
        issue.body
    );
    Ok((intent, issue.url))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ListRequest {
    repository: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ListedIssue {
    number: u64,
    title: String,
    labels: Vec<Label>,
    url: String,
}

pub fn list(control: &Path, body: &[u8]) -> Result<Value> {
    let request: ListRequest = serde_json::from_slice(body)?;
    let repo = request.repository.trim();
    if repo.len() > 256 || !valid_repository(repo) {
        return Err("expected a GitHub repository in owner/repo form".into());
    }
    let issues: Vec<ListedIssue> = serde_json::from_slice(&issue_json(
        control,
        &[
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,title,labels,url",
        ],
    )?)?;
    if issues.len() > 100 {
        return Err("invalid Issue list size".into());
    }
    let tickets = issues
        .into_iter()
        .map(|issue| {
            let expected = format!("https://github.com/{repo}/issues/{}", issue.number);
            if issue.number == 0 || !issue.url.eq_ignore_ascii_case(&expected) {
                return Err("GitHub returned an Issue URL outside the requested repository");
            }
            Ok(json!({
                "identity": format!("{repo}#{}", issue.number), "title": issue.title,
                "labels": labels(issue.labels), "url": issue.url,
            }))
        })
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(json!({"issues": tickets}))
}
