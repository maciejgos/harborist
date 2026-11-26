//! Read historical Python Run files without changing their layout or lifecycle.

use crate::{Result, continuation, record::read_artifact, store::digest};
use harborist_verify::workflow::{Attempt, Sha};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs, io,
    path::{Path, PathBuf},
};
use uuid::Uuid;

#[derive(Deserialize)]
struct Contract {
    run_id: Uuid,
    base_sha: Sha,
    intent: Intent,
    verification: Value,
}

#[derive(Deserialize)]
struct Intent {
    source_ref: String,
    source_url: Option<String>,
    markdown: String,
    artifact: IntentArtifact,
}

#[derive(Deserialize)]
struct IntentArtifact {
    run_id: Uuid,
    size_bytes: usize,
    sha256: String,
}

#[derive(Deserialize, Serialize, PartialEq)]
struct Snapshot {
    run_id: Uuid,
    lifecycle: Lifecycle,
    outcome: Option<String>,
    failure_reason: Option<String>,
    verification: Option<Value>,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum Lifecycle {
    Created,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Deserialize)]
struct Event {
    event_type: String,
    run: Snapshot,
}

fn snapshot(directory: &Path, id: Uuid) -> Result<Snapshot> {
    let saved: Snapshot = serde_json::from_str(&read_artifact(directory, "run.json")?)?;
    if saved.run_id != id {
        return Err("historical lifecycle belongs to another Run".into());
    }
    if !directory.join("events.jsonl").try_exists()? {
        return if saved.lifecycle == Lifecycle::Created && saved.valid() {
            Ok(saved)
        } else {
            Err("historical lifecycle lacks its journal".into())
        };
    }
    let journal = read_artifact(directory, "events.jsonl")?;
    let mut last = None;
    for line in journal.lines() {
        let event: Event = serde_json::from_str(line)?;
        let life = event.run.lifecycle;
        let valid = matches!(
            (
                last.as_ref().map(|run: &Snapshot| run.lifecycle),
                event.event_type.as_str(),
                life
            ),
            (None, "run_created", Lifecycle::Created)
                | (Some(Lifecycle::Created), "run_started", Lifecycle::Running)
                | (
                    Some(Lifecycle::Running),
                    "run_completed",
                    Lifecycle::Completed
                )
                | (
                    Some(Lifecycle::Created | Lifecycle::Running),
                    "run_failed",
                    Lifecycle::Failed
                )
                | (
                    Some(Lifecycle::Created | Lifecycle::Running),
                    "run_cancelled",
                    Lifecycle::Cancelled
                )
        );
        if !valid || event.run.run_id != id || !event.run.valid() {
            return Err("historical lifecycle journal has an invalid transition".into());
        }
        last = Some(event.run);
    }
    if last.as_ref() != Some(&saved) {
        return Err("historical lifecycle snapshot disagrees with its journal".into());
    }
    Ok(saved)
}

impl Snapshot {
    fn valid(&self) -> bool {
        let outcome = self.outcome.as_deref();
        let verified = outcome == Some("VERIFIED");
        if self.verification.is_some() != verified {
            return false;
        }
        match self.lifecycle {
            Lifecycle::Completed => {
                self.failure_reason.is_none()
                    && matches!(
                        outcome,
                        Some(
                            "VERIFIED"
                                | "NEEDS_CLARIFICATION"
                                | "NEEDS_RESCOPING"
                                | "TEST_FAILED"
                                | "CHANGES_REQUIRED"
                        )
                    )
            }
            Lifecycle::Failed => self.failure_reason.is_some() && outcome.is_none(),
            _ => outcome.is_none() && self.failure_reason.is_none(),
        }
    }
}

fn validate_verification(
    contract: &Contract,
    attempt: Option<&Attempt>,
    verification: &Value,
) -> Result<Sha> {
    let attempt = attempt.ok_or("historical verification lacks its Attempt")?;
    let candidate: Sha =
        serde_json::from_value(verification["candidate"]["candidate_sha"].clone())?;
    let identity = json!(attempt.candidate(candidate.clone()));
    if verification["run_id"] != json!(contract.run_id)
        || verification["attempt"] != json!(attempt)
        || verification["candidate"] != identity
        || verification["review"]["candidate"] != identity
        || verification["verification"] != contract.verification
    {
        return Err("historical verification attribution does not match".into());
    }
    let required = contract.verification["config"]["checks"]
        .as_array()
        .ok_or("missing frozen checks")?;
    let captured = verification["checks"]
        .as_array()
        .ok_or("missing verification checks")?;
    if required.is_empty()
        || required.len() != captured.len()
        || !required.iter().zip(captured).all(|(a, b)| {
            a["id"].is_string()
                && a["command"].is_string()
                && a["id"] == b["id"]
                && a["command"] == b["command"]
                && b["passed"] == true
        })
    {
        return Err("historical verification lacks passing mandatory checks".into());
    }
    let criteria = verification["specification"]["criterion_ids"]
        .as_array()
        .ok_or("missing criteria")?;
    let assessed = verification["review"]["criteria"]
        .as_array()
        .ok_or("missing assessments")?;
    let ids = criteria
        .iter()
        .map(Value::as_str)
        .collect::<Option<std::collections::BTreeSet<_>>>()
        .ok_or("invalid required criterion IDs")?;
    let covered = assessed
        .iter()
        .map(|item| {
            (item["status"] == "pass")
                .then(|| item["criterion_id"].as_str())
                .flatten()
        })
        .collect::<Option<std::collections::BTreeSet<_>>>()
        .ok_or("invalid criterion assessments")?;
    if ids.is_empty()
        || ids != covered
        || ids.len() != criteria.len()
        || covered.len() != assessed.len()
    {
        return Err("historical verification lacks passing criterion coverage".into());
    }
    Ok(candidate)
}

