import React, { useState } from "react";
import { Plug } from "lucide-react";
import { useResource } from "./api";
import { Field, write } from "./run-actions";
import { Button } from "./ui";
import { SandboxIntegration } from "./sandbox-policy";

function CodexProfile({ workspace }) {
  const path = `/integrations/codex/profile/${workspace.id}`;
  const profile = useResource(path);
  const data = profile.data;
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await write(path, { model: fields.get("model").trim(), effort: fields.get("effort") || null });
      setEditing(false);
      profile.refresh();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  return <>
    {profile.error && <p role="alert" className="notice">{profile.error}</p>}
    {!data && !profile.error && <p role="status">Loading profile…</p>}
    {data?.status === "configured" ? <p role="status">
      Model <strong>{data.model}</strong> · Reasoning effort {data.effort || "Codex default"}
    </p> : data && <p role="status" className="notice">{data.message}</p>}
    {data && data.status !== "settings_unavailable" && !editing &&
      <Button variant="outline" onClick={() => setEditing(true)}>Edit profile</Button>}
    {editing && <form aria-label="Codex profile" onSubmit={save}>
      <Field label="Model" name="model" defaultValue={data.model} maxLength={128} disabled={busy} required />
      <label className="field">Reasoning effort
        <select className="input" name="effort" defaultValue={data.effort || ""} disabled={busy}>
          <option value="">Codex default</option>
          <option value="minimal">Minimal</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="xhigh">Extra high</option>
        </select>
      </label>
      <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button>
      <Button type="button" variant="outline" disabled={busy} onClick={() => { setEditing(false); setError(""); }}>Cancel</Button>
    </form>}
    {error && <p role="alert" className="notice">{error}</p>}
  </>;
}

function CodexIntegration({ workspaces }) {
  const [selected, setSelected] = useState(null);
  const workspace = workspaces.find(item => item.id === (selected ?? workspaces[0]?.id));
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function check() {
    setBusy(true);
    setResult(null);
    try {
      setResult(await write("/integrations/codex/check", {}));
    } catch (error) {
      setResult({ status: "check_failed", message: error.message });
    } finally {
      setBusy(false);
    }
  }

  return <section className="integration-panel">
    <h2>Codex</h2>
    <p className="muted">Check Codex CLI login in the Harborist service environment.</p>
    <Button disabled={busy} onClick={check}>{busy ? "Checking…" : "Check Codex"}</Button>
    {result && <p role="status" className={result.status === "ready" ? "integration-connected" : "notice"}>
      {result.message}
      {result.status === "cli_missing" && " Restart the Harborist service after installing it."}
    </p>}
    <h3>Execution profile</h3>
    {workspace ? <>
      <p className="muted">Changes apply to future Runs that use the selected settings file.</p>
      <label className="field">Workspace
        <select className="input" value={workspace.id} onChange={event => setSelected(event.target.value)}>
          {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <CodexProfile key={workspace.id} workspace={workspace} />
    </> : <p className="muted">Add a Workspace to configure its execution profile.</p>}
  </section>;
}

export function Integrations({ resource }) {
  const [workspace, setWorkspace] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const workspaces = resource.data?.workspaces || [];

  async function check(event) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      setResult(await write("/integrations/github", { workspace_id: workspace || null }));
    } catch (error) {
      setResult({ status: "check_failed", message: error.message });
    } finally {
      setBusy(false);
    }
  }

  return <main>
    <header className="topbar"><Plug size={15} /> Integrations</header>
    <div className="page-heading"><h1>Integrations</h1></div>
    <div className="settings-list">
      <section className="integration-panel">
        <h2>GitHub</h2>
        <p className="muted">Check your local GitHub CLI login or access to a Workspace repository.</p>
        {resource.error && <p role="alert" className="notice">{resource.error}</p>}
        <form onSubmit={check}>
          <label className="field">Check
            <select className="input" value={workspace} disabled={busy} onChange={event => { setWorkspace(event.target.value); setResult(null); }}>
              <option value="">GitHub CLI login</option>
              {workspaces.filter(item => item.github_repository).map(item =>
                <option key={item.id} value={item.id}>{item.name} · {item.github_repository}</option>)}
            </select>
          </label>
          <Button type="submit" disabled={busy}>{busy ? "Checking…" : "Check connection"}</Button>
        </form>
        {result && <p role="status" className={result.status === "connected" ? "integration-connected" : "notice"}>{result.message}</p>}
      </section>
      <CodexIntegration workspaces={workspaces} />
      <SandboxIntegration workspaces={workspaces} />
    </div>
  </main>;
}
