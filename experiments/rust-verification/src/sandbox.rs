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
        self.baseline_sha256 = Some(local_baseline()?);
        Ok(self)
    }

    pub fn validate_frozen(&self) -> Result<()> {
        if self.baseline_sha256.is_none() || self.clone().validate()? != *self {
            return Err("invalid frozen Docker sandbox policy".into());
        }
        Ok(())
    }

    pub fn check_baseline(&self) -> Result<()> {
        let current = local_baseline()?;
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

fn local_control(args: &[&str]) -> Result<Vec<u8>> {
    use std::process::{Command, Stdio};
    use std::time::Duration;

    let mut command = Command::new("sbx");
    command.arg("--no-input").args(args).stdin(Stdio::null());
    let result =
        crate::process::capture_command(&mut command, Duration::from_secs(10), 1024 * 1024)?;
    if result.returncode != 0 || result.timed_out || result.stdout.truncated {
        return Err("Docker Sandboxes control command failed or returned oversized output".into());
    }
    Ok(result.stdout.bytes)
}

fn local_baseline() -> Result<String> {
    if std::env::var_os("HARBORIST_SANDBOX_HOST").is_some_and(|host| !host.is_empty()) {
        return Err("Docker sandbox host helper transport is unavailable in Rust".into());
    }
    static VERSION: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\bv0\.54\.[0-9]+\b").unwrap());
    if !VERSION.is_match(std::str::from_utf8(&local_control(&["version"])?)?) {
        return Err("this adapter requires Docker Sandboxes 0.54.x".into());
    }
    policy_digest(&local_control(&["policy", "ls", "--json"])?)
}

pub fn check_local(args: &[std::ffi::OsString]) -> Result<()> {
    let baseline = match args {
        [] => None,
        [expected] => Some(
            expected
                .to_str()
                .filter(|digest| DIGEST.is_match(digest))
                .ok_or("expected a SHA-256 baseline digest")?,
        ),
        _ => return Err("expected sandbox-check [BASELINE_SHA256]".into()),
    };
    let current = local_baseline()?;
    if baseline.is_some_and(|expected| expected != current) {
        return Err("Docker Sandboxes global policy changed since capture".into());
    }
    println!("{current}");
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