pub fn numbers(root: &Path) -> Result<Vec<u32>> {
    let path = root.join("attempts");
    if !path.try_exists()? {
        return Ok(vec![0]);
    }
    if path.canonicalize()? != path {
        return Err("historical Attempt path is not regular".into());
    }
    let mut list = vec![0];
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let number = entry
            .file_name()
            .to_str()
            .and_then(|name| name.parse::<u32>().ok())
            .ok_or("invalid historical Attempt number")?;
        if number == 0
            || !entry.file_type()?.is_dir()
            || entry.file_name() != format!("{number:06}").as_str()
        {
            return Err("invalid historical Attempt directory".into());
        }
        list.push(number);
    }
    list.sort_unstable();
    if list
        .iter()
        .enumerate()
        .any(|(index, number)| index != *number as usize)
    {
        return Err("historical Attempt history has gaps".into());
    }
    Ok(list)
}

pub fn select(root: &Path, number: Option<u32>) -> Result<(u32, PathBuf)> {
    let numbers = numbers(root)?;
    let number = number.unwrap_or(*numbers.last().expect("initial Attempt"));
    if !numbers.contains(&number) {
        return Err("historical Attempt does not exist".into());
    }
    Ok((number, continuation::attempt_path(root, number)))
}

pub fn view(root: &Path, id: Uuid, number: Option<u32>) -> Result<Value> {
    let (number, directory) = select(root, number)?;
    let mut result = json!({
        "version":1, "source":"saved", "submission":{"run_id":id,"runs_root":root.parent()},
        "state": null, "run": null, "attempt_number": number, "stages": {},
        "stage_errors": {}, "artifacts": {}, "package_available": false,
    });
    if let Err(error) = populate(root, &directory, id, number, &mut result) {
        result["run_error"] = json!(error.to_string());
    }
    Ok(result)
}

fn populate(
    root: &Path,
    directory: &Path,
    id: Uuid,
    number: u32,
    result: &mut Value,
) -> Result<()> {
    let original = read_artifact(root, "contract.json")?;
    let raw = read_artifact(directory, "contract.json")?;
    if serde_json::from_str::<Value>(&original)? != serde_json::from_str::<Value>(&raw)? {
        return Err("historical Attempt changed the frozen contract".into());
    }
    let contract: Contract = serde_json::from_str(&raw)?;
    let intent = &contract.intent;
    if contract.run_id != id
        || intent.artifact.run_id != id
        || contract.verification["base_sha"] != json!(contract.base_sha)
        || intent.artifact.size_bytes != intent.markdown.len()
        || intent.artifact.sha256 != digest(intent.markdown.as_bytes())
        || read_artifact(directory, "intent.md")? != intent.markdown
    {
        return Err("historical contract or intent does not match this Run".into());
    }
    result["title"] = json!(
        intent
            .markdown
            .lines()
            .find(|line| !line.trim().is_empty())
            .unwrap_or("Untitled request")
            .trim()
            .trim_start_matches(['#', ' '])
            .chars()
            .take(200)
            .collect::<String>()
    );
    if let Some(url) = &intent.source_url {
        if crate::github::selector(url).is_ok() {
            result["source_url"] = json!(url);
            result["source_ref"] = json!(intent.source_ref);
        }
    }
    let saved = snapshot(directory, id)?;
    let attempt: Option<Attempt> = if directory.join("attempt.json").try_exists()? {
        Some(serde_json::from_str(&read_artifact(
            directory,
            "attempt.json",
        )?)?)
    } else {
        None
    };
    if let Some(attempt) = &attempt {
        if attempt.run_id() != id || (number == 0 && attempt.start_sha() != &contract.base_sha) {
            return Err("historical Attempt attribution does not match".into());
        }
    }
    if let Some(verification) = &saved.verification {
        result["candidate_sha"] = json!(validate_verification(
            &contract,
            attempt.as_ref(),
            verification
        )?);
    }
    let terminal = matches!(
        saved.lifecycle,
        Lifecycle::Completed | Lifecycle::Failed | Lifecycle::Cancelled
    );
    result["run"] = json!(saved);
    result["attempt_id"] = json!(attempt.as_ref().map(Attempt::id));
    for name in ["report.md", "evidence.json"] {
        if terminal && read_artifact(directory, name).is_ok() {
            result["artifacts"][name] = json!(directory.join(name));
        }
    }
    result["package_available"] = json!(
        result["artifacts"]
            .as_object()
            .is_some_and(|files| files.len() == 2)
    );
    result["has_specification"] = json!(specification(directory).is_ok());
    Ok(())
}

