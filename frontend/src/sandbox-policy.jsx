import React, { useState } from "react";
import { useResource } from "./api";
import { Field, write } from "./run-actions";
import { Button } from "./ui";

function PolicyEditor({ workspace }) {
  const path = `/integrations/sandbox/policy/${workspace.id}`;
  const resource = useResource(path);
  const [editing, setEditing] = useState(false);
  const [mode, setMode] = useState("trusted-local");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const data = resource.data;
  const policy = typeof data?.policy === "object" ? data.policy : data?.defaults;
  const docker = typeof data?.policy === "object";

  async function save(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const rules = name => String(fields.get(name) || "").split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    const next = mode === "trusted-local" ? "trusted-local" : {
      ...policy, baseline_sha256: null, cpus: Number(fields.get("cpus")),
      memory_mib: Number(fields.get("memory_mib")), allow: rules("allow"), deny: rules("deny"),
    };
    setBusy(true);
    setError("");
    try {
      await write(path, { policy: next });
      setEditing(false);
      setSaved(true);
      resource.refresh();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  return <>
    {resource.error && <p role="alert" className="notice">{resource.error}</p>}
    {!data && !resource.error && <p role="status">Loading execution policy…</p>}
    {data?.status === "settings_unavailable" && <p role="alert" className="notice">{data.message}</p>}
    {data?.status === "configured" && !editing && <>
      <p>Runtime <strong>{docker ? "Docker Sandboxes" : "Trusted local"}</strong></p>
      {docker ? <p className="muted">{policy.cpus} CPUs · {policy.memory_mib} MiB · {policy.allow.length} added allow rules · {policy.deny.length} deny rules</p>
        : <p className="muted">Commands run on this machine without a sandbox security boundary.</p>}
      <Button variant="outline" onClick={() => { setMode(docker ? "docker-sandboxes" : "trusted-local"); setEditing(true); setSaved(false); setError(""); }}>Edit execution policy</Button>
    </>}
    {editing && <form className="sandbox-policy-form" aria-label="Sandbox execution policy" onSubmit={save}>
      <label className="field">Execution runtime
        <select className="input" aria-label="Execution runtime" value={mode} onChange={event => setMode(event.target.value)} disabled={busy}>
          <option value="trusted-local">Trusted local</option>
          <option value="docker-sandboxes">Docker Sandboxes</option>
        </select>
      </label>
      {mode === "docker-sandboxes" && <>
        <div className="field-pair">
          <Field label="CPUs" name="cpus" type="number" min={1} max={16} defaultValue={policy.cpus} required disabled={busy} />
          <Field label="Memory (MiB)" name="memory_mib" type="number" min={512} max={32768} defaultValue={policy.memory_mib} required disabled={busy} />
        </div>
        <p className="muted">Network rules apply to Shipyard’s disposable sandboxes on top of Docker’s machine policy. Deny rules take precedence. Saving does not edit Docker’s global policy.</p>
        <label className="field">Additional allowed destinations
          <textarea className="input" aria-label="Additional allowed destinations" name="allow" rows={4} defaultValue={policy.allow.join("\n")} placeholder="registry.example.com:443" aria-describedby="sandbox-rule-help" disabled={busy} />
        </label>
        <label className="field">Blocked destinations
          <textarea className="input" aria-label="Blocked destinations" name="deny" rows={4} defaultValue={policy.deny.join("\n")} placeholder="example.com" aria-describedby="sandbox-rule-help" disabled={busy} />
        </label>
        <p id="sandbox-rule-help" className="muted">One hostname per line. Optional subdomain wildcards and ports are supported, such as *.example.com:443. Do not enter URLs or credentials.</p>
        <p className="muted">Uses a pinned Codex image, fresh environments for each stage, no host folder mounts, and no shared skills, SSH agent, or MCP tools.</p>
      </>}
      <p className="muted">Changes apply to future Runs using this settings file. Queued Runs and recovery Attempts keep their frozen policy. If Docker’s global rules change after intake, capture a new Run.</p>
      <div className="sandbox-policy-actions">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save execution policy"}</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setEditing(false); setError(""); }}>Cancel</Button>
      </div>
    </form>}
    {saved && <p role="status" className="integration-connected">Execution policy saved for future Runs.</p>}
    {error && <p role="alert" className="notice">{error}</p>}
  </>;
}

export function SandboxIntegration({ workspaces }) {
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const workspace = workspaces.find(item => item.id === (selected ?? workspaces[0]?.id));

  async function check() {
    setBusy(true);
    setResult(null);
    try {
      setResult(await write("/integrations/sandbox/check", {}));
    } catch (error) {
      setResult({ status: "unavailable", message: error.message });
    } finally {
      setBusy(false);
    }
  }

  return <section className="integration-panel sandbox-integration">
    <h2>Docker Sandboxes</h2>
    <p className="muted">Run agents and mandatory checks in isolated environments on this machine.</p>
    <Button variant="outline" onClick={check} disabled={busy}>{busy ? "Checking…" : "Check Docker Sandboxes"}</Button>
    {result && <p role="status" className={result.status === "ready" ? "integration-connected" : "notice"}>{result.message}</p>}
    <h3>Execution policy</h3>
    {workspace ? <>
      <label className="field">Workspace
        <select className="input" value={workspace.id} onChange={event => setSelected(event.target.value)}>
          {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <PolicyEditor key={workspace.id} workspace={workspace} />
    </> : <p className="muted">Add a Workspace to configure sandbox execution.</p>}
  </section>;
}
