import React, { useState } from "react";
import { Github } from "lucide-react";
import { write } from "./run-actions";
import { Button } from "./ui";

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
    <header className="topbar"><Github size={15} /> Integrations</header>
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
    </div>
  </main>;
}