fn specification(directory: &Path) -> Result<String> {
    let name = if directory.join("frozen-spec.md").try_exists()? {
        "frozen-spec.md"
    } else {
        "design/spec.md"
    };
    read_artifact(directory, name)
}

pub fn artifact(root: &Path, id: Uuid, number: Option<u32>, name: &str) -> Result<Value> {
    let (_, directory) = select(root, number)?;
    let view = view(root, id, number)?;
    if !matches!(
        view["run"]["lifecycle"].as_str(),
        Some("COMPLETED" | "FAILED" | "CANCELLED")
    ) {
        return Err("historical terminal artifacts are unavailable".into());
    }
    let content = match name {
        "report.md" | "evidence.json" => read_artifact(&directory, name)?,
        "spec.md" => specification(&directory)?,
        _ => return Err("unsupported historical artifact".into()),
    };
    Ok(json!({"name": name, "content": content}))
}

pub fn locate(root: &Path, id: Uuid) -> Result<PathBuf> {
    let directory = root.join(id.to_string());
    let metadata = fs::symlink_metadata(&directory)?;
    if !metadata.is_dir() || !directory.join("run.json").is_file() {
        return Err("historical Run does not exist".into());
    }
    Ok(directory)
}

pub fn ids(root: &Path) -> Result<Vec<Uuid>> {
    let entries = match fs::read_dir(root) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(error.into()),
    };
    let mut ids = Vec::new();
    for entry in entries {
        let entry = entry?;
        if let Some(id) = entry
            .file_name()
            .to_str()
            .and_then(|name| Uuid::parse_str(name).ok())
        {
            if entry.file_type()?.is_dir() && entry.path().join("run.json").is_file() {
                ids.push(id);
            }
        }
    }
    ids.sort_unstable();
    Ok(ids)
}

pub fn default_root() -> Option<PathBuf> {
    let home = PathBuf::from(std::env::var_os("HOME")?);
    let current = home.join(".harborist");
    let previous = home.join(".shipyard");
    Some(
        if !current.exists() && previous.is_dir() {
            previous
        } else {
            current
        }
        .join("runs"),
    )
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SavedContext {
    version: u32,
    run_id: Uuid,
    repository: PathBuf,
    runs_root: PathBuf,
}

pub fn import(args: &[std::ffi::OsString]) -> Result<()> {
    let [source, destination] = args else {
        return Err("expected import-python PYTHON_RUN_DIR NEW_RUST_RUN_DIR".into());
    };
    let source = Path::new(source).canonicalize()?;
    let root = source.parent().ok_or("historical Run has no root")?;
    let id = Uuid::parse_str(
        source
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("historical Run has no UUID directory name")?,
    )?;
    locate(root, id)?;
    let state = snapshot(&source, id)?;
    if state.lifecycle != Lifecycle::Created
        || numbers(&source)? != [0]
        || source.join("attempt.json").try_exists()?
        || root
            .join("retirements")
            .join(format!("{id}.json"))
            .try_exists()?
    {
        return Err(
            "only unstarted and unretired Python Runs can be imported for execution".into(),
        );
    }
    let view = view(&source, id, Some(0))?;
    if view["run"]["lifecycle"] != "CREATED" {
        return Err(format!("historical capture is invalid: {}", view["run_error"]).into());
    }
    let (capture, frozen) = execution_capture(&source, id)?;
    let directory =
        crate::store::new_directory(Path::new(destination), &capture.contract.repository)?;
    if directory.starts_with(&source) {
        return Err("import destination must be outside the original Run".into());
    }
    crate::store::save(&directory, &capture.contract, &capture.intent, &frozen)?;
    println!("{}", serde_json::to_string(&capture.contract)?);
    Ok(())
}

/// Reconstruct frozen execution inputs independently of the Run lifecycle.
/// Callers separately validate whether the requested lifecycle action is allowed.
fn execution_capture(source: &Path, id: Uuid) -> Result<(crate::store::Captured, Vec<u8>)> {
    let root = source.parent().ok_or("historical Run has no root")?;
    let raw = read_artifact(source, "contract.json")?;
    let contract: Contract = serde_json::from_str(&raw)?;
    let execution: crate::settings::LegacyExecution =
        serde_json::from_value(serde_json::from_str::<Value>(&raw)?["execution"].clone())?;
    let (execution, total_seconds, verification_reserve_seconds) = execution.trusted_local()?;
    let context: SavedContext =
        serde_json::from_str(&read_artifact(source, "execution-context.json")?)?;
    if context.version != 1
        || context.run_id != id
        || context.runs_root != root
        || !context.repository.is_absolute()
        || crate::store::repository(&context.repository)? != context.repository
    {
        return Err("historical execution context does not match the Run or repository".into());
    }
    let frozen = crate::verification_source(&context.repository, &contract.base_sha)?;
    let source_sha256 = digest(&frozen);
    let config = crate::Config::parse(&frozen)?;
    if contract.verification["source_sha256"] != source_sha256
        || contract.verification["config"] != serde_json::to_value(&config)?
    {
        return Err("historical verification differs from the saved base commit".into());
    }
    if contract.run_id != id || contract.intent.markdown.trim().is_empty() {
        return Err("historical contract must match the Run and contain intent text".into());
    }
    let converted = crate::store::Contract {
        version: crate::store::VERSION,
        run_id: id,
        repository: context.repository,
        base_sha: contract.base_sha,
        intent_sha256: contract.intent.artifact.sha256,
        source_ref: Some(contract.intent.source_ref),
        source_url: contract.intent.source_url,
        source_sha256,
        total_seconds,
        verification_reserve_seconds,
        execution: Some(execution),
    };
    Ok((
        crate::store::Captured {
            directory: source.to_owned(),
            contract: converted,
            config,
            intent: contract.intent.markdown,
        },
        frozen,
    ))
}

#[derive(Deserialize)]
struct FileEntry {
    path: String,
    size_bytes: u64,
    sha256: String,
}

fn checked_index(directory: &Path, records: &Value) -> Result<std::collections::HashSet<String>> {
    use sha2::{Digest, Sha256};
    use std::io::Read;
    let entries: Vec<FileEntry> = serde_json::from_value(records.clone())?;
    let mut names = std::collections::HashSet::new();
    for entry in entries {
        if entry.path == "evidence.json"
            || entry.path.split('/').next() == Some("workspace")
            || entry
                .path
                .split('/')
                .any(|part| matches!(part, "" | "." | ".."))
            || !names.insert(entry.path.clone())
        {
            return Err("unsafe or duplicate historical evidence path".into());
        }
        let mut file = crate::record::open_artifact(directory, &entry.path)?;
        if file.metadata()?.len() != entry.size_bytes {
            return Err(
                format!("historical evidence length/digest mismatch: {}", entry.path).into(),
            );
        }
        let mut hasher = Sha256::new();
        let mut buffer = [0; 65536];
        let mut size = 0u64;
        loop {
            let count = file.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            size += count as u64;
            hasher.update(&buffer[..count]);
        }
        if size != entry.size_bytes || format!("{:x}", hasher.finalize()) != entry.sha256 {
            return Err(
                format!("historical evidence length/digest mismatch: {}", entry.path).into(),
            );
        }
    }
    Ok(names)
}

struct HistoricalPackage<'a> {
    directory: &'a Path,
    package: Value,
    index: std::collections::HashSet<String>,
    contract: Contract,
    saved: Snapshot,
    attempt: Attempt,
}

