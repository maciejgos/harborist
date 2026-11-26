use crate::{
    Config, Evidence, Result, commit, git,
    native::{Codex, NativeAgent, Output, Request},
    run_checks_with_budget,
};
use harborist_verify::{
    review::{Review, Specification},
    workflow::{Attempt, Outcome, Receipt, Sha, Stage, Workflow},
};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    ffi::{OsStr, OsString},
    fs,
    path::Path,
    time::{Duration, Instant},
};
use uuid::Uuid;

pub fn execute(args: &[OsString]) -> Result<()> {
    let [repo, base, intent, directory] = args else {
        return Err("usage: harborist-verify run REPO BASE_SHA INTENT_FILE NEW_RUN_DIR".into());
    };
    let repo = Path::new(repo).canonicalize()?;
    let root = git_text(&repo, &["rev-parse", "--show-toplevel"])?;
    let directory = Path::new(directory);
    let directory = directory
        .parent()
        .ok_or("run directory has no parent")?
        .canonicalize()?
        .join(directory.file_name().ok_or("missing run directory name")?);
    if directory.starts_with(&root) {
        return Err("run directory must be outside the source checkout".into());
    }
    let base = commit(base)?;
    let resolved = git_text(&repo, &["rev-parse", &format!("{base}^{{commit}}")])?;
    if resolved != base.as_str() {
        return Err("base must identify the exact commit".into());
    }
    let frozen = git(
        &repo,
        &["show".as_ref(), format!("{base}:harborist.yaml").as_ref()],
    )?;
    let config = Config::parse(&frozen)?;
    let intent = fs::read_to_string(intent)?;
    if intent.trim().is_empty() {
        return Err("intent must contain text".into());
    }
    let id = Uuid::new_v4();
    let attempt = Attempt::new(id, base.clone());
    let source_sha256 = format!("{:x}", Sha256::digest(&frozen));
    fs::create_dir(&directory)?;
    let candidate_ref = format!("refs/harborist/rust-runs/{id}/candidate");
    let mut run = Run {
        repo: &repo,
        dir: &directory,
        base: &base,
        attempt: &attempt,
        workflow: Workflow::new(attempt.clone()),
        candidate: None,
        candidate_ref: &candidate_ref,
        source_sha256: &source_sha256,
        started: Instant::now(),
        agent: &Codex,
    };

    let result = (|| {
        fs::write(directory.join("intent.md"), &intent)?;
        fs::write(directory.join("harborist.yaml"), frozen)?;
        fs::write(
            directory.join("contract.json"),
            serde_json::to_vec_pretty(&json!({
                "run_id": id,
                "attempt": attempt,
                "base_sha": base,
                "source_sha256": source_sha256,
                "total_seconds": 1800,
                "verification_reserve_seconds": 300,
            }))?,
        )?;
        run.run(&intent, config)
    })();
    // External errors still produce terminal artifacts, with no successful software outcome.
    let (outcome, error) = match result {
        Ok(outcome) => (outcome, None),
        Err(error) => ("FAILED", Some(error.to_string())),
    };
    if outcome == "FAILED" {
        if let Some(stage) = run
            .workflow
            .next_stage()
            .filter(|stage| *stage != Stage::Package)
        {
            let candidate = match stage {
                Stage::Test | Stage::Review => {
                    run.candidate.clone().map(|sha| attempt.candidate(sha))
                }
                _ => None,
            };
            run.accept(stage, Outcome::Failed, candidate)?;
        }
    }
    if run.workflow.next_stage() == Some(Stage::Package) {
        run.accept(Stage::Package, Outcome::Succeeded, None)?;
    }
    let evidence = json!({
        "run_id": id,
        "base_sha": base,
        "attempt": attempt,
        "outcome": outcome,
        "error": error,
        "candidate": run.candidate,
        "candidate_ref": run.candidate.as_ref().map(|_| candidate_ref.as_str()),
        "source_sha256": source_sha256,
        "receipts": run.workflow.receipts(),
    });
    fs::write(
        directory.join("report.md"),
        format!(
            "# Harborist Run {id}\n\nOutcome **{outcome}**\n\n{}\n",
            error.as_deref().unwrap_or("")
        ),
    )?;
    fs::write(
        directory.join("evidence.json"),
        serde_json::to_vec_pretty(&evidence)?,
    )?;
    println!("{}", serde_json::to_string(&evidence)?);
    if outcome != "VERIFIED" {
        return Err(error.unwrap_or_else(|| outcome.to_owned()).into());
    }
    Ok(())
}

