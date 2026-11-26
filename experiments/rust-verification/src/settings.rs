//! Capture and validate trusted-local execution settings before admission.

use crate::{Result, store::digest};
use harborist_verify::workflow::Stage;
use serde::{Deserialize, Serialize};
use serde_yaml::Value;
use std::{
    collections::HashSet,
    fs, io,
    path::{Path, PathBuf},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Settings {
    version: Value,
    playbook: Source,
    skills: Vec<Source>,
    agent_profile: Profile,
    sandbox_policy: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Source {
    name: String,
    version: String,
    path: PathBuf,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    name: String,
    version: String,
    provider: String,
    pub model: String,
    pub arguments: Vec<String>,
}

impl Profile {
    fn validate(&self) -> Result<()> {
        let model = self.model.as_bytes();
        if self.name.trim().is_empty()
            || self.version.trim().is_empty()
            || self.provider != "codex"
            || model.len() > 128
            || !model.first().is_some_and(u8::is_ascii_alphanumeric)
            || !model
                .iter()
                .all(|byte| byte.is_ascii_alphanumeric() || b"._:/-".contains(byte))
        {
            return Err("invalid Codex profile".into());
        }
        for pair in self.arguments.chunks(2) {
            let [flag, argument] = pair else {
                return Err("invalid Codex profile argument".into());
            };
            let (key, value) = argument
                .split_once('=')
                .ok_or("invalid Codex profile argument")?;
            let value = value.trim();
            let effort = value
                .strip_prefix('"')
                .and_then(|value| value.strip_suffix('"'))
                .or_else(|| {
                    value
                        .strip_prefix('\'')
                        .and_then(|value| value.strip_suffix('\''))
                });
            if !matches!(flag.as_str(), "--config" | "-c")
                || key.trim() != "model_reasoning_effort"
                || !matches!(
                    effort,
                    Some("minimal" | "low" | "medium" | "high" | "xhigh")
                )
            {
                return Err("unsupported Codex profile argument".into());
            }
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Execution {
    pub profile: Profile,
    playbook: Asset,
    skills: Vec<Asset>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Asset {
    name: String,
    version: String,
    content: String,
    sha256: String,
}

impl Asset {
    fn capture(parent: &Path, source: Source) -> Result<Self> {
        let content = fs::read_to_string(parent.join(source.path))?;
        let sha256 = digest(content.as_bytes());
        Ok(Self {
            name: source.name,
            version: source.version,
            content,
            sha256,
        })
    }

    fn header<T: for<'de> Deserialize<'de>>(&self) -> Result<T> {
        if self.sha256 != digest(self.content.as_bytes()) {
            return Err("captured methodology digest mismatch".into());
        }
        let mut lines = self.content.lines();
        if lines.next() != Some("---") {
            return Err("methodology asset requires YAML front matter".into());
        }
        let mut header = String::new();
        for line in lines {
            if line == "---" {
                return Ok(serde_yaml::from_str(&header)?);
            }
            header.push_str(line);
            header.push('\n');
        }
        Err("missing closing methodology delimiter".into())
    }

    fn identity(&self, id: &str, version: &Value) -> bool {
        id == self.name
            && match version {
                Value::String(text) => text == &self.version,
                Value::Number(number) => number.to_string() == self.version,
                _ => false,
            }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Playbook {
    id: String,
    version: Value,
    stages: Vec<Step>,
}

#[derive(Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct Step {
    stage: Stage,
    executor: Executor,
    depends_on: Vec<Stage>,
    fresh_invocation: bool,
    read_only: bool,
    budgeted: bool,
}

#[derive(Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Executor {
    Harborist,
    NativeAgent,
    TrustedTest,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Skill {
    id: String,
    version: Value,
    description: String,
    stages: Vec<Stage>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LegacyExecution {
    playbook: Asset,
    skills: Vec<Asset>,
    agent_profile: Profile,
    sandbox_policy: serde_json::Value,
    budget: LegacyBudget,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyBudget {
    total_seconds: u64,
    verification_reserve_seconds: u64,
}

impl LegacyExecution {
    pub fn trusted_local(self) -> Result<(Execution, u64, u64)> {
        if self.sandbox_policy != "trusted-local" {
            return Err(
                "importing a Docker Sandboxes Run requires the Rust sandbox runtime".into(),
            );
        }
        let total = self.budget.total_seconds;
        let reserve = self.budget.verification_reserve_seconds;
        crate::store::validate_budget(total, reserve)?;
        let execution = Execution {
            profile: self.agent_profile,
            playbook: self.playbook,
            skills: self.skills,
        };
        execution.validate()?;
        Ok((execution, total, reserve))
    }
}

impl Execution {
    pub fn load(repository: &Path, explicit: Option<&Path>) -> Result<Option<Self>> {
        let settings = repository.join("harborist.settings.yaml");
        let path = if let Some(path) = explicit {
            path
        } else {
            match fs::symlink_metadata(&settings) {
                Ok(_) => settings.as_path(),
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    let legacy = repository.join("shipyard.settings.yaml");
                    if !legacy.exists() {
                        return Ok(None);
                    }
                    return Self::load(repository, Some(&legacy));
                }
                Err(error) => return Err(error.into()),
            }
        };
        let path = path.canonicalize()?;
        let parent = path.parent().ok_or("settings file has no parent")?;
        let source: Settings = serde_yaml::from_str(&fs::read_to_string(&path)?)?;
        if source.version.as_u64() != Some(1) {
            return Err("unsupported execution settings version".into());
        }
        if source.sandbox_policy.as_str() != Some("trusted-local") {
            return Err("this Rust runtime supports the trusted-local sandbox policy".into());
        }
        let execution = Self {
            profile: source.agent_profile,
            playbook: Asset::capture(parent, source.playbook)?,
            skills: source
                .skills
                .into_iter()
                .map(|source| Asset::capture(parent, source))
                .collect::<Result<_>>()?,
        };
        execution.validate()?;
        Ok(Some(execution))
    }

    pub fn validate(&self) -> Result<()> {
        self.profile.validate()?;
        let playbook: Playbook = self.playbook.header()?;
        if playbook.id != "bounded-repository-change"
            || playbook.version.as_u64() != Some(1)
            || !self.playbook.identity(&playbook.id, &playbook.version)
            || playbook.stages.len() != Stage::ORDER.len()
        {
            return Err("unsupported playbook identity or canonical stage count".into());
        }
        let mut previous = Vec::new();
        for (&stage, actual) in Stage::ORDER.iter().zip(playbook.stages) {
            let executor = match stage {
                Stage::Intake | Stage::Package => Executor::Harborist,
                Stage::Test => Executor::TrustedTest,
                _ => Executor::NativeAgent,
            };
            let expected = Step {
                stage,
                fresh_invocation: executor == Executor::NativeAgent,
                executor,
                depends_on: previous,
                read_only: stage == Stage::Review,
                budgeted: stage != Stage::Package,
            };
            if actual != expected {
                return Err("playbook does not match canonical execution".into());
            }
            previous = vec![stage];
        }
        let mut ids = HashSet::new();
        for asset in &self.skills {
            let skill: Skill = asset.header()?;
            let stages: HashSet<_> = skill.stages.iter().collect();
            if !asset.identity(&skill.id, &skill.version)
                || !ids.insert(skill.id)
                || skill.description.trim().is_empty()
                || stages.is_empty()
                || stages.len() != skill.stages.len()
                || skill.stages.iter().any(|stage| {
                    !matches!(
                        stage,
                        Stage::Design | Stage::Plan | Stage::Build | Stage::Review
                    )
                })
            {
                return Err("invalid or duplicate skill declaration".into());
            }
        }
        Ok(())
    }

    pub fn guidance(&self, stage: Stage) -> Result<serde_json::Value> {
        let mut skills = Vec::new();
        for asset in &self.skills {
            let skill: Skill = asset.header()?;
            if skill.stages.contains(&stage) {
                skills.push(&asset.content);
            }
        }
        Ok(serde_json::json!({"playbook": self.playbook.content, "skills": skills}))
    }
}