impl<'a> HistoricalPackage<'a> {
    fn load(directory: &'a Path, id: Uuid) -> Result<Self> {
        let package: Value = serde_json::from_str(&read_artifact(directory, "evidence.json")?)?;
        if package["version"] != 1 {
            return Err("historical PACKAGE version is invalid".into());
        }
        let index = checked_index(directory, &package["files"])?;
        let get = |name: &str| -> Result<String> {
            if !index.contains(name) {
                return Err(format!("historical evidence index lacks {name}").into());
            }
            read_artifact(directory, name)
        };
        for name in [
            "run.json",
            "contract.json",
            "events.jsonl",
            "intent.json",
            "intent.md",
            "attempt.json",
            "report.md",
        ] {
            get(name)?;
        }
        for name in [
            "workspace-layout.json",
            "execution-context.json",
            "execution-workspace.json",
        ] {
            if directory.join(name).symlink_metadata().is_ok() {
                get(name)?;
            }
        }
        let raw = get("contract.json")?;
        let contract: Contract = serde_json::from_str(&raw)?;
        let saved = snapshot(directory, id)?;
        let attempt: Attempt = serde_json::from_str(&get("attempt.json")?)?;
        if contract.run_id != id
            || attempt.run_id() != id
            || matches!(saved.lifecycle, Lifecycle::Created | Lifecycle::Running)
            || package["run"] != json!(saved)
            || package["contract"] != serde_json::from_str::<Value>(&raw)?
            || package["attempt"] != json!(attempt)
        {
            return Err("historical PACKAGE conflicts with the saved Attempt".into());
        }
        Ok(Self {
            directory,
            package,
            index,
            contract,
            saved,
            attempt,
        })
    }

    fn specification(&self) -> Result<Option<(String, bool)>> {
        let stages = self.package["stages"]
            .as_array()
            .ok_or("missing historical native stage captures")?;
        let mut designs = stages.iter().filter(|stage| {
            stage["stage"] == "design" && stage["output"]["result"]["status"] == "ready"
        });
        if let Some(design) = designs.next() {
            let spec = self.get("design/spec.md")?;
            let manifest: Value = serde_json::from_str(&self.get("design/manifest.json")?)?;
            if designs.next().is_some()
                || !self.package["reused_spec_sha256"].is_null()
                || design["run_id"] != json!(self.attempt.run_id())
                || design["attempt_id"] != json!(self.attempt.id())
                || design["output"]["result"]["stage"] != "design"
                || design["output"]["artifact"].as_str() != Some(spec.as_str())
                || manifest != *design
            {
                return Err("historical specification does not match DESIGN".into());
            }
            return Ok(Some((spec, false)));
        }
        if let Some(expected) = self.package["reused_spec_sha256"].as_str() {
            let record: Value = serde_json::from_str(&self.get("continuation.json")?)?;
            let spec = self.get("frozen-spec.md")?;
            if record["attempt"] != json!(self.attempt)
                || record["spec_digest"] != expected
                || digest(spec.as_bytes()) != expected
            {
                return Err("historical specification lineage does not match".into());
            }
            return Ok(Some((spec, true)));
        }
        Ok(None)
    }

