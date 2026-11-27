//! Translate approved host-helper operations into local sbx argument vectors.

use crate::{
    Result,
    sandbox::{CODEX_KIT, GUEST_BUNDLE, GUEST_FINAL, GUEST_REPOSITORY, GUEST_SCHEMA, destinations},
};
use regex::Regex;
use std::{collections::HashSet, sync::LazyLock};

static NAME: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\Aharborist-(?:design|plan|build|test|review)-[a-f0-9]{16}\z").unwrap()
});

pub fn host_command(args: &[&str], owned: &HashSet<&str>) -> Result<Vec<String>> {
    if args.iter().any(|value| value.as_bytes().contains(&0)) {
        return Err("invalid sandbox command argument".into());
    }
    let converted = match args {
        ["version"] | ["policy", "ls", "--json"] | ["ls", "--json"] => args.to_vec(),
        [
            "create",
            "--name",
            name,
            "--cpus",
            cpu,
            "--memory",
            memory,
            "--skills",
            "off",
            "--static-mcp",
            "none",
            CODEX_KIT,
        ] if NAME.is_match(name) && !owned.contains(name) => {
            let valid = |number: &str, min_digits, max_digits, min, max| {
                (min_digits..=max_digits).contains(&number.len())
                    && number.bytes().all(|byte| byte.is_ascii_digit())
                    && number
                        .parse::<u32>()
                        .is_ok_and(|n| (min..=max).contains(&n))
            };
            if !valid(cpu, 1, 2, 1, 16)
                || !memory
                    .strip_suffix('m')
                    .is_some_and(|number| valid(number, 3, 5, 512, 32768))
            {
                return Err("invalid sandbox resources".into());
            }
            args.to_vec()
        }
        [
            "policy",
            decision @ ("allow" | "deny"),
            "network",
            "--sandbox",
            name,
            destination,
        ] if owned.contains(name) => {
            let normalized = destinations(vec![(*destination).to_owned()])?;
            return Ok(["policy", decision, "network", "--sandbox", name]
                .into_iter()
                .map(str::to_owned)
                .chain(normalized)
                .collect());
        }
        ["stop", name] | ["rm", "--force", name] if owned.contains(name) => args.to_vec(),
        [
            "exec",
            "-i",
            "--workdir",
            GUEST_REPOSITORY,
            name,
            executable,
            rest @ ..,
        ] if owned.contains(name) => {
            let mut command = vec![
                "exec",
                "-i",
                "--workdir",
                GUEST_REPOSITORY,
                "--",
                name,
                executable,
            ];
            command.extend_from_slice(rest);
            command
        }
        ["exec", name, executable, rest @ ..] if owned.contains(name) => {
            let mut command = vec!["exec", "--", name, executable];
            command.extend_from_slice(rest);
            command
        }
        ["upload", name, path @ (GUEST_BUNDLE | GUEST_SCHEMA)] if owned.contains(name) => {
            return Ok(["exec", "-i", "--", name, "dd"]
                .into_iter()
                .map(str::to_owned)
                .chain([format!("of={path}"), "status=none".to_owned()])
                .collect());
        }
        ["download", name, GUEST_FINAL] if owned.contains(name) => {
            vec!["exec", "--", name, "cat", GUEST_FINAL]
        }
        _ => return Err("sandbox operation is outside this deployment's authority".into()),
    };
    Ok(converted.into_iter().map(str::to_owned).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restricts_operations_and_preserves_guest_argument_boundaries() {
        let name = "harborist-build-1234567890abcdef";
        let owned = HashSet::from([name]);
        assert_eq!(
            host_command(
                &[
                    "exec",
                    "-i",
                    "--workdir",
                    GUEST_REPOSITORY,
                    name,
                    "git",
                    "status"
                ],
                &owned
            )
            .unwrap(),
            [
                "exec",
                "-i",
                "--workdir",
                GUEST_REPOSITORY,
                "--",
                name,
                "git",
                "status"
            ],
        );
        assert_eq!(
            host_command(
                &[
                    "policy",
                    "deny",
                    "network",
                    "--sandbox",
                    name,
                    " EXAMPLE.org "
                ],
                &owned
            )
            .unwrap(),
            [
                "policy",
                "deny",
                "network",
                "--sandbox",
                name,
                "example.org"
            ],
        );
        assert_eq!(
            host_command(&["upload", name, GUEST_SCHEMA], &owned).unwrap(),
            [
                "exec",
                "-i",
                "--",
                name,
                "dd",
                "of=/tmp/harborist-schema.json",
                "status=none"
            ],
        );
        for command in [
            &["exec", "foreign", "git", "status"][..],
            &["exec", "-i", "--workdir", "/other", name, "git"],
            &["upload", name, "/tmp/other"],
            &["download", name, GUEST_BUNDLE],
            &["policy", "allow", "network", "example.org"],
        ] {
            assert!(host_command(command, &owned).is_err(), "{command:?}");
        }
    }

    #[test]
    fn provisions_only_the_pinned_template_with_bounded_resources() {
        let name = "harborist-design-1234567890abcdef";
        let create = [
            "create",
            "--name",
            name,
            "--cpus",
            "2",
            "--memory",
            "2048m",
            "--skills",
            "off",
            "--static-mcp",
            "none",
            CODEX_KIT,
        ];
        assert!(host_command(&create, &HashSet::new()).is_ok());
        assert!(host_command(&create, &HashSet::from([name])).is_err());
        let mut invalid = create;
        invalid[4] = "17";
        assert!(host_command(&invalid, &HashSet::new()).is_err());
        invalid = create;
        invalid[11] = "docker.io/sbx/codex:latest";
        assert!(host_command(&invalid, &HashSet::new()).is_err());
    }
}
