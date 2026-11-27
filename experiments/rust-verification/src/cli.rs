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

pub fn execute(args: &[OsString]) -> Result<i32> {
    let [command, args @ ..] = args else {
        return Err("expected harborist run or intake".into());
    };
    let command = command.to_str().ok_or("invalid Harborist command")?;
    if command == "--help" || command == "-h" {
        println!("Usage: harborist <run|intake> SOURCE_OR_RUN_ID [OPTIONS]");
        return Ok(0);
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
