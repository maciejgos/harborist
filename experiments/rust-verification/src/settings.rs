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
    sandbox_policy: SandboxPolicy,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum SandboxPolicy {
    Mode(String),
    Docker(crate::sandbox::DockerPolicy),
}

impl SandboxPolicy {
    fn docker(self) -> Result<Option<crate::sandbox::DockerPolicy>> {
        match self {
            Self::Mode(mode) if mode == "trusted-local" => Ok(None),
            Self::Docker(policy) => Ok(Some(policy.validate()?)),
            _ => Err("invalid sandbox policy".into()),
        }
    }
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub docker_policy: Option<crate::sandbox::DockerPolicy>,
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

    fn document(&self) -> Result<(&str, &str)> {
        if self.sha256 != digest(self.content.as_bytes()) {
            return Err("captured methodology digest mismatch".into());
        }
        let source = self
            .content
            .strip_prefix('\u{feff}')
            .unwrap_or(&self.content);
        let mut lines = source.split_inclusive('\n');
        let opening = lines.next().ok_or("empty methodology document")?;
        if opening.trim_end_matches(['\r', '\n']) != "---" {
            return Err("methodology asset requires YAML front matter".into());
        }
        let mut offset = opening.len();
        for line in lines {
            if line.trim_end_matches(['\r', '\n']) == "---" {
                let body = &source[offset + line.len()..];
                if body.trim().is_empty() {
                    return Err("methodology requires nonblank Markdown guidance".into());
                }
                return Ok((&source[opening.len()..offset], body));
            }
            offset += line.len();
        }
        Err("missing closing methodology delimiter".into())
    }

    fn header<T: for<'de> Deserialize<'de>>(&self) -> Result<T> {
        Ok(serde_yaml::from_str(self.document()?.0)?)
    }

    fn preview_identity(&self, kind: &str) -> serde_json::Value {
        serde_json::json!({
            "kind": kind, "name": self.name, "version": self.version, "sha256": self.sha256,
        })
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

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Playbook {
    id: String,
    version: Value,
    stages: Vec<Step>,
}

#[derive(Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct Step {
    stage: Stage,
    executor: Executor,
    depends_on: Vec<Stage>,
    fresh_invocation: bool,
    read_only: bool,
    budgeted: bool,
}

#[derive(Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Executor {
    #[serde(alias = "shipyard")]
    Harborist,
    NativeAgent,
    TrustedTest,
}

#[derive(Deserialize, Serialize)]
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
    sandbox_policy: SandboxPolicy,
    budget: LegacyBudget,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyBudget {
    total_seconds: u64,
    verification_reserve_seconds: u64,
}

impl LegacyExecution {
    pub fn into_execution(self) -> Result<(Execution, u64, u64)> {
        let docker_policy = self.sandbox_policy.docker()?;
        let total = self.budget.total_seconds;
        let reserve = self.budget.verification_reserve_seconds;
        crate::store::validate_budget(total, reserve)?;
        let execution = Execution {
            profile: self.agent_profile,
            docker_policy,
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
        let docker_policy = source
            .sandbox_policy
            .docker()?
            .map(crate::sandbox::DockerPolicy::freeze)
            .transpose()?;
        let execution = Self {
            profile: source.agent_profile,
            docker_policy,
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

    pub fn check_runtime(&self) -> Result<()> {
        if let Some(policy) = &self.docker_policy {
            policy.check_baseline()?;
        }
        Ok(())
    }

    pub fn validate(&self) -> Result<()> {
        if let Some(policy) = &self.docker_policy {
            policy.validate_frozen()?;
        }
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

    pub fn methodology(&self) -> Result<serde_json::Value> {
        use serde_json::json;

        let playbook: Playbook = self.playbook.header()?;
        let mut skills = Vec::new();
        for asset in &self.skills {
            let skill: Skill = asset.header()?;
            skills.push(json!({
                "identity": asset.preview_identity("skill"),
                "metadata": {"id": skill.id, "version": asset.version, "description": skill.description, "stages": skill.stages},
                "guidance": asset.document()?.1,
            }));
        }
        Ok(json!({
            "playbook": {
                "identity": self.playbook.preview_identity("playbook"),
                "definition": {"name": playbook.id, "version": self.playbook.version, "stages": playbook.stages},
                "guidance": self.playbook.document()?.1,
            },
            "skills": skills,
        }))
    }

    pub fn preview_guidance(&self, stage: Stage) -> Result<serde_json::Value> {
        use serde_json::json;

        let mut skills = Vec::new();
        for asset in &self.skills {
            let skill: Skill = asset.header()?;
            if skill.stages.contains(&stage) {
                skills.push(json!({
                    "identity": asset.preview_identity("skill"),
                    "description": skill.description,
                    "content": asset.document()?.1,
                }));
            }
        }
        Ok(json!({
            "stage": stage,
            "playbook": self.playbook.preview_identity("playbook"),
            "playbook_guidance": self.playbook.document()?.1,
            "skills": skills,
        }))
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
