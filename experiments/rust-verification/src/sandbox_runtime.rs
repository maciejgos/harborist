//! Host-side authority for disposable Docker Sandboxes.

use crate::{
    Result,
    process::{Capture, Stream},
    sandbox_authority::host_command,
    store,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, HashSet},
    fs::{self, File},
    io,
    path::{Path, PathBuf},
    sync::Mutex,
};
use uuid::Uuid;

#[derive(Deserialize, Serialize)]
struct Identity {
    name: String,
    id: Uuid,
    status: String,
}

type Ownership = BTreeMap<String, Option<Uuid>>;

pub struct Runtime {
    directory: PathBuf,
    ownership_lock: Mutex<()>,
}

impl Runtime {
    pub fn new(directory: &Path) -> Self {
        Self {
            directory: directory.to_owned(),
            ownership_lock: Mutex::new(()),
        }
    }

    fn ownership(&self) -> Result<Ownership> {
        match fs::read(self.directory.join("ownership.json")) {
            Ok(raw) => Ok(serde_json::from_slice(&raw)?),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(BTreeMap::new()),
            Err(error) => Err(error.into()),
        }
    }

    fn save(&self, ownership: &Ownership) -> Result<()> {
        let pending = self
            .directory
            .join(format!(".ownership-{}.pending", Uuid::new_v4()));
        store::write_new(&pending, &serde_json::to_vec(ownership)?)?;
        if let Err(error) = fs::rename(&pending, self.directory.join("ownership.json")) {
            let _ = fs::remove_file(pending);
            return Err(error.into());
        }
        File::open(&self.directory)?.sync_all()?;
        Ok(())
    }

    pub fn execute(
        &self,
        args: &[&str],
        timeout: u64,
        limit: usize,
        input: &[u8],
        run: impl Fn(&[&str], u64, usize, &[u8], bool) -> Result<Capture>,
        disconnected: impl Fn() -> bool,
    ) -> Result<Capture> {
        if !(1..=3600).contains(&timeout)
            || !(1..=16 * 1024 * 1024).contains(&limit)
            || input.len() > 64 * 1024 * 1024
            || args.is_empty()
            || args.len() > 1024
            || (!input.is_empty() && !matches!(args.first(), Some(&("exec" | "upload"))))
        {
            return Err("invalid host sandbox operation bounds or input".into());
        }
        if matches!(args, ["version"] | ["policy", "ls", "--json"]) {
            return run(args, timeout, limit, &[], true);
        }
        let lock = self
            .ownership_lock
            .lock()
            .map_err(|_| "sandbox ownership lock poisoned")?;
        let mut ownership = self.ownership()?;
        let observed = inventory(&run)?;
        let mut owned: HashSet<_> = observed
            .values()
            .filter_map(|entry| {
                (ownership.get(&entry.name) == Some(&Some(entry.id))).then_some(entry.name.as_str())
            })
            .collect();
        if args == ["ls", "--json"] {
            if ownership.values().any(Option::is_none) {
                return Err("a sandbox creation could not be reconciled".into());
            }
            let mut output = serde_json::to_vec(
                &observed
                    .values()
                    .filter(|entry| owned.contains(entry.name.as_str()))
                    .collect::<Vec<_>>(),
            )?;
            let truncated = output.len() > limit;
            output.truncate(limit);
            return Ok(Capture {
                returncode: 0,
                timed_out: false,
                stdout: Stream {
                    bytes: output,
                    truncated,
                },
                stderr: Stream::default(),
            });
        }
        if args.first() == Some(&"create") {
            owned.extend(ownership.keys().map(String::as_str));
        }
        let command = host_command(args, &owned)?;
        let command: Vec<_> = command.iter().map(String::as_str).collect();
        if let ["create", "--name", name, ..] = command.as_slice() {
            if observed.contains_key(*name) {
                return Err("sandbox name is already in use".into());
            }
            ownership.insert((*name).to_owned(), None);
            self.save(&ownership)?;
            let result = run(&command, timeout, limit, &[], false);
            match inventory_now(&run, name)? {
                Some(id) => {
                    ownership.insert((*name).to_owned(), Some(id));
                }
                None => {
                    ownership.remove(*name);
                }
            }
            self.save(&ownership)?;
            if disconnected() {
                if let Some(Some(id)) = ownership.get(*name) {
                    stop_owned(&run, name, *id)?;
                }
            }
            return result;
        }
        drop(lock);
        let result = run(&command, timeout, limit, input, true);
        if command[0] == "exec" && disconnected() {
            let name = command[command
                .iter()
                .position(|arg| *arg == "--")
                .ok_or("missing guest command separator")?
                + 1];
            let _lock = self
                .ownership_lock
                .lock()
                .map_err(|_| "sandbox ownership lock poisoned")?;
            stop_owned(&run, name, observed[name].id)?;
        }
        result
    }
}

