use crate::{
    Config, Evidence, Result, git, git_text,
    native::{AgentFailure, Codex, NativeAgent, Output, Request},
    record::VerificationInputs,
    run_checks_with_budget,
    store::{self, Captured},
};
use harborist_verify::{
    review::{Review, Specification},
    workflow::{Attempt, Outcome, Receipt, Sha, Stage, Workflow},
};
use serde_json::json;
use std::{
    fs::{self, File},
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

pub fn execute(capture: Captured) -> Result<serde_json::Value> {
    if let Some(execution) = &capture.contract.execution {
        execution.require_executor()?;
    }
    let attempt = store::admit(&capture)?;
    let directory = capture.directory.clone();
    execute_attempt(capture, directory, attempt, None)
}

pub struct Rework {
    pub context: String,
    pub specification: Option<String>,
    pub spent_seconds: u64,
    pub granted_seconds: u64,
    pub cancellation: Option<std::path::PathBuf>,
}

pub fn execute_attempt(
    capture: Captured,
    directory: PathBuf,
    attempt: Attempt,
    rework: Option<Rework>,
) -> Result<serde_json::Value> {
    let cancellation = rework
        .as_ref()
        .and_then(|data| data.cancellation.clone())
        .unwrap_or_else(|| crate::retirement::path(&capture.directory));
    let spent = rework.as_ref().map_or(0, |data| data.spent_seconds);
    let granted = rework.as_ref().map_or(0, |data| data.granted_seconds);
    let total = capture
        .contract
        .total_seconds
        .checked_add(granted)
        .ok_or("execution budget overflow")?
        .saturating_sub(spent);
    let candidate_ref = if rework.is_some() {
        store::attempt_candidate_ref(capture.contract.run_id, attempt.id())
    } else {
        store::candidate_ref(capture.contract.run_id)
    };
    let Captured {
        contract,
        config,
        intent,
        ..
    } = capture;
    let repo = contract.repository;
    let base = contract.base_sha;
    let id = contract.run_id;
    let source_sha256 = contract.source_sha256;
    let agent = Codex(contract.execution.as_ref());
    let mut run = Run {
        repo: &repo,
        dir: &directory,
        cancellation: &cancellation,
        base: attempt.start_sha(),
        rework: rework.as_ref(),
        spec_sha256: None,
        attempt: &attempt,
        workflow: Workflow::new(attempt.clone()),
        candidate: None,
        verification_inputs: None,
        candidate_ref: &candidate_ref,
        source_sha256: &source_sha256,
        started: Instant::now(),
        total_seconds: total,
        verification_reserve_seconds: contract.verification_reserve_seconds,
        agent: &agent,
    };

    let result = run.run(&intent, config);
    // External errors still produce terminal artifacts, with no successful software outcome.
    let (outcome, error, failure_reason) = match result {
        Ok(outcome) => (outcome, None, None),
        Err(error)
            if error
                .downcast_ref::<std::io::Error>()
                .is_some_and(|error| error.kind() == std::io::ErrorKind::Interrupted)
                && cancellation.exists() =>
        {
            ("CANCELLED", None, None)
        }
        Err(error) => {
            let reason = if let Some(agent) = error.downcast_ref::<AgentFailure>() {
                agent.reason
            } else if error.is::<harborist_verify::review::ReviewError>() {
                "INVALID_STAGE_OUTPUT"
            } else {
                "INTERNAL_ERROR"
            };
            ("FAILED", Some(error.to_string()), Some(reason))
        }
    };
    if matches!(outcome, "FAILED" | "CANCELLED") {
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
            let disposition = if outcome == "FAILED" {
                Outcome::Failed
            } else {
                Outcome::Cancelled
            };
            run.accept(stage, disposition, candidate)?;
        }
    }
    if run.workflow.next_stage() == Some(Stage::Package) {
        run.accept(Stage::Package, Outcome::Succeeded, None)?;
    }
    let evidence = json!({
        "run_id": id,
        "base_sha": base,
        "start_sha": attempt.start_sha(),
        "spec_sha256": run.spec_sha256,
        "spent_seconds": spent.saturating_add(run.started.elapsed().as_secs_f64().ceil() as u64),
        "granted_seconds": granted,
        "attempt": attempt,
        "outcome": outcome,
        "error": error,
        "failure_reason": failure_reason,
        "candidate": run.candidate,
        "candidate_ref": run.candidate.as_ref().map(|_| candidate_ref.as_str()),
        "source_sha256": source_sha256,
        "receipts": run.workflow.receipts(),
        "verification_inputs": run.verification_inputs,
    });
    store::write_new(
        &directory.join("report.md"),
        format!(
            "# Harborist Run {id}\n\nOutcome **{outcome}**\n\n{}\n",
            error.as_deref().unwrap_or("")
        )
        .as_bytes(),
    )?;
    store::write_new(
        &directory.join(".evidence.pending"),
        &serde_json::to_vec_pretty(&evidence)?,
    )?;
    fs::rename(
        directory.join(".evidence.pending"),
        directory.join("evidence.json"),
    )?;
    File::open(&directory)?.sync_all()?;
    Ok(evidence)
}