    fn get(&self, name: &str) -> Result<String> {
        if !self.index.contains(name) {
            return Err(format!("historical evidence index lacks {name}").into());
        }
        read_artifact(self.directory, name)
    }
}

fn interrupted_spec(
    directory: &Path,
    attempt: &Attempt,
    contract: &Value,
    inherited: Option<&str>,
) -> Result<Option<String>> {
    if let Some(expected) = inherited {
        let spec = read_artifact(directory, "frozen-spec.md")?;
        if digest(spec.as_bytes()) != expected {
            return Err("historical inherited specification digest mismatch".into());
        }
        harborist_verify::review::Specification::parse(&spec)?;
        return Ok(Some(spec));
    }
    if !directory.join("design/manifest.json").try_exists()? {
        return Ok(None);
    }
    let manifest: Value = serde_json::from_str(&read_artifact(directory, "design/manifest.json")?)?;
    let attempt_id = json!(attempt.id());
    let run_id = json!(attempt.run_id());
    if manifest["run_id"] != run_id
        || manifest["attempt_id"] != attempt_id
        || manifest["stage"] != "design"
        || manifest["output"]["result"]["stage"] != "design"
        || manifest["output"]["result"]["status"] != "ready"
        || !manifest["candidate"].is_null()
        || !manifest["review_decision"].is_null()
    {
        return Err("historical interrupted DESIGN attribution mismatch".into());
    }
    let mut expected = Vec::new();
    for (name, kind) in [
        ("request.json", "log"),
        ("stdout.log", "log"),
        ("stderr.log", "log"),
        ("invocation.json", "log"),
        ("stage-result.json", "stage_result"),
        ("spec.md", "spec"),
    ] {
        use std::io::Read;
        let mut file = crate::record::open_artifact(directory, &format!("design/{name}"))?;
        let mut raw = Vec::new();
        (&mut file).take(2_097_153).read_to_end(&mut raw)?;
        if raw.len() > 2_097_152 {
            return Err(
                "historical interrupted DESIGN artifact exceeds the supported limit".into(),
            );
        }
        expected.push(json!([kind, raw.len(), digest(&raw)]));
    }
    let refs = manifest["artifacts"]
        .as_array()
        .ok_or("historical DESIGN has no artifact index")?;
    for reference in refs {
        let identity = json!([
            reference["kind"],
            reference["size_bytes"],
            reference["sha256"]
        ]);
        let position = expected
            .iter()
            .position(|expected| *expected == identity)
            .ok_or("historical interrupted DESIGN artifact digest mismatch")?;
        if reference["run_id"] != run_id
            || reference["attempt_id"] != attempt_id
            || reference["produced_by"] != "design"
        {
            return Err("historical interrupted DESIGN artifact ownership mismatch".into());
        }
        expected.swap_remove(position);
    }
    if !expected.is_empty() {
        return Err("historical interrupted DESIGN artifact index is incomplete".into());
    }
    let request: Value = serde_json::from_str(&read_artifact(directory, "design/request.json")?)?;
    let workspace_name = if directory.join("execution-workspace.json").try_exists()? {
        "execution-workspace.json"
    } else {
        "workspace.json"
    };
    let workspace: Value = serde_json::from_str(&read_artifact(directory, workspace_name)?)?;
    let result: Value =
        serde_json::from_str(&read_artifact(directory, "design/stage-result.json")?)?;
    let spec = read_artifact(directory, "design/spec.md")?;
    if request["stage"] != "design"
        || !request["candidate"].is_null()
        || request["profile"] != contract["execution"]["agent_profile"]
        || request["guidance"]["stage"] != "design"
        || request["inputs"]
            != json!([{"name": "intent.md", "content": contract["intent"]["markdown"]}])
        || workspace["version"] != 1
        || workspace["run_id"] != run_id
        || workspace["attempt_id"] != attempt_id
        || !workspace["path"]
            .as_str()
            .is_some_and(|path| Path::new(path).is_absolute())
        || request["workspace"] != workspace["path"]
        || result != manifest["output"]["result"]
        || spec != manifest["output"]["artifact"]
    {
        return Err("historical interrupted DESIGN does not match the frozen invocation".into());
    }
    harborist_verify::review::Specification::parse(&spec)?;
    Ok(Some(spec))
}

