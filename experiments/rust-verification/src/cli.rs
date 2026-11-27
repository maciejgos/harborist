//! User-facing Rust entry points, backed by the same capture and worker APIs.

use crate::{Result, control, queue, store};
use harborist_verify::workflow::Sha;
use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
};
use uuid::Uuid;

#[derive(Default)]
struct RunOptions {
    source: Option<OsString>,
    repository: Option<PathBuf>,
    settings: Option<PathBuf>,
    runs: Option<PathBuf>,
    control: Option<PathBuf>,
    reference: Option<String>,
    total: Option<u64>,
    reserve: Option<u64>,
    foreground: bool,
    json: bool,
}

impl RunOptions {
    fn parse(args: &[OsString]) -> Result<Self> {
        let mut options = Self::default();
        let mut args = args.iter();
        while let Some(arg) = args.next() {
            let value = |args: &mut std::slice::Iter<'_, OsString>| {
                args.next()
                    .cloned()
                    .ok_or_else(|| format!("{} requires a value", arg.to_string_lossy()))
            };
            match arg.to_str() {
                Some("--foreground") => options.foreground = true,
                Some("--json") => options.json = true,
                Some("--repo") => options.repository = Some(value(&mut args)?.into()),
                Some("--settings") => options.settings = Some(value(&mut args)?.into()),
                Some("--runs-dir") => options.runs = Some(value(&mut args)?.into()),
                Some("--control-dir") => options.control = Some(value(&mut args)?.into()),
                Some("--ref") => {
                    options.reference = Some(
                        value(&mut args)?
                            .into_string()
                            .map_err(|_| "invalid Git ref")?,
                    )
                }
                Some("--timeout") => options.total = Some(seconds(&value(&mut args)?)?),
                Some("--verification-reserve") => {
                    options.reserve = Some(seconds(&value(&mut args)?)?)
                }
                Some(flag) if flag.starts_with('-') => {
                    return Err(format!("unknown option {flag}").into());
                }
                _ if options.source.is_none() => options.source = Some(arg.clone()),
                _ => return Err("expected one source or Run UUID".into()),
            }
        }
        Ok(options)
    }

    fn capture(&self, root: &Path, existing: bool) -> Result<store::Captured> {
        let source = self
            .source
            .as_ref()
            .ok_or("expected a source or Run UUID")?;
        if let Some(id) = source
            .to_str()
            .and_then(|value| Uuid::parse_str(value).ok())
        {
            if !existing
                || self.settings.is_some()
                || self.reference.is_some()
                || self.total.is_some()
                || self.reserve.is_some()
            {
                return Err("capture options require a source".into());
            }
            let capture = store::load(&root.join(id.to_string()))?;
            if capture.contract.run_id != id
                || self.repository.as_ref().is_some_and(|path| {
                    store::repository(path).ok().as_ref() != Some(&capture.contract.repository)
                })
            {
                return Err("saved Run does not match the requested context".into());
            }
            return Ok(capture);
        }
        let repository = store::repository(self.repository.as_deref().unwrap_or(Path::new(".")))?;
        let reference = self.reference.as_deref().unwrap_or("HEAD");
        let base: Sha = crate::git_text(
            &repository,
            &[
                "rev-parse",
                "--verify",
                "--end-of-options",
                &format!("{reference}^{{commit}}"),
            ],
        )?
        .parse()?;
        fs::create_dir_all(root)?;
        let run_id = Uuid::new_v4();
        store::capture_to(store::Capture {
            repository: &repository,
            base_sha: base,
            source,
            directory: &root.join(run_id.to_string()),
            settings: self.settings.as_deref(),
            run_id,
            total_seconds: self.total.unwrap_or(store::TOTAL_SECONDS),
            verification_reserve_seconds: self
                .reserve
                .unwrap_or(store::VERIFICATION_RESERVE_SECONDS),
        })
    }
}

fn seconds(value: &OsString) -> Result<u64> {
    Ok(value.to_str().ok_or("invalid time in seconds")?.parse()?)
}