struct Run<'a> {
    repo: &'a Path,
    dir: &'a Path,
    cancellation: &'a Path,
    base: &'a Sha,
    rework: Option<&'a Rework>,
    spec_sha256: Option<String>,
    attempt: &'a Attempt,
    workflow: Workflow,
    candidate: Option<Sha>,
    verification_inputs: Option<VerificationInputs>,
    candidate_ref: &'a str,
    source_sha256: &'a str,
    started: Instant,
    total_seconds: u64,
    verification_reserve_seconds: u64,
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
        let response = self
            .agent
            .execute(Request {
                stage,
                directory: &directory,
                workspace,
                inputs,
                candidate,
                allowance: left,
                cancellation: self.cancellation,
            })
            .map_err(|error| {
                if error.is::<AgentFailure>()
                    || error
                        .downcast_ref::<std::io::Error>()
                        .is_some_and(|io| io.kind() == std::io::ErrorKind::Interrupted)
                {
                    return error;
                }
                AgentFailure {
                    reason: "EXECUTION_FAILED",
                    message: error.to_string(),
                }
                .into()
            })?;
        self.allowance(stage)?;
        Ok(response)
    }

    fn allowance(&self, stage: Stage) -> Result<Duration> {
        crate::retirement::cancelled(self.cancellation)?;
        let seconds = if matches!(stage, Stage::Test | Stage::Review) {
            self.total_seconds
        } else {
            self.total_seconds
                .saturating_sub(self.verification_reserve_seconds)
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
                let checks = run_checks_with_budget(
                    config,
                    workspace,
                    &self.dir.join("test"),
                    left,
                    left,
                    Some(self.cancellation),
                )?;
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
        let process_report = match fs::read_to_string(self.dir.join("build/build-process.json")) {
            Ok(report) => Some(report),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(error) => return Err(error.into()),
        };
        let mut review_inputs = vec![
            ("spec.md", spec.as_str()),
            ("test-evidence.json", test.as_str()),
        ];
        if let Some(report) = process_report.as_deref() {
            review_inputs.push(("build-process.json", report));
        }
        let specification = Specification::parse(&spec)?;
        let (review, review_sha256) = with_worktree(
            repo,
            &self.dir.join("review-workspace"),
            candidate.as_str(),
            |workspace| {
                let response = self.invoke(
                    Stage::Review,
                    "review",
                    workspace,
                    &review_inputs,
                    Some(&identity),
                )?;
                require_clean(workspace, candidate.as_str())?;
                let receipt = Review::parse(&response.result.to_string())?
                    .receipt(&identity, &specification)?;
                fs::write(
                    self.dir.join("review/review.md"),
                    response.artifact.ok_or("missing review artifact")?,
                )?;
                Ok((receipt, response.sha256))
            },
        )?;
        let outcome = if review.outcome == Outcome::Succeeded {
            self.verification_inputs = Some(VerificationInputs {
                spec_sha256: specification.sha256().to_owned(),
                test_sha256: store::digest(test.as_bytes()),
                review_sha256,
            });
            "VERIFIED"
        } else {
            "CHANGES_REQUIRED"
        };
        self.workflow.accept(review)?;
        Ok(outcome)
    }

    fn design_plan_build(&mut self, workspace: &Path, intent: &str) -> Result<BuildDecision> {
        let spec = if let Some(spec) = self.rework.and_then(|rework| rework.specification.as_ref())
        {
            fs::create_dir(self.dir.join("design"))?;
            store::write_new(&self.dir.join("design/spec.md"), spec.as_bytes())?;
            spec.clone()
        } else {
            let output = self.invoke(
                Stage::Design,
                "design",
                workspace,
                &[("intent.md", intent)],
                None,
            )?;
            require_clean(workspace, self.base.as_str())?;
            let spec = output.artifact.ok_or("missing specification artifact")?;
            store::write_new(&self.dir.join("design/spec.md"), spec.as_bytes())?;
            if let Some(stopped) = self.stop_if_requested(Stage::Design, &output.result)? {
                return Ok(stopped);
            }
            spec
        };
        let specification = Specification::parse(&spec)?;
        crate::continuation::checkpoint_design(self.dir, self.attempt, specification.sha256())?;
        self.spec_sha256 = Some(specification.sha256().to_owned());
        self.accept(Stage::Design, Outcome::Succeeded, None)?;

        let mut upstream = vec![("intent.md", intent), ("spec.md", spec.as_str())];
        if let Some(rework) = self.rework {
            upstream.push(("continuation-context.json", rework.context.as_str()));
        }
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
        if let Some(report) = output.process_report {
            let evidence = json!({
                "run_id": self.attempt.run_id(),
                "attempt_id": self.attempt.id(),
                "provenance": "agent-reported",
                "report": report,
            });
            fs::write(
                self.dir.join("build/build-process.json"),
                serde_json::to_vec(&evidence)?,
            )?;
        }
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
        || crate::hidden_index_flags(workspace)?
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
