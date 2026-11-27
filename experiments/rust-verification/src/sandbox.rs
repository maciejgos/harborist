//! Frozen Docker Sandboxes policy shared by intake and execution.

use crate::Result;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::LazyLock;

const CODEX_KIT: &str =
    "docker.io/sbx/codex@sha256:7d283f7cacf5c069b6f61cdcba87ce3b570a0c5a43c36d88d3f8873732503162";
static TEMPLATE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\A[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}\z").unwrap());
static DESTINATION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\A(?:\*\*?\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?\z").unwrap()
});
static DIGEST: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\A[0-9a-f]{64}\z").unwrap());

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum Kind {
    DockerSandboxes,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct DockerPolicy {
    kind: Kind,
    template: String,
    cpus: u8,
    memory_mib: u16,
    allow: Vec<String>,
    deny: Vec<String>,
    baseline_sha256: Option<String>,
}

impl Default for DockerPolicy {
    fn default() -> Self {
        Self {
            kind: Kind::DockerSandboxes,
            template: CODEX_KIT.to_owned(),
            cpus: 2,
            memory_mib: 2048,
            allow: Vec::new(),
            deny: Vec::new(),
            baseline_sha256: None,
        }
    }
}

impl DockerPolicy {
    pub fn freeze(mut self) -> Result<Self> {
        self.baseline_sha256 = Some(baseline()?);
        Ok(self)
    }

    pub fn validate_frozen(&self) -> Result<()> {
        if self.baseline_sha256.is_none() || self.clone().validate()? != *self {
            return Err("invalid frozen Docker sandbox policy".into());
        }
        Ok(())
    }

    pub fn check_baseline(&self) -> Result<()> {
        let current = baseline()?;
        if self.baseline_sha256.as_deref() != Some(current.as_str()) {
            return Err("Docker Sandboxes global policy changed since capture".into());
        }
        Ok(())
    }

    pub fn validate(mut self) -> Result<Self> {
        if !TEMPLATE.is_match(&self.template)
            || !(1..=16).contains(&self.cpus)
            || !(512..=32768).contains(&self.memory_mib)
            || self
                .baseline_sha256
                .as_ref()
                .is_some_and(|value| !DIGEST.is_match(value))
        {
            return Err(
                "invalid Docker sandbox template, resource limits, or baseline digest".into(),
            );
        }
        self.allow = destinations(self.allow)?;
        self.deny = destinations(self.deny)?;
        if self.allow.iter().any(|entry| self.deny.contains(entry)) {
            return Err("a Docker sandbox destination cannot be both allowed and blocked".into());
        }
        Ok(self)
    }
}

fn destinations(values: Vec<String>) -> Result<Vec<String>> {
    if values.len() > 64 {
        return Err("Docker sandbox policy permits up to 64 destinations per list".into());
    }
    let mut normalized = Vec::new();
    for value in values {
        let value = value.trim().to_lowercase();
        if !DESTINATION.is_match(&value)
            || value.contains("..")
            || value
                .split_once(':')
                .is_some_and(|(_, port)| !port.parse::<u16>().is_ok_and(|port| port > 0))
        {
            return Err("invalid Docker sandbox network destination".into());
        }
        if !normalized.contains(&value) {
            normalized.push(value);
        }
    }
    Ok(normalized)
}

/// Fingerprint effective global rules using the canonical Python wire format.
pub fn policy_digest(raw: &[u8]) -> Result<String> {
    use serde_json::Value;
    const FIELDS: [&str; 9] = [
        "scope",
        "resource_type",
        "decision",
        "resources",
        "actions",
        "status",
        "origin",
        "layer",
        "reason",
    ];
    let snapshot: Value = serde_json::from_slice(raw)?;
    let rules = snapshot["rules"]
        .as_array()
        .ok_or("invalid Docker network policy")?;
    let mut effective = Vec::new();
    for rule in rules {
        let rule = rule.as_object().ok_or("invalid Docker network rule")?;
        if rule.get("scope").and_then(Value::as_str) == Some("global") {
            let projected = Value::Object(
                FIELDS
                    .into_iter()
                    .map(|field| {
                        (
                            field.to_owned(),
                            rule.get(field).cloned().unwrap_or(Value::Null),
                        )
                    })
                    .collect(),
            );
            effective.push(canonical_json(&projected)?);
        }
    }
    if effective.is_empty() {
        return Err("no global Docker network policy".into());
    }
    effective.sort_unstable();
    Ok(crate::store::digest(
        format!("[{}]", effective.join(", ")).as_bytes(),
    ))
}

fn canonical_json(value: &serde_json::Value) -> Result<String> {
    use serde_json::Value;
    use std::fmt::Write;
    match value {
        Value::String(value) => {
            let mut ascii = String::new();
            for unit in serde_json::to_string(value)?.encode_utf16() {
                if unit <= 0x7e {
                    ascii.push(char::from(u8::try_from(unit)?));
                } else {
                    write!(ascii, "\\u{unit:04x}")?;
                }
            }
            Ok(ascii)
        }
        Value::Array(values) => {
            let items = values
                .iter()
                .map(canonical_json)
                .collect::<Result<Vec<_>>>()?;
            Ok(format!("[{}]", items.join(", ")))
        }
        Value::Object(values) => {
            let mut entries: Vec<_> = values.iter().collect();
            entries.sort_unstable_by_key(|(name, _)| *name);
            let mut fields = Vec::with_capacity(entries.len());
            for (name, value) in entries {
                let key = canonical_json(&Value::String(name.clone()))?;
                fields.push(format!("{key}: {}", canonical_json(value)?));
            }
            Ok(format!("{{{}}}", fields.join(", ")))
        }
        Value::Number(number) if number.is_f64() => {
            Err("unexpected non-integer number in effective Docker network policy".into())
        }
        _ => Ok(serde_json::to_string(value)?),
    }
}

fn helper_host() -> Result<Option<String>> {
    match std::env::var("HARBORIST_SANDBOX_HOST") {
        Ok(host) if !host.is_empty() => Ok(Some(host)),
        Ok(_) | Err(std::env::VarError::NotPresent) => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn control(args: &[&str]) -> Result<Vec<u8>> {
    control_with_timeout(args, 10)
}

fn control_with_timeout(args: &[&str], seconds: u64) -> Result<Vec<u8>> {
    capture_output(args, seconds, 1024 * 1024)
}

fn capture_output(args: &[&str], seconds: u64, limit: usize) -> Result<Vec<u8>> {
    let result = match helper_host()? {
        Some(host) => crate::sandbox_host::invoke(&host, args, seconds, limit, &[])?,
        None => local_capture(args, seconds, limit)?,
    };
    checked_output(result)
}

fn checked_output(result: crate::process::Capture) -> Result<Vec<u8>> {
    if result.returncode != 0 || result.timed_out || result.stdout.truncated {
        return Err("Docker Sandboxes control command failed or returned oversized output".into());
    }
    Ok(result.stdout.bytes)
}

struct GuestCommand<'a> {
    name: &'a str,
    allowance: std::time::Duration,
    limit: usize,
    cancellation: Option<&'a std::path::Path>,
}

impl GuestCommand<'_> {
    fn capture(
        &self,
        command: &[&str],
        input: Option<&std::fs::File>,
    ) -> Result<crate::process::Capture> {
        use std::io::Read;
        use std::time::Duration;
        if let Some(marker) = self.cancellation {
            crate::retirement::cancelled(marker)?;
        }
        if self.allowance.is_zero() {
            return Err("Docker Sandbox execution deadline exhausted".into());
        }
        let timeout = format!("{:.3}s", self.allowance.as_secs_f64().max(0.001));
        let mut args = vec![
            "exec",
            "-i",
            "--workdir",
            GUEST_REPOSITORY,
            self.name,
            "timeout",
            "--kill-after=2s",
            &timeout,
        ];
        args.extend_from_slice(command);
        let host_timeout = self.allowance.saturating_add(Duration::from_secs(3));
        let mut result = if let Some(host) = helper_host()? {
            let mut bytes = Vec::new();
            if let Some(file) = input {
                file.take(64 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
            }
            crate::sandbox_host::invoke(
                &host,
                &args,
                host_timeout.as_secs().clamp(1, 3600),
                self.limit,
                &bytes,
            )?
        } else {
            let mut child = local_command(&args);
            if let Some(file) = input {
                child.stdin(file.try_clone()?);
            }
            crate::process::capture_cancellable(
                &mut child,
                host_timeout,
                self.limit,
                self.cancellation,
            )?
        };
        if let Some(marker) = self.cancellation {
            crate::retirement::cancelled(marker)?;
        }
        result.timed_out |= result.returncode == 124;
        Ok(result)
    }
}

fn local_capture(args: &[&str], seconds: u64, limit: usize) -> Result<crate::process::Capture> {
    Ok(crate::process::capture_command(
        &mut local_command(args),
        std::time::Duration::from_secs(seconds),
        limit,
    )?)
}

fn local_command(args: &[&str]) -> std::process::Command {
    use std::process::{Command, Stdio};
    let mut command = Command::new("sbx");
    command.arg("--no-input").args(args).stdin(Stdio::null());
    for key in [
        "SSH_AUTH_SOCK",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ] {
        command.env_remove(key);
    }
    command
}

fn baseline() -> Result<String> {
    static VERSION: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\bv0\.54\.[0-9]+\b").unwrap());
    if !VERSION.is_match(std::str::from_utf8(&control(&["version"])?)?) {
        return Err("this adapter requires Docker Sandboxes 0.54.x".into());
    }
    policy_digest(&control(&["policy", "ls", "--json"])?)
}

pub fn check(args: &[std::ffi::OsString]) -> Result<()> {
    let expected_baseline = match args {
        [] => None,
        [expected] => Some(
            expected
                .to_str()
                .filter(|digest| DIGEST.is_match(digest))
                .ok_or("expected a SHA-256 baseline digest")?,
        ),
        _ => return Err("expected sandbox-check [BASELINE_SHA256]".into()),
    };
    let current = baseline()?;
    if expected_baseline.is_some_and(|expected| expected != current) {
        return Err("Docker Sandboxes global policy changed since capture".into());
    }
    println!("{current}");
    Ok(())
}

fn provision(policy: &DockerPolicy, name: &str) -> Result<()> {
    let cpus = policy.cpus.to_string();
    let memory = format!("{}m", policy.memory_mib);
    control(&[
        "create",
        "--name",
        name,
        "--cpus",
        &cpus,
        "--memory",
        &memory,
        "--skills",
        "off",
        "--static-mcp",
        "none",
        &policy.template,
    ])?;
    for (decision, rules) in [("allow", &policy.allow), ("deny", &policy.deny)] {
        for resource in rules {
            control(&["policy", decision, "network", "--sandbox", name, resource])?;
        }
    }
    Ok(())
}

#[derive(Deserialize)]
struct SandboxStatus {
    name: String,
    status: String,
}

fn finish(name: &str, exported: bool) -> Result<()> {
    if exported {
        control_with_timeout(&["rm", "--force", name], 30)?;
    } else {
        // A failed create may have left no sandbox. Inspect to determine its state.
        let _ = control_with_timeout(&["stop", name], 30);
    }
    let listed: Vec<SandboxStatus> = serde_json::from_slice(&control(&["ls", "--json"])?)?;
    if listed
        .iter()
        .any(|entry| entry.name == name && (exported || entry.status != "stopped"))
    {
        return Err("Docker Sandbox termination or removal is still pending".into());
    }
    Ok(())
}

const GUEST_BUNDLE: &str = "/tmp/harborist-source.bundle";
pub const GUEST_SCHEMA: &str = "/tmp/harborist-schema.json";
pub const GUEST_FINAL: &str = "/tmp/harborist-final.json";
pub const GUEST_REPOSITORY: &str = "/home/agent/workspace/repository";

struct TransferDirectory(std::path::PathBuf);

impl TransferDirectory {
    fn create() -> Result<Self> {
        use std::os::unix::fs::DirBuilderExt;

        let directory =
            std::env::temp_dir().join(format!("harborist-bundle-{}", uuid::Uuid::new_v4()));
        std::fs::DirBuilder::new().mode(0o700).create(&directory)?;
        Ok(Self(directory))
    }
}

impl Drop for TransferDirectory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn upload(name: &str, path: &std::path::Path, destination: &str) -> Result<()> {
    use std::io::Read;
    if let Some(host) = helper_host()? {
        const LIMIT: u64 = 64 * 1024 * 1024;
        let mut input = Vec::new();
        std::fs::File::open(path)?
            .take(LIMIT + 1)
            .read_to_end(&mut input)?;
        if input.len() as u64 > LIMIT {
            return Err("Docker Sandbox input exceeds the transfer limit".into());
        }
        checked_output(crate::sandbox_host::invoke(
            &host,
            &["upload", name, destination],
            30,
            1024 * 1024,
            &input,
        )?)?;
    } else {
        let source = path
            .to_str()
            .ok_or("Docker Sandbox input path must be UTF-8")?;
        control_with_timeout(&["cp", source, &format!("{name}:{destination}")], 30)?;
    }
    Ok(())
}

fn download(name: &str, source: &str, limit: usize) -> Result<Vec<u8>> {
    use std::io::Read;
    if let Some(host) = helper_host()? {
        return checked_output(crate::sandbox_host::invoke(
            &host,
            &["download", name, source],
            30,
            limit,
            &[],
        )?);
    }
    let transfer = TransferDirectory::create()?;
    let destination = transfer.0.join("artifact");
    control_with_timeout(
        &[
            "cp",
            &format!("{name}:{source}"),
            destination
                .to_str()
                .ok_or("Docker Sandbox output path must be UTF-8")?,
        ],
        30,
    )?;
    let mut bytes = Vec::new();
    crate::record::open_artifact(&transfer.0, "artifact")?
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > limit {
        return Err("Docker Sandbox output exceeds the transfer limit".into());
    }
    Ok(bytes)
}

pub fn with_guest<T>(
    policy: &DockerPolicy,
    label: &str,
    workspace: &std::path::Path,
    build: bool,
    operation: impl FnOnce(&str) -> Result<T>,
) -> Result<T> {
    policy.check_baseline()?;
    let name = format!(
        "harborist-{label}-{}",
        &uuid::Uuid::new_v4().simple().to_string()[..16]
    );
    let result = provision(policy, &name)
        .and_then(|_| populate(&name, workspace))
        .and_then(|revision| {
            let output = operation(&name)?;
            export_changes(policy, &name, workspace, revision.as_str(), build)?;
            Ok(output)
        });
    finish(&name, result.is_ok())
        .map_err(|error| format!("Sandbox {name} cleanup failed: {error}"))?;
    result
}

pub fn run_check(
    name: &str,
    command: &str,
    allowance: std::time::Duration,
    cancellation: &std::path::Path,
) -> std::io::Result<crate::process::Capture> {
    GuestCommand {
        name,
        allowance,
        limit: 65536,
        cancellation: Some(cancellation),
    }
    .capture(&["/bin/sh", "-c", command], None)
    .map_err(|error| match error.downcast::<std::io::Error>() {
        Ok(error) => *error,
        Err(error) => std::io::Error::other(error.to_string()),
    })
}

pub fn run_codex(
    name: &str,
    args: &[&str],
    schema: &std::path::Path,
    input: &std::fs::File,
    allowance: std::time::Duration,
    cancellation: &std::path::Path,
) -> Result<(crate::process::Capture, Vec<u8>)> {
    let started = std::time::Instant::now();
    upload(name, schema, GUEST_SCHEMA)?;
    let capture = GuestCommand {
        name,
        allowance: allowance.saturating_sub(started.elapsed()),
        limit: 65536,
        cancellation: Some(cancellation),
    }
    .capture(args, Some(input))?;
    let response = if capture.returncode == 0 && !capture.timed_out {
        download(name, GUEST_FINAL, 4 * 1024 * 1024)?
    } else {
        Vec::new()
    };
    Ok((capture, response))
}

fn guest_git(name: &str, args: &[&str], limit: usize) -> Result<Vec<u8>> {
    let mut command = vec![
        "exec",
        name,
        "git",
        "--no-replace-objects",
        "-C",
        GUEST_REPOSITORY,
        "-c",
        "core.hooksPath=/dev/null",
    ];
    command.extend_from_slice(args);
    capture_output(&command, 30, limit)
}

fn export_changes(
    policy: &DockerPolicy,
    name: &str,
    workspace: &std::path::Path,
    revision: &str,
    build: bool,
) -> Result<()> {
    let head = guest_git(name, &["rev-parse", "--verify", "HEAD"], 65536)?;
    if std::str::from_utf8(&head)?.trim_end() != revision {
        return Err("Docker Sandbox changed the starting revision".into());
    }
    let flags = guest_git(name, &["ls-files", "-v", "-z"], 16 * 1024 * 1024)?;
    if flags
        .split(|byte| *byte == 0)
        .filter_map(|entry| entry.first())
        .any(|flag| flag.is_ascii_lowercase() || *flag == b'S')
    {
        return Err("Docker Sandbox changed index tracking flags".into());
    }
    guest_git(name, &["clean", "-fdX", "--", "."], 65536)?;
    guest_git(name, &["add", "--all", "--", "."], 65536)?;
    let patch = guest_git(
        name,
        &[
            "diff",
            "--cached",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            revision,
            "--",
            ".",
        ],
        16 * 1024 * 1024,
    )?;
    if !build && !patch.is_empty() {
        return Err("read-only Docker Sandbox stage changed the workspace".into());
    }
    policy.check_baseline()?;
    if !patch.is_empty() {
        if crate::git_text(workspace, &["rev-parse", "--verify", "HEAD"])? != revision {
            return Err("host workspace changed during Docker Sandbox execution".into());
        }
        let transfer = TransferDirectory::create()?;
        let file = transfer.0.join("build.patch");
        crate::store::write_new(&file, &patch)?;
        crate::git(
            workspace,
            &[
                "apply".as_ref(),
                "--index".as_ref(),
                "--binary".as_ref(),
                "--whitespace=nowarn".as_ref(),
                "--".as_ref(),
                file.as_os_str(),
            ],
        )?;
    }
    Ok(())
}

fn populate(name: &str, repository: &std::path::Path) -> Result<harborist_verify::workflow::Sha> {
    use harborist_verify::workflow::Sha;

    let revision: Sha =
        crate::git_text(repository, &["rev-parse", "--verify", "HEAD^{commit}"])?.parse()?;
    let transfer = TransferDirectory::create()?;
    let path = transfer.0.join("source.bundle");
    crate::git(
        repository,
        &[
            "bundle".as_ref(),
            "create".as_ref(),
            path.as_os_str(),
            "HEAD".as_ref(),
        ],
    )?;
    // Confirm the exported ref still points at the revision selected before bundling.
    let bundle = crate::git(
        repository,
        &["bundle".as_ref(), "list-heads".as_ref(), path.as_os_str()],
    )?;
    if std::str::from_utf8(&bundle)?.trim_end() != format!("{} HEAD", revision.as_str()) {
        return Err("Docker Sandbox bundle does not match the selected revision".into());
    }
    upload(name, &path, GUEST_BUNDLE)?;
    control(&[
        "exec",
        name,
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "clone",
        "--no-checkout",
        GUEST_BUNDLE,
        GUEST_REPOSITORY,
    ])?;
    control(&[
        "exec",
        name,
        "git",
        "--no-replace-objects",
        "-C",
        GUEST_REPOSITORY,
        "-c",
        "core.hooksPath=/dev/null",
        "checkout",
        "--detach",
        revision.as_str(),
    ])?;
    let head = control(&[
        "exec",
        name,
        "git",
        "--no-replace-objects",
        "-C",
        GUEST_REPOSITORY,
        "rev-parse",
        "--verify",
        "HEAD",
    ])?;
    if std::str::from_utf8(&head)?.trim_end() != revision.as_str() {
        return Err("Docker Sandbox checkout does not match the selected revision".into());
    }
    let status = GuestCommand {
        name,
        allowance: std::time::Duration::from_secs(10),
        limit: 65536,
        cancellation: None,
    }
    .capture(
        &[
            "git",
            "--no-replace-objects",
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        None,
    )?;
    if status.returncode != 0
        || status.timed_out
        || status.stdout.truncated
        || !status.stdout.bytes.is_empty()
    {
        return Err("Docker Sandbox checkout is not a clean workspace".into());
    }
    Ok(revision)
}

pub fn probe(args: &[std::ffi::OsString]) -> Result<()> {
    let (file, repository) = match args {
        [file] => (file, None),
        [file, repository] => (file, Some(std::path::Path::new(repository))),
        _ => return Err("expected sandbox-probe FROZEN_POLICY_JSON [REPOSITORY]".into()),
    };
    let policy: DockerPolicy = serde_json::from_slice(&std::fs::read(file)?)?;
    policy.validate_frozen()?;
    policy.check_baseline()?;
    let name = format!(
        "harborist-test-{}",
        &uuid::Uuid::new_v4().simple().to_string()[..16]
    );
    let result = provision(&policy, &name).and_then(|_| {
        repository.map_or(Ok(()), |repository| {
            let revision = populate(&name, repository)?;
            export_changes(&policy, &name, repository, revision.as_str(), false)
        })
    });
    finish(&name, result.is_ok())
        .map_err(|error| format!("Sandbox {name} cleanup failed: {error}"))?;
    result?;
    println!("{name}");
    Ok(())
}

pub fn digest_file(args: &[std::ffi::OsString]) -> Result<()> {
    let [file] = args else {
        return Err("expected sandbox-policy-digest POLICY_JSON".into());
    };
    println!("{}", policy_digest(&std::fs::read(file)?)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_ordered_destinations_and_defaults() {
        let policy: DockerPolicy =
            serde_json::from_str(r#"{"allow":[" Example.COM ","example.com","**.test.org:443"]}"#)
                .unwrap();
        let policy = policy.validate().unwrap();
        assert_eq!(policy.allow, ["example.com", "**.test.org:443"]);
        assert_eq!(policy.template, CODEX_KIT);
        assert_eq!((policy.cpus, policy.memory_mib), (2, 2048));
    }

    #[test]
    fn rejects_expanding_or_invalid_rules() {
        for raw in [
            r#"{"allow":["EXAMPLE.COM"],"deny":["example.com"]}"#,
            r#"{"allow":["example.com:65536"]}"#,
            r#"{"allow":["example..com"]}"#,
            r#"{"cpus":17}"#,
            r#"{"baseline_sha256":"invalid"}"#,
            r#"{"template":"docker.io/sbx/codex:latest"}"#,
        ] {
            assert!(
                serde_json::from_str::<DockerPolicy>(raw)
                    .unwrap()
                    .validate()
                    .is_err(),
                "{raw}"
            );
        }
    }
}
