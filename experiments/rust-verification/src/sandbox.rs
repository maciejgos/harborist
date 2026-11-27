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

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
enum Kind {
    DockerSandboxes,
}

#[derive(Debug, Deserialize, Serialize)]
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