pub fn continue_run(args: &[std::ffi::OsString]) -> Result<()> {
    let (original, destination, request) = continuation_arguments(args)?;
    continuation::print_result(
        prepare_continuation(&original, &destination, &request)?.execute(&request)?,
    )
}

pub fn continuation_arguments(
    args: &[std::ffi::OsString],
) -> Result<(PathBuf, PathBuf, continuation::Request)> {
    let (action, original, destination, expected, feedback, extra) = match args {
        [action, original, destination, expected, feedback, extra @ ..] if extra.len() <= 1 =>
            (action, original, destination, expected, feedback, extra),
        _ => return Err("expected continue-python rework|recover PYTHON_RUN_DIR NEW_RUST_RUN_DIR EXPECTED_ATTEMPT FEEDBACK [ADDITIONAL_SECONDS]".into()),
    };
    let action = action.to_str().ok_or("invalid continuation action")?;
    let mut parsed = vec![original.clone(), expected.clone(), feedback.clone()];
    parsed.extend_from_slice(extra);
    let (original, request) = continuation::parse(action, &parsed)?;
    Ok((
        original.canonicalize()?,
        PathBuf::from(destination),
        request,
    ))
}

pub struct HistoricalContinuation {
    _lock: fs::File,
    capture: crate::store::Captured,
    frozen: Vec<u8>,
    pub destination: PathBuf,
    number: u32,
    start: Sha,
    rework: crate::foreground::Rework,
}

impl HistoricalContinuation {
    pub fn run_id(&self) -> Uuid {
        self.capture.contract.run_id
    }

    pub fn execute(self, request: &continuation::Request) -> Result<Value> {
        let Self {
            _lock,
            mut capture,
            frozen,
            destination,
            number,
            start,
            rework,
        } = self;
        crate::store::save(&destination, &capture.contract, &capture.intent, &frozen)?;
        capture.directory = destination;
        let _destination_lock = continuation::lock(&capture.directory)?;
        let directory = continuation::attempt_path(&capture.directory, number);
        continuation::execute_prepared(capture, directory, start, rework, request)
    }
}