fn stop_owned(
    run: &impl Fn(&[&str], u64, usize, &[u8], bool) -> Result<Capture>,
    name: &str,
    id: Uuid,
) -> Result<()> {
    let current = inventory(run)?;
    if current
        .get(name)
        .is_some_and(|guest| guest.id == id && guest.status != "stopped")
    {
        let result = run(&["stop", name], 20, 65536, &[], false)?;
        if result.returncode != 0 || result.timed_out {
            return Err("host helper could not stop the disconnected sandbox".into());
        }
    }
    Ok(())
}

fn inventory_now(
    run: &impl Fn(&[&str], u64, usize, &[u8], bool) -> Result<Capture>,
    name: &str,
) -> Result<Option<Uuid>> {
    Ok(inventory(run)?.get(name).map(|entry| entry.id))
}

fn inventory(
    run: &impl Fn(&[&str], u64, usize, &[u8], bool) -> Result<Capture>,
) -> Result<BTreeMap<String, Identity>> {
    let result = run(&["ls", "--json"], 5, 1024 * 1024, &[], false)?;
    if result.returncode != 0 || result.timed_out || result.stdout.truncated {
        return Err("cannot establish live sandbox identity".into());
    }
    let entries: Vec<Identity> = serde_json::from_slice(&result.stdout.bytes)?;
    let mut values = BTreeMap::new();
    for entry in entries {
        if values.insert(entry.name.clone(), entry).is_some() {
            return Err("duplicate sandbox name in live inventory".into());
        }
    }
    Ok(values)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::cell::{Cell, RefCell};

    #[test]
    fn ownership_survives_restart_and_does_not_follow_reused_names() {
        let directory = crate::sandbox::TransferDirectory::create().unwrap();
        let name = "harborist-build-1234567890abcdef";
        let identity = Uuid::new_v4();
        let live = Cell::new(None);
        let calls = RefCell::new(Vec::new());
        let run = |args: &[&str], _: u64, _: usize, _: &[u8], _: bool| {
            let bytes = match args {
                ["ls", "--json"] => serde_json::to_vec(
                    &live
                        .get()
                        .map(|id| {
                            json!({
                                "name": name, "id": id, "status": "running",
                            })
                        })
                        .into_iter()
                        .collect::<Vec<_>>(),
                )?,
                ["create", ..] => {
                    live.set(Some(identity));
                    Vec::new()
                }
                other => {
                    calls.borrow_mut().push(other.join(" "));
                    Vec::new()
                }
            };
            Ok(Capture {
                returncode: 0,
                timed_out: false,
                stdout: Stream {
                    bytes,
                    truncated: false,
                },
                stderr: Stream::default(),
            })
        };
        let first = Runtime::new(&directory.0);
        first
            .execute(
                &[
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
                    crate::sandbox::CODEX_KIT,
                ],
                10,
                65536,
                &[],
                run,
                || false,
            )
            .unwrap();
        let restarted = Runtime::new(&directory.0);
        restarted
            .execute(&["stop", name], 10, 65536, &[], run, || false)
            .unwrap();
        live.set(Some(Uuid::new_v4()));
        assert!(
            restarted
                .execute(&["stop", name], 10, 65536, &[], run, || false)
                .is_err()
        );
        let listing = restarted
            .execute(&["ls", "--json"], 10, 65536, &[], run, || false)
            .unwrap();
        assert_eq!(listing.stdout.bytes, b"[]");
        assert_eq!(*calls.borrow(), [format!("stop {name}")]);
    }
}