fn state_path(name: &str) -> Result<PathBuf> {
    let home = std::env::var_os("HOME").ok_or("home directory is unavailable")?;
    Ok(PathBuf::from(home).join(".harborist").join(name))
}

fn read_status(command: &str, args: &[OsString]) -> Result<i32> {
    let mut id = None;
    let mut directory = None;
    let mut wait = false;
    let mut json = false;
    let mut interval = 1.0;
    let mut args = args.iter();
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--help" | "-h") => {
                if command == "runs" {
                    println!("Usage: harborist runs [--control-dir PATH] [--json]");
                } else {
                    println!(
                        "Usage: harborist status RUN_ID [--control-dir PATH] [--wait] [--interval SECONDS] [--json]"
                    );
                }
                return Ok(0);
            }
            Some("--control-dir") => {
                directory = Some(PathBuf::from(
                    args.next().ok_or("--control-dir needs a path")?,
                ))
            }
            Some("--json") => json = true,
            Some("--wait") if command == "status" => wait = true,
            Some("--no-wait") if command == "status" => wait = false,
            Some("--interval") if command == "status" => {
                interval = args
                    .next()
                    .and_then(|value| value.to_str())
                    .ok_or("missing polling interval")?
                    .parse()?;
                if !(0.01..=60.0).contains(&interval) {
                    return Err("polling interval must be between 0.01 and 60 seconds".into());
                }
            }
            Some(value) if command == "status" && id.is_none() && !value.starts_with('-') => {
                id = Some(Uuid::parse_str(value)?);
            }
            _ => {
                return Err(
                    format!("unexpected {command} argument: {}", arg.to_string_lossy()).into(),
                );
            }
        }
    }
    if command == "status" && id.is_none() {
        return Err("status requires a Run UUID".into());
    }
    let directory = match directory {
        Some(path) => path,
        None => state_path("control")?,
    };
    let route = id.map_or_else(|| "/runs".to_owned(), |id| format!("/runs/{id}"));
    loop {
        let record = control::read(&directory, &route)?;
        let terminal = match record["state"].as_str() {
            Some("FINISHED" | "FAILED" | "INTERRUPTED" | "CANCELLED") => true,
            Some("QUEUED" | "RUNNING") => false,
            _ => matches!(
                record["run"]["lifecycle"].as_str(),
                Some("COMPLETED" | "FAILED" | "CANCELLED")
            ),
        };
        if !wait || terminal {
            if json {
                println!("{record}");
            } else if command == "runs" {
                for run in record["runs"]
                    .as_array()
                    .ok_or("invalid Run list response")?
                {
                    print_run(run);
                }
            } else {
                print_run(&record);
            }
            return Ok(0);
        }
        std::thread::sleep(std::time::Duration::from_secs_f64(interval));
    }
}

fn print_run(record: &serde_json::Value) {
    let id = record["run"]["run_id"]
        .as_str()
        .or_else(|| record["submission"]["run_id"].as_str())
        .unwrap_or("unknown");
    let state = record["state"]
        .as_str()
        .or_else(|| record["run"]["lifecycle"].as_str())
        .unwrap_or("UNKNOWN");
    let outcome = record["run"]["outcome"].as_str().unwrap_or("");
    println!("{id} {state} {outcome}");
}