pub fn prepare_continuation(
    original: &Path,
    destination: &Path,
    request: &continuation::Request,
) -> Result<HistoricalContinuation> {
    use std::os::fd::AsRawFd;
    let action = request.action.as_str();
    let original = original.canonicalize()?;
    let parent = original.parent().ok_or("historical Run has no root")?;
    let id = Uuid::parse_str(
        original
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("missing historical Run ID")?,
    )?;
    locate(parent, id)?;
    let lock = fs::File::open(&original)?;
    // Python uses the Run directory itself as the execution lock.
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if parent
        .join("retirements")
        .join(format!("{id}.json"))
        .try_exists()?
    {
        return Err("historical Run is retired".into());
    }
    let (number, directory) = select(&original, None)?;
    let (capture, frozen) = execution_capture(&original, id)?;
    let contract: Value = serde_json::from_str(&read_artifact(&original, "contract.json")?)?;
    let attempt: Attempt = serde_json::from_str(&read_artifact(&directory, "attempt.json")?)?;
    if attempt.id() != request.expected_attempt_id
        || attempt.run_id() != id
        || serde_json::from_str::<Value>(&read_artifact(&directory, "contract.json")?)? != contract
    {
        return Err("historical continuation predecessor or frozen contract changed".into());
    }
    let state = snapshot(&directory, id)?;
    let interrupted =
        state.lifecycle == Lifecycle::Running || !directory.join("evidence.json").try_exists()?;
    let continuation_record: Option<Value> = if number == 0 {
        None
    } else {
        let record: Value = serde_json::from_str(&read_artifact(&directory, "continuation.json")?)?;
        if record["attempt"] != json!(attempt) || record["previous_number"] != number - 1 {
            return Err("historical time grant belongs to another Attempt".into());
        }
        Some(record)
    };
    let prior_grants = continuation_record.as_ref().map_or(Ok(0), |record| {
        record["granted_seconds"]
            .as_u64()
            .ok_or("invalid historical time grant")
    })?;
    let original_allowance = capture
        .contract
        .total_seconds
        .checked_add(prior_grants)
        .ok_or("historical time budget overflow")?;
    let (candidate, spec, spent_seconds) = if interrupted {
        if action != "recover"
            || request.additional_seconds == 0
            || state.lifecycle == Lifecycle::Created
        {
            return Err(
                "interrupted historical Attempt requires explicit recovery with additional seconds"
                    .into(),
            );
        }
        let inherited = continuation_record
            .as_ref()
            .and_then(|record| record["spec_digest"].as_str());
        (
            None,
            interrupted_spec(&directory, &attempt, &contract, inherited)?,
            original_allowance,
        )
    } else {
        let previous = HistoricalPackage::load(&directory, id)?;
        if number != 0 {
            previous.get("continuation.json")?;
        }
        let spec = previous.specification()?.map(|(text, _)| text);
        let candidate = if previous.package["candidate"].is_null() {
            None
        } else {
            let sha: Sha =
                serde_json::from_value(previous.package["candidate"]["candidate_sha"].clone())?;
            if previous.package["candidate"] != json!(previous.attempt.candidate(sha.clone())) {
                return Err("historical candidate belongs to another Attempt".into());
            }
            let reference = if number == 0 {
                format!("refs/shipyard/runs/{id}/candidate")
            } else {
                format!(
                    "refs/shipyard/runs/{id}/attempts/{}/candidate",
                    previous.attempt.id()
                )
            };
            let repo = &capture.contract.repository;
            if crate::git_text(repo, &["rev-parse", "--verify", &reference])? != sha.as_str() {
                return Err("historical candidate ref changed".into());
            }
            crate::apply::exact_commit(repo, &sha)?;
            crate::git_text(
                repo,
                &[
                    "merge-base",
                    "--is-ancestor",
                    capture.contract.base_sha.as_str(),
                    sha.as_str(),
                ],
            )?;
            Some(sha)
        };
        match action {
            "rework"
                if previous.saved.lifecycle == Lifecycle::Completed
                    && matches!(
                        previous.saved.outcome.as_deref(),
                        Some("TEST_FAILED" | "CHANGES_REQUIRED")
                    )
                    && candidate.is_some()
                    && spec.is_some() =>
            {
                ()
            }
            "recover"
                if previous.saved.lifecycle == Lifecycle::Failed
                    && matches!(
                        previous.saved.failure_reason.as_deref(),
                        Some(
                            "EXECUTION_FAILED"
                                | "INVALID_STAGE_OUTPUT"
                                | "CREDENTIAL_UNAVAILABLE"
                                | "CREDENTIAL_REJECTED"
                        )
                    ) =>
            {
                ()
            }
            _ => {
                return Err(
                    "historical Attempt is not eligible for the requested continuation".into(),
                );
            }
        }
        let timing = &previous.package["timing"];
        let remaining = timing["remaining_seconds"]
            .as_f64()
            .ok_or("missing historical time accounting")?;
        if timing["original_seconds"] != original_allowance
            || !(0.0..=original_allowance as f64).contains(&remaining)
        {
            return Err("historical Package has inconsistent time accounting".into());
        }
        // The Rust executor budgets whole seconds. Round spending up to preserve the cap.
        (
            candidate,
            spec,
            original_allowance - remaining.floor() as u64,
        )
    };
    let granted_seconds = prior_grants
        .checked_add(request.additional_seconds)
        .ok_or("historical time grant overflow")?;
    let total = capture
        .contract
        .total_seconds
        .checked_add(granted_seconds)
        .ok_or("historical time budget overflow")?;
    if total > u32::MAX as u64
        || total.saturating_sub(spent_seconds) <= capture.contract.verification_reserve_seconds
    {
        return Err("insufficient historical continuation budget; grant additional seconds".into());
    }
    let context = serde_json::to_string_pretty(&json!({
        "previous_attempt": attempt.id(),
        "previous_candidate": candidate,
        "previous_outcome": state.outcome,
        "previous_evidence": (!interrupted).then(|| directory.join("evidence.json")),
        "feedback": request.feedback,
    }))?;
    let start = candidate.unwrap_or_else(|| attempt.start_sha().clone());
    crate::apply::exact_commit(&capture.contract.repository, &start)?;
    let destination =
        crate::store::new_directory(Path::new(destination), &capture.contract.repository)?;
    if destination.starts_with(&original) {
        return Err("continuation destination must be outside the original Run".into());
    }
    if destination.symlink_metadata().is_ok() {
        return Err("historical continuation destination already exists".into());
    }
    Ok(HistoricalContinuation {
        _lock: lock,
        capture,
        frozen,
        destination,
        number: number
            .checked_add(1)
            .ok_or("historical Attempt number overflow")?,
        start,
        rework: crate::foreground::Rework {
            context,
            specification: spec,
            spent_seconds,
            granted_seconds,
        },
    })
}