struct Run<'a> {
    repo: &'a Path,
    dir: &'a Path,
    base: &'a Sha,
    attempt: &'a Attempt,
    workflow: Workflow,
    candidate: Option<Sha>,
    candidate_ref: &'a str,
    source_sha256: &'a str,
    started: Instant,
    agent: &'a dyn NativeAgent,
}

impl Run<'_> {
    fn accept(
        &mut self,
        stage: Stage,
        outcome: Outcome,
        candidate: Option<harborist_verify::workflow::Candidate>,
    ) -> Result<()> {
        self.workflow.accept(Receipt {
            stage,
            outcome,
            candidate,
        })?;
        Ok(())
    }

    fn invoke(
        &self,
        stage: Stage,
        name: &str,
        workspace: &Path,
        inputs: &[(&str, &str)],
        candidate: Option<&harborist_verify::workflow::Candidate>,
    ) -> Result<Output> {
        let left = self.allowance(stage)?;
        let directory = self.dir.join(name);
        fs::create_dir(&directory)?;
        let response = self.agent.execute(Request {
            stage,
            directory: &directory,
            workspace,
            inputs,
            candidate,
            allowance: left,
        })?;
        self.allowance(stage)?;
        Ok(response)
    }

    fn allowance(&self, stage: Stage) -> Result<Duration> {
        let seconds = if matches!(stage, Stage::Test | Stage::Review) {
            1800
        } else {
            1500
        };
        let left = Duration::from_secs(seconds).saturating_sub(self.started.elapsed());
        if left.as_secs() == 0 {
            return Err("execution budget exhausted".into());
        }
        Ok(left)
    }

    fn run(&mut self, intent: &str, config: Config) -> Result<&'static str> {
        self.accept(Stage::Intake, Outcome::Succeeded, None)?;
        let build_workspace = self.dir.join("build-workspace");
        let base = self.base.as_str();
        let repo = self.repo;
        let (spec, candidate) = match with_worktree(repo, &build_workspace, base, |workspace| {
            self.design_plan_build(workspace, intent)
        })? {
            BuildDecision::Stopped(outcome) => return Ok(outcome),
            BuildDecision::Candidate { spec, sha } => (spec, sha),
        };
        let identity = self.attempt.candidate(candidate.clone());
        let (checks, workspace_error) = with_worktree(
            repo,
            &self.dir.join("test-workspace"),
            candidate.as_str(),
            |workspace| {
                require_clean(workspace, candidate.as_str())?;
                let left = self.allowance(Stage::Test)?;
                let checks =
                    run_checks_with_budget(config, workspace, &self.dir.join("test"), left, left)?;
                let workspace_error = git_text(workspace, &["clean", "-fdX"])
                    .and_then(|_| require_clean(workspace, candidate.as_str()))
                    .err()
                    .map(|error| error.to_string());
                Ok((checks, workspace_error))
            },
        )?;
        self.allowance(Stage::Test)?;
        let passed = workspace_error.is_none()
            && checks.iter().all(|check| {
                check.returncode == Some(0) && !check.timed_out && check.error.is_none()
            });
        let mut test = serde_json::to_value(Evidence {
            candidate: candidate.clone(),
            source_sha256: self.source_sha256.to_owned(),
            passed,
            checks,
        })?;
        test["workspace_error"] = json!(workspace_error);
        let test = serde_json::to_string_pretty(&test)?;
        fs::write(self.dir.join("test/evidence.json"), &test)?;
        self.accept(
            Stage::Test,
            if passed {
                Outcome::Succeeded
            } else {
                Outcome::TestFailed
            },
            Some(identity.clone()),
        )?;
        if !passed {
            return Ok("TEST_FAILED");
        }
        let specification = Specification::parse(&spec)?;
        let review = with_worktree(
            repo,
            &self.dir.join("review-workspace"),
            candidate.as_str(),
            |workspace| {
                let response = self.invoke(
                    Stage::Review,
                    "review",
                    workspace,
                    &[("spec.md", &spec), ("test-evidence.json", &test)],
                    Some(&identity),
                )?;
                require_clean(workspace, candidate.as_str())?;
                let receipt = Review::parse(&response.result.to_string())?
                    .receipt(&identity, &specification)?;
                fs::write(
                    self.dir.join("review/review.md"),
                    response.artifact.ok_or("missing review artifact")?,
                )?;
                Ok(receipt)
            },
        )?;
        let outcome = if review.outcome == Outcome::Succeeded {
            "VERIFIED"
        } else {
            "CHANGES_REQUIRED"
        };
        self.workflow.accept(review)?;
        Ok(outcome)
    }

    fn design_plan_build(&mut self, workspace: &Path, intent: &str) -> Result<BuildDecision> {
        let output = self.invoke(
            Stage::Design,
            "design",
            workspace,
            &[("intent.md", intent)],
            None,
        )?;
        require_clean(workspace, self.base.as_str())?;
        let spec = output.artifact.ok_or("missing specification artifact")?;
        fs::write(self.dir.join("design/spec.md"), &spec)?;
        if let Some(stopped) = self.stop_if_requested(Stage::Design, &output.result)? {
            return Ok(stopped);
        }
        Specification::parse(&spec)?;
        self.accept(Stage::Design, Outcome::Succeeded, None)?;

        let upstream = [("intent.md", intent), ("spec.md", spec.as_str())];
        let output = self.invoke(Stage::Plan, "plan", workspace, &upstream, None)?;
        require_clean(workspace, self.base.as_str())?;
        let plan = output.artifact.ok_or("missing plan artifact")?;
        fs::write(self.dir.join("plan/plan.md"), &plan)?;
        if let Some(stopped) = self.stop_if_requested(Stage::Plan, &output.result)? {
            return Ok(stopped);
        }
        self.accept(Stage::Plan, Outcome::Succeeded, None)?;

        let output = self.invoke(
            Stage::Build,
            "build",
            workspace,
            &[upstream[0], upstream[1], ("plan.md", &plan)],
            None,
        )?;
        if let Some(plan) = output.plan_update {
            fs::write(self.dir.join("build/plan.md"), plan)?;
        }
        if let Some(stopped) = self.stop_if_requested(Stage::Build, &output.result)? {
            return Ok(stopped);
        }
        if git_text(workspace, &["rev-parse", "HEAD"])? != self.base.as_str() {
            return Err("BUILD must leave commits to Harborist".into());
        }
        git_text(workspace, &["add", "-A"])?;
        git_text(
            workspace,
            &["commit", "--allow-empty", "-m", "Harborist candidate"],
        )?;
        let sha: Sha = git_text(workspace, &["rev-parse", "HEAD"])?.parse()?;
        git_text(
            self.repo,
            &["update-ref", self.candidate_ref, sha.as_str(), ""],
        )?;
        self.accept(
            Stage::Build,
            Outcome::Succeeded,
            Some(self.attempt.candidate(sha.clone())),
        )?;
        self.candidate = Some(sha.clone());
        Ok(BuildDecision::Candidate { spec, sha })
    }

    fn stop_if_requested(
        &mut self,
        stage: Stage,
        result: &serde_json::Value,
    ) -> Result<Option<BuildDecision>> {
        let (outcome, label) = match result["status"].as_str() {
            Some("ready") => return Ok(None),
            Some("needs_clarification") => (Outcome::NeedsClarification, "NEEDS_CLARIFICATION"),
            Some("needs_rescoping") => (Outcome::NeedsRescoping, "NEEDS_RESCOPING"),
            _ => return Err("invalid agent status".into()),
        };
        self.accept(stage, outcome, None)?;
        Ok(Some(BuildDecision::Stopped(label)))
    }
}