fn change_run(command: &str, args: &[OsString]) -> Result<i32> {
    use serde_json::json;

    let [id, args @ ..] = args else {
        return Err("expected a Run UUID".into());
    };
    if id == "--help" || id == "-h" {
        if command == "cancel" {
            println!("Usage: harborist cancel RUN_ID --reason TEXT [--control-dir PATH]");
        } else {
            println!(
                "Usage: harborist {command} RUN_ID [--expected-attempt UUID] [--additional-seconds N] [--feedback TEXT] [--control-dir PATH] [--json]"
            );
        }
        return Ok(0);
    }
    let id = Uuid::parse_str(id.to_str().ok_or("invalid Run UUID")?)?;
    let mut directory = None;
    let mut reason = None;
    let mut feedback = String::new();
    let mut additional = 0;
    let mut observation = None;
    let mut feedback_ids = Vec::new();
    let mut expected = None;
    let mut json_output = false;
    let mut args = args.iter();
    while let Some(flag) = args.next() {
        let mut value = || args.next().ok_or("missing argument value");
        match flag.to_str() {
            Some("--control-dir") => directory = Some(PathBuf::from(value()?)),
            Some("--json") => json_output = true,
            Some("--reason") if command == "cancel" => {
                reason = Some(value()?.to_str().ok_or("invalid cancellation reason")?);
            }
            Some("--feedback") if command != "cancel" => {
                feedback = value()?.to_str().ok_or("invalid feedback")?.to_owned();
            }
            Some("--observation") if command == "rework" => {
                observation = Some(PathBuf::from(value()?));
            }
            Some("--feedback-id") if command == "rework" => {
                feedback_ids.push(value()?.to_str().ok_or("invalid feedback ID")?);
            }
            Some("--additional-seconds") if command != "cancel" => {
                additional = seconds(value()?)?;
            }
            Some("--expected-attempt") if command != "cancel" => {
                expected = Some(Uuid::parse_str(
                    value()?.to_str().ok_or("invalid Attempt UUID")?,
                )?);
            }
            _ => {
                return Err(
                    format!("unexpected {command} argument: {}", flag.to_string_lossy()).into(),
                );
            }
        }
    }
    let directory = match directory {
        Some(path) => path,
        None => state_path("control")?,
    };
    let (route, payload) = if command == "cancel" {
        let reason = crate::retirement::validate_reason(reason.ok_or("cancel requires --reason")?)?;
        (
            format!("/workspace/runs/{id}/cancel"),
            json!({"reason": reason}),
        )
    } else {
        if observation.is_some() == feedback_ids.is_empty() {
            return Err("--observation and --feedback-id must be supplied together".into());
        }
        let github_feedback =
            observation.map(|path| json!({"observation": path, "ids": feedback_ids}));
        let attempt = match expected {
            Some(id) => id,
            None => {
                let current = control::read(&directory, &format!("/runs/{id}"))?;
                Uuid::parse_str(
                    current["attempt_id"]
                        .as_str()
                        .ok_or("Run has no current Attempt")?,
                )?
            }
        };
        (
            format!("/workspace/runs/{id}/continue"),
            json!({
                "request_id": Uuid::new_v4(), "action": command, "expected_attempt_id": attempt,
                "feedback": feedback, "additional_seconds": additional, "github_feedback": github_feedback
            }),
        )
    };
    let response = control::write(&directory, &route, &payload)?;
    if json_output {
        println!("{response}");
    } else if command == "cancel" {
        println!("Recorded cancellation for Run {id}");
    } else {
        println!("Queued {command} for Run {id}");
    }
    Ok(0)
}

fn apply(args: &[OsString]) -> Result<i32> {
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("Usage: harborist apply RUN_ID --branch BRANCH [--repo PATH] [--runs-dir PATH]");
        return Ok(0);
    }
    let [id, options @ ..] = args else {
        return Err("apply requires a Run UUID".into());
    };
    let id = Uuid::parse_str(id.to_str().ok_or("invalid Run UUID")?)?;
    let mut branch = None;
    let mut repository = None;
    let mut runs = None;
    let mut options = options.iter();
    while let Some(flag) = options.next() {
        let value = options.next().ok_or("missing application option value")?;
        match flag.to_str() {
            Some("--branch") => branch = Some(value.to_str().ok_or("invalid branch name")?),
            Some("--repo") => repository = Some(Path::new(value)),
            Some("--runs-dir") => runs = Some(Path::new(value)),
            _ => {
                return Err(
                    format!("unexpected apply argument: {}", flag.to_string_lossy()).into(),
                );
            }
        }
    }
    let branch = branch.ok_or("apply requires --branch")?;
    let directory = saved_directory(id, runs)?;
    crate::apply::apply_saved(&directory, branch, Some(id), repository)?;
    Ok(0)
}

