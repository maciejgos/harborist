//! Operator-facing integration checks and future Workspace defaults.

use crate::{Result, github, native, sandbox, settings, workspace};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io,
    path::{Path, PathBuf},
};
use uuid::Uuid;

fn profile_route(route: &str) -> Option<(&str, Uuid)> {
    let (kind, id) = route.strip_prefix("/integrations/")?.rsplit_once('/')?;
    matches!(kind, "codex/profile" | "sandbox/policy").then_some((kind, id.parse().ok()?))
}

pub fn is_read(route: &str) -> bool {
    profile_route(route).is_some()
}

pub fn is_write(route: &str) -> bool {
    is_read(route)
        || matches!(
            route,
            "/integrations/github" | "/integrations/codex/check" | "/integrations/sandbox/check"
        )
}

fn profile_path(control: &Path, id: Uuid) -> Result<PathBuf> {
    let workspace = workspace::load(control, id)?;
    settings::profile_path(&workspace.repository, workspace.settings.as_deref())
}

pub fn read(control: &Path, route: &str) -> Result<Value> {
    let (kind, id) = profile_route(route).ok_or("unknown integration route")?;
    let path = profile_path(control, id)?;
    Ok(if kind == "codex/profile" {
        settings::profile_status(&path)
    } else {
        settings::policy_status(&path)
    })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CodexProfile {
    model: String,
    effort: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Policy {
    policy: settings::SandboxPolicy,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GitHubCheck {
    workspace_id: Option<Uuid>,
}

pub fn write(control: &Path, route: &str, body: &[u8]) -> Result<Value> {
    if let Some((kind, id)) = profile_route(route) {
        let path = profile_path(control, id)?;
        match kind {
            "codex/profile" => {
                let profile: CodexProfile = serde_json::from_slice(body)?;
                settings::configure_profile(&path, &profile.model, profile.effort.as_deref())?;
            }
            _ => {
                let policy: Policy = serde_json::from_slice(body)?;
                settings::configure_policy(&path, policy.policy)?;
            }
        }
        return Ok(json!({"status":"saved"}));
    }
    match route {
        "/integrations/codex/check" => Ok(native::check_connection()),
        "/integrations/sandbox/check" => {
            let args: Value = serde_json::from_slice(body)?;
            if args != json!({}) {
                return Err("Sandbox readiness expects an empty request".into());
            }
            Ok(match sandbox::baseline() {
                Ok(digest) => {
                    json!({"status":"ready","message":"Docker Sandboxes 0.54.x is available with an initialized network policy. Model credentials are checked when execution starts.","baseline_sha256":digest})
                }
                Err(error) => json!({"status":"unavailable","message":error.to_string()}),
            })
        }
        "/integrations/github" => github_connection(control, serde_json::from_slice(body)?),
        _ => Err("unknown integration route".into()),
    }
}

fn github_connection(control: &Path, request: GitHubCheck) -> Result<Value> {
    let repository = request
        .workspace_id
        .map(|id| -> Result<String> {
            workspace::load(control, id)?
                .github_repository
                .filter(|repository| github::valid_repository(repository))
                .ok_or_else(|| {
                    "Set a GitHub repository in this Workspace before checking access".into()
                })
        })
        .transpose()?;
    let check = |args: &[&str]| github::run(control, 8, args).map(|result| result.returncode == 0);
    let result = (|| -> Result<Value> {
        if !check(&["auth", "status", "--hostname", "github.com"])? {
            return Ok(
                json!({"status":"login_required","message":"Run gh auth login --hostname github.com in your terminal, then check again."}),
            );
        }
        if let Some(repository) = repository {
            if !check(&[
                "api",
                "--hostname",
                "github.com",
                &format!("repos/{repository}"),
            ])? {
                return Ok(
                    json!({"status":"repository_unavailable","message":format!("GitHub could not confirm access to {repository}. Check the Workspace repository and your GitHub account’s access.")}),
                );
            }
            return Ok(
                json!({"status":"connected","message":format!("GitHub CLI can access {repository}.")}),
            );
        }
        Ok(json!({"status":"connected","message":"GitHub CLI is signed in to github.com."}))
    })();
    Ok(match result {
        Ok(status) => status,
        Err(error)
            if error
                .downcast_ref::<io::Error>()
                .is_some_and(|error| error.kind() == io::ErrorKind::NotFound) =>
        {
            json!({"status":"cli_missing","message":"Install GitHub CLI (gh), then restart the Harborist service and check again."})
        }
        Err(_) => {
            json!({"status":"check_failed","message":"GitHub CLI could not complete the check. Check your connection and try again."})
        }
    })
}
