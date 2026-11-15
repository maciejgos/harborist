import React from "react";
import { FolderGit2, Plus } from "lucide-react";
import { Button } from "./ui";
import { CommandDialog, Field, write } from "./run-actions";

function WorkspaceEditor({ workspace, onDone }) {
  return <CommandDialog title={workspace ? "Edit Workspace" : "New Workspace"}
    description="Save a local Git checkout and the defaults for its Runs."
    trigger={workspace ? <Button variant="outline">Edit</Button> : <Button><Plus size={15} /> New Workspace</Button>}
    send={write} submitLabel="Save Workspace" onDone={onDone}
    prepare={(fields, id) => ["/workspaces", {
      ...fields, id: workspace?.id || id, settings: fields.settings.trim() || null,
      github_repository: fields.github_repository.trim() || null,
      timeout: Number(fields.timeout), verification_reserve: Number(fields.verification_reserve),
    }]}>
    <Field label="Name" name="name" defaultValue={workspace?.name} required />
    <Field label="Repository path" name="repository" placeholder="~/Code/my-repository" defaultValue={workspace?.repository} required />
    <Field label="GitHub repository (optional)" name="github_repository" placeholder="owner/repository" defaultValue={workspace?.github_repository} />
    <details className="advanced">
      <summary>Advanced</summary>
      <Field label="Settings path (optional)" name="settings" placeholder="shipyard.settings.yaml in the checkout" defaultValue={workspace?.settings} />
      <Field label="Base Git ref" name="ref" defaultValue={workspace?.ref || "HEAD"} required />
      <div className="field-pair">
        <Field label="Total time (seconds)" name="timeout" type="number" min="1" defaultValue={workspace?.timeout || 1800} required />
        <Field label="Verification reserve (seconds)" name="verification_reserve" type="number" min="1" defaultValue={workspace?.verification_reserve || 300} required />
      </div>
    </details>
  </CommandDialog>;
}

export function Workspaces({ resource }) {
  const workspaces = resource.data?.workspaces || [];
  return <main>
    <header className="topbar"><FolderGit2 size={15} /> Workspaces</header>
    <div className="page-heading"><h1>Workspaces</h1>{resource.data && <WorkspaceEditor onDone={resource.refresh} />}</div>
    {resource.error && <p className="notice settings-notice" role="alert">{resource.error}</p>}
    {!resource.data && !resource.error && <p className="empty" role="status">Loading Workspaces…</p>}
    {resource.data && !workspaces.length && <div className="empty"><h2>No Workspaces yet</h2><p>Add a local checkout to reuse its settings when you start a Run.</p></div>}
    <div className="settings-list">{workspaces.map(workspace => <section key={workspace.id} className="settings-row">
      <FolderGit2 size={18} /><div><h2>{workspace.name}</h2><p className="mono muted">{workspace.repository} · {workspace.ref}</p>
      {workspace.github_repository && <p className="muted">{workspace.github_repository}</p>}</div>
      <WorkspaceEditor workspace={workspace} onDone={resource.refresh} />
    </section>)}</div>
  </main>;
}