enum BuildDecision {
    Stopped(&'static str),
    Candidate { spec: String, sha: Sha },
}

fn git_text(repo: &Path, args: &[&str]) -> Result<String> {
    let args: Vec<_> = args.iter().map(OsStr::new).collect();
    Ok(String::from_utf8(git(repo, &args)?)?.trim_end().to_owned())
}

fn require_clean(workspace: &Path, expected: &str) -> Result<()> {
    if git_text(workspace, &["rev-parse", "HEAD"])? != expected
        || !git_text(
            workspace,
            &[
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--ignored",
            ],
        )?
        .is_empty()
    {
        return Err("read-only stage changed the candidate checkout".into());
    }
    Ok(())
}

fn with_worktree<T>(
    repo: &Path,
    path: &Path,
    sha: &str,
    action: impl FnOnce(&Path) -> Result<T>,
) -> Result<T> {
    git(
        repo,
        &[
            "worktree".as_ref(),
            "add".as_ref(),
            "--detach".as_ref(),
            path.as_os_str(),
            sha.as_ref(),
        ],
    )?;
    let result = action(path);
    let cleanup = git(
        repo,
        &[
            "worktree".as_ref(),
            "remove".as_ref(),
            "--force".as_ref(),
            path.as_os_str(),
        ],
    );
    cleanup?;
    result
}