fn saved_directory(id: Uuid, runs: Option<&Path>) -> Result<PathBuf> {
    Ok(match runs {
        Some(root) => root.join(id.to_string()),
        None => {
            let saved = state_path("runs")?.join(id.to_string());
            if saved.try_exists()? {
                saved
            } else {
                let file = state_path("control")?
                    .join("queue")
                    .join(format!("{id}.json"));
                queue::read(&file)?.directory
            }
        }
    })
}

fn publish(args: &[OsString]) -> Result<i32> {
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!(
            "Usage: harborist publish RUN_ID --approve SHA --destination OWNER/REPO --base BRANCH [--expect-head SHA] [--runs-dir PATH]"
        );
        return Ok(0);
    }
    let [id, options @ ..] = args else {
        return Err("publish requires a Run UUID".into());
    };
    let id = Uuid::parse_str(id.to_str().ok_or("invalid Run UUID")?)?;
    let mut approve = None;
    let mut destination = None;
    let mut base = None;
    let mut expect_head = None;
    let mut runs = None;
    let mut options = options.iter();
    while let Some(flag) = options.next() {
        let value = options.next().ok_or("missing publication option value")?;
        match flag.to_str() {
            Some("--approve") => approve = Some(crate::commit(value)?),
            Some("--destination") => {
                destination = Some(value.to_str().ok_or("invalid destination")?.to_owned())
            }
            Some("--base") => base = Some(value.to_str().ok_or("invalid base branch")?.to_owned()),
            Some("--expect-head") => expect_head = Some(crate::commit(value)?),
            Some("--runs-dir") => runs = Some(Path::new(value)),
            _ => {
                return Err(
                    format!("unexpected publish argument: {}", flag.to_string_lossy()).into(),
                );
            }
        }
    }
    let request = crate::publication::PublishRequest {
        approve: approve.ok_or("publish requires --approve")?,
        destination: destination.ok_or("publish requires --destination")?,
        base: base.ok_or("publish requires --base")?,
        expected_attempt: None,
        expect_head,
    };
    crate::publication::publish_saved(&saved_directory(id, runs)?, Some(id), request)?;
    Ok(0)
}

fn github_status(args: &[OsString]) -> Result<i32> {
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("Usage: harborist github-status RUN_ID [--runs-dir PATH]");
        return Ok(0);
    }
    let (id, root) = match args {
        [id] => (id, None),
        [id, flag, path] if flag == "--runs-dir" => (id, Some(Path::new(path))),
        _ => return Err("expected harborist github-status RUN_ID [--runs-dir PATH]".into()),
    };
    let id = Uuid::parse_str(id.to_str().ok_or("invalid Run UUID")?)?;
    let result = crate::publication::observe(&saved_directory(id, root)?, id)?;
    println!("{}", result["observation"]);
    eprintln!(
        "{}",
        result["observation_path"]
            .as_str()
            .ok_or("missing saved observation path")?
    );
    Ok(0)
}