pub fn verified(root: &Path) -> Result<(Uuid, PathBuf, crate::apply::Verified)> {
    let parent = root.parent().ok_or("historical Run has no root")?;
    let id = Uuid::parse_str(
        root.file_name()
            .and_then(|name| name.to_str())
            .ok_or("historical Run has no UUID directory name")?,
    )?;
    locate(parent, id)?;
    if parent
        .join("retirements")
        .join(format!("{id}.json"))
        .try_exists()?
    {
        return Err("historical Run is retired".into());
    }
    let (number, directory) = select(root, None)?;
    let historical = HistoricalPackage::load(&directory, id)?;
    let package = &historical.package;
    if !package["error"].is_null() {
        return Err("historical PACKAGE outcome is invalid".into());
    }
    let contract = &historical.contract;
    let observed = view(root, id, Some(number))?;
    let attempt = &historical.attempt;
    let get = |name: &str| historical.get(name);
    let verification = historical
        .saved
        .verification
        .as_ref()
        .ok_or("historical Run lacks verification")?;
    let candidate: Sha = serde_json::from_value(observed["candidate_sha"].clone())?;
    let identity = json!(attempt.candidate(candidate.clone()));
    if observed["run"]["outcome"] != "VERIFIED" || package["candidate"] != identity {
        return Err("historical PACKAGE conflicts with validated verification".into());
    }
    let test_raw = get("test/manifest.json")?;
    let test: Value = serde_json::from_str(&test_raw)?;
    if package["test"] != test
        || test["run_id"] != json!(id)
        || test["attempt_id"] != json!(attempt.id())
        || test["verification"] != contract.verification
        || test["receipt"]["stage"] != "test"
        || test["receipt"]["outcome"] != "succeeded"
        || test["receipt"]["candidate"] != identity
        || test.get("workspace_error") != Some(&Value::Null)
    {
        return Err("historical TEST capture does not match PACKAGE".into());
    }
    let checks = test["collection"]["checks"]
        .as_array()
        .ok_or("missing historical TEST checks")?;
    let approved = verification["checks"]
        .as_array()
        .ok_or("missing historical passing checks")?;
    if checks.len() != approved.len() {
        return Err("historical TEST checks differ from verification".into());
    }
    for (position, (check, expected)) in checks.iter().zip(approved).enumerate() {
        if check["id"] != expected["id"]
            || check["command"] != expected["command"]
            || check["returncode"] != 0
            || check["timed_out"] != false
            || !check["error"].is_null()
        {
            return Err("historical TEST checks did not pass".into());
        }
        for stream in ["stdout", "stderr"] {
            let name = format!("test/logs/{position:04}.{stream}.log");
            if !historical.index.contains(&name)
                || check[format!("{stream}_path")] != json!(directory.join(&name))
            {
                return Err("historical TEST log attribution does not match".into());
            }
        }
    }
    let (spec, reused_spec) = historical
        .specification()?
        .ok_or("historical verified Run has no frozen specification")?;
    let parsed = harborist_verify::review::Specification::parse(&spec)?;
    if verification["specification"]["sha256"] != parsed.sha256()
        || verification["specification"]["criterion_ids"] != json!(parsed.criterion_ids())
    {
        return Err("historical specification does not match verification".into());
    }
    let stages = package["stages"]
        .as_array()
        .ok_or("missing historical native stage captures")?;
    let expected_stages: &[&str] = if reused_spec {
        &["plan", "build", "review"]
    } else {
        &["design", "plan", "build", "review"]
    };
    if stages.len() != expected_stages.len() {
        return Err("historical PACKAGE lacks the canonical stage captures".into());
    }
    for (stage, name) in stages.iter().zip(expected_stages) {
        if stage["stage"] != *name
            || stage["run_id"] != json!(id)
            || stage["attempt_id"] != json!(attempt.id())
            || stage["output"]["result"]["stage"] != *name
            || stage["output"]["result"]["status"] != "ready"
            || serde_json::from_str::<Value>(&get(&format!("{name}/manifest.json"))?)? != *stage
            || serde_json::from_str::<Value>(&get(&format!("{name}/stage-result.json"))?)?
                != stage["output"]["result"]
        {
            return Err("historical native stage capture conflicts with PACKAGE".into());
        }
    }
    let review = stages.last().ok_or("historical Run lacks REVIEW")?;
    let request: Value = serde_json::from_str(&get("review/request.json")?)?;
    let inputs = request["inputs"]
        .as_array()
        .ok_or("missing historical REVIEW inputs")?;
    let input = |name: &str| {
        inputs
            .iter()
            .find(|item| item["name"] == name)
            .and_then(|item| item["content"].as_str())
    };
    if request["candidate"] != identity
        || input("spec.md") != Some(spec.as_str())
        || input("test-evidence.json") != Some(test_raw.as_str())
        || review["test_evidence_sha256"] != digest(test_raw.as_bytes())
        || review["output"]["result"] != verification["review"]
        || review["review_decision"]["verification"] != *verification
    {
        return Err("historical REVIEW does not match the exact TEST and candidate".into());
    }
    let context: SavedContext =
        serde_json::from_str(&read_artifact(root, "execution-context.json")?)?;
    let repo = context.repository;
    if context.version != 1
        || context.run_id != id
        || context.runs_root != parent
        || !repo.is_absolute()
        || crate::store::repository(&repo)? != repo
    {
        return Err("historical execution context does not match the Run or repository".into());
    }
    crate::apply::exact_commit(&repo, &contract.base_sha)?;
    crate::apply::exact_commit(&repo, &candidate)?;
    let candidate_ref = if number == 0 {
        format!("refs/shipyard/runs/{id}/candidate")
    } else {
        format!(
            "refs/shipyard/runs/{id}/attempts/{}/candidate",
            attempt.id()
        )
    };
    if crate::git_text(&repo, &["rev-parse", "--verify", &candidate_ref])? != candidate.as_str() {
        return Err("historical Run-owned candidate ref does not match verification".into());
    }
    crate::git_text(
        &repo,
        &[
            "merge-base",
            "--is-ancestor",
            contract.base_sha.as_str(),
            candidate.as_str(),
        ],
    )?;
    Ok((
        id,
        repo,
        crate::apply::Verified {
            candidate,
            candidate_ref,
            directory,
            attempt: attempt.id(),
        },
    ))
}