fn supersede(args: &[OsString]) -> Result<i32> {
    use serde_json::json;

    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!(
            "Usage: harborist supersede RUN_ID [SOURCE | --replacement RUN_ID] --reason TEXT [OPTIONS]"
        );
        return Ok(0);
    }
    let [id, args @ ..] = args else {
        return Err("supersede requires the original Run UUID".into());
    };
    let id = Uuid::parse_str(id.to_str().ok_or("invalid Run UUID")?)?;
    let mut reason = None;
    let mut replacement = None;
    let mut capture = Vec::new();
    let mut args = args.iter();
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--reason") => {
                reason = Some(
                    args.next()
                        .and_then(|value| value.to_str())
                        .ok_or("invalid reason")?,
                )
            }
            Some("--replacement") => {
                replacement = Some(Uuid::parse_str(
                    args.next()
                        .and_then(|value| value.to_str())
                        .ok_or("invalid replacement UUID")?,
                )?)
            }
            Some(
                "--control-dir"
                | "--runs-dir"
                | "--repo"
                | "--settings"
                | "--ref"
                | "--timeout"
                | "--verification-reserve",
            ) => {
                capture.push(arg.clone());
                capture.push(
                    args.next()
                        .ok_or("missing supersession option value")?
                        .clone(),
                );
            }
            _ => capture.push(arg.clone()),
        }
    }
    let options = RunOptions::parse(&capture)?;
    if options.foreground || options.json {
        return Err("unsupported supersession mode".into());
    }
    let reason = crate::retirement::validate_reason(reason.ok_or("supersede requires --reason")?)?;
    let directory = match options.control {
        Some(path) => path,
        None => state_path("control")?,
    };
    let current = control::read(&directory, &format!("/runs/{id}"))?;
    let repository = PathBuf::from(
        current["repository"]
            .as_str()
            .ok_or("original Run has no saved repository")?,
    );
    if let Some(path) = options.repository {
        if store::repository(&path)? != repository {
            return Err("original Run does not match the requested repository".into());
        }
    }
    if let Some(root) = options.runs {
        if current["submission"]["runs_root"].as_str().map(Path::new)
            != Some(root.canonicalize()?.as_path())
        {
            return Err("original Run does not match the requested Runs root".into());
        }
    }
    let payload = match (options.source, replacement) {
        (None, Some(replacement))
            if options.settings.is_none()
                && options.reference.is_none()
                && options.total.is_none()
                && options.reserve.is_none() =>
        {
            json!({"reason": reason, "replacement": replacement})
        }
        (Some(source), None) => {
            let source = source.to_str().ok_or("invalid replacement source")?;
            let source = if source.starts_with("github:") || source.starts_with("https://") {
                source.to_owned()
            } else {
                let path = Path::new(source.strip_prefix("file:").unwrap_or(source));
                if path.starts_with("~") {
                    path.to_owned()
                } else {
                    path.canonicalize()?
                }
                .to_str()
                .ok_or("invalid replacement file path")?
                .to_owned()
            };
            let settings = options
                .settings
                .map(|path| path.canonicalize())
                .transpose()?;
            json!({
                "request_id": Uuid::new_v4(), "reason": reason, "source": source,
                "repository": repository, "settings": settings,
                "ref": options.reference.unwrap_or_else(|| "HEAD".into()),
                "timeout": options.total.unwrap_or(store::TOTAL_SECONDS),
                "verification_reserve": options.reserve.unwrap_or(store::VERIFICATION_RESERVE_SECONDS),
            })
        }
        _ => {
            return Err(
                "supply exactly one source or a saved replacement without capture options".into(),
            );
        }
    };
    println!(
        "{}",
        control::write(
            &directory,
            &format!("/workspace/runs/{id}/supersede"),
            &payload
        )?
    );
    Ok(0)
}

fn web(args: &[OsString]) -> Result<i32> {
    let mut directory = None;
    let mut port = OsString::from("8765");
    let mut container_listener = false;
    let mut args = args.iter();
    while let Some(flag) = args.next() {
        let mut value = || args.next().cloned().ok_or("missing web option value");
        match flag.to_str() {
            Some("--help" | "-h") => {
                println!("Usage: harborist web [--control-dir PATH] [--port PORT]");
                return Ok(0);
            }
            Some("--control-dir") => directory = Some(PathBuf::from(value()?)),
            Some("--port") => port = value()?,
            Some("--container-listener") => container_listener = true,
            _ => return Err(format!("unexpected web argument: {}", flag.to_string_lossy()).into()),
        }
    }
    let directory = match directory {
        Some(path) => path,
        None => state_path("control")?,
    };
    control::require_service(&directory)?;
    let mut arguments = vec![directory.into_os_string(), port];
    if container_listener {
        arguments.push("--container-listener".into());
    }
    control::web(&arguments)?;
    Ok(0)
}

fn service(args: &[OsString]) -> Result<i32> {
    let (command, args) = match args {
        [command, args @ ..] if matches!(command.to_str(), Some("serve" | "status" | "stop")) => {
            (command, args)
        }
        [flag] if flag == "--help" || flag == "-h" => {
            println!("Usage: harborist service status [--control-dir PATH]");
            return Ok(0);
        }
        _ => {
            return Err(
                "expected harborist service <serve|status|stop> [--control-dir PATH]".into(),
            );
        }
    };
    let directory = match args {
        [] => state_path("control")?,
        [flag, directory] if flag == "--control-dir" => PathBuf::from(directory),
        [flag] if flag == "--help" || flag == "-h" => {
            println!(
                "Usage: harborist service {} [--control-dir PATH]",
                command.to_string_lossy()
            );
            return Ok(0);
        }
        _ => {
            return Err(
                "expected harborist service <serve|status|stop> [--control-dir PATH]".into(),
            );
        }
    };
    match command.to_str() {
        Some("serve") => control::serve_managed(&directory)?,
        Some("stop") => println!(
            "{}",
            control::write(&directory, "/shutdown", &serde_json::json!({}))?
        ),
        _ => println!("{}", control::read(&directory, "/health")?),
    }
    Ok(0)
}

pub fn execute(args: &[OsString]) -> Result<i32> {
    let [command, args @ ..] = args else {
        return Err("expected a Harborist command".into());
    };
    let command = command.to_str().ok_or("invalid Harborist command")?;
    if command == "--help" || command == "-h" {
        println!(
            "Usage: harborist <run|intake|runs|status|cancel|rework|recover|apply|publish|github-status|supersede|service|web> [OPTIONS]"
        );
        return Ok(0);
    }
    if command == "service" {
        return service(args);
    }
    if command == "web" {
        return web(args);
    }
    if command == "supersede" {
        return supersede(args);
    }
    if command == "github-status" {
        return github_status(args);
    }
    if command == "publish" {
        return publish(args);
    }
    if command == "apply" {
        return apply(args);
    }
    if matches!(command, "runs" | "status") {
        return read_status(command, args);
    }
    if matches!(command, "cancel" | "rework" | "recover") {
        return change_run(command, args);
    }
    if !matches!(command, "run" | "intake") {
        return Err(format!("unsupported Harborist command: {command}").into());
    }
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!(
            "Usage: harborist {command} SOURCE_OR_RUN_ID [--repo PATH] [--ref REF] [--settings PATH] [--runs-dir PATH] [--control-dir PATH] [--timeout SECONDS] [--verification-reserve SECONDS] [--foreground] [--json]"
        );
        return Ok(0);
    }
    let options = RunOptions::parse(args)?;
    let root = match &options.runs {
        Some(path) => path.clone(),
        None => state_path("runs")?,
    };
    let capture = options.capture(&root, command == "run")?;
    let id = capture.contract.run_id;
    if command == "intake" {
        if options.json {
            println!("{}", serde_json::to_string(&capture.contract)?);
        } else {
            println!("Captured Run {id}");
        }
        return Ok(0);
    }
    if !options.foreground {
        let directory = match options.control {
            Some(path) => path,
            None => state_path("control")?,
        };
        control::require_service(&directory)?;
        let delivery = queue::enqueue(&directory, capture)?;
        if options.json {
            println!("{}", serde_json::to_string(&delivery)?);
        } else {
            println!("Queued Run {id}");
        }
        return Ok(0);
    }
    let result = crate::foreground::execute(capture)?;
    if options.json {
        println!("{result}");
    } else {
        println!(
            "Run {id}: {}",
            result["outcome"].as_str().unwrap_or("FAILED")
        );
    }
    Ok(match result["outcome"].as_str() {
        Some("VERIFIED") => 0,
        Some("CANCELLED") => 130,
        Some("FAILED") | None => 1,
        _ => 2,
    })
}
