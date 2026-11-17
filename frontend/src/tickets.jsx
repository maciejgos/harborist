import React, { useEffect, useRef, useState } from "react";
import { Github } from "lucide-react";
import { Field, write } from "./run-actions";
import { Badge, Button } from "./ui";

const repositoryPattern = /^[A-Za-z0-9][A-Za-z0-9-]*\/(?!\.{1,2}$)[A-Za-z0-9_.-]+$/;

export function TicketInbox({ resource }) {
  const [source, setSource] = useState("");
  const [listing, setListing] = useState(null);
  const [selection, setSelection] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [submission, setSubmission] = useState(null);
  const listRequest = useRef(null);
  const queueRequest = useRef(null);
  const repository = source.trim();
  const validRepository = repository.length <= 256 && repositoryPattern.test(repository);
  const busy = submission?.pending === true;
  const ticket = listing?.issues?.find(issue => issue.identity === selection);
  const workspaces = resource.data?.workspaces || [];
  const workspace = workspaces.find(item => item.id === workspaceId);
  const confirmed = submission?.runId && selection === submission.source && workspaceId === submission.workspaceId;
  const canQueue = ticket && workspace && !resource.error && !busy && !confirmed;

  useEffect(() => () => listRequest.current?.abort(), []);

  function changeSource(value) {
    setSource(value);
    if (value.trim() !== repository) {
      listRequest.current?.abort();
      setListing(null);
      setSelection("");
    }
  }

  async function load(event) {
    event.preventDefault();
    if (!validRepository || busy || listing?.pending) return;
    listRequest.current?.abort();
    const controller = new AbortController();
    listRequest.current = controller;
    setListing({ pending: true, refresh: Boolean(listing) });
    try {
      const { issues } = await write("/tickets/list", { repository }, controller.signal);
      if (!controller.signal.aborted) {
        setListing({ issues });
        setSelection(current => issues.some(issue => issue.identity === current) ? current : "");
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setListing({
          error: error.name === "TimeoutError"
            ? "The issue request timed out. Check the local service and retry."
            : error.message,
        });
      }
    }
  }

  async function queue() {
    if (!canQueue || queueRequest.current?.pending) return;
    const source = ticket.identity;
    const previous = queueRequest.current;
    const requestId = previous?.source === source && previous.workspaceId === workspaceId
      ? previous.requestId
      : crypto.randomUUID();
    const request = { source, workspaceId, requestId, pending: true };
    queueRequest.current = request;
    setSubmission(request);
    try {
      const { run_id } = await write("/tickets/queue", {
        source,
        workspace_id: workspaceId,
        request_id: requestId,
      });
      queueRequest.current = null;
      setSubmission({ source, workspaceId, runId: run_id });
    } catch (error) {
      queueRequest.current = { ...request, pending: false };
      setSubmission({
        source, workspaceId,
        error: error.name === "TimeoutError"
          ? "The service response timed out. Retry with the same issue and Workspace."
          : error.message,
      });
    }
  }

  return <main>
    <header className="topbar"><Github size={15} /><span>Ticket Inbox</span></header>
    <div className="page-heading"><h1>Ticket Inbox</h1></div>
    <div className="ticket-inbox">
      <form className="ticket-source" onSubmit={load}>
        <Field label="Source repository" placeholder="owner/repo" value={source} maxLength={256}
          disabled={busy} onChange={event => changeSource(event.target.value)} />
        <Button type="submit" variant="outline" disabled={!validRepository || busy || listing?.pending}>
          {listing?.error ? "Retry" : listing?.issues || listing?.refresh ? "Refresh issues" : "Load issues"}
        </Button>
      </form>
      <p className="muted">Shows up to 100 open issues.</p>
      {source && !validRepository && <p className="muted">Enter the source as owner/repo.</p>}
      {listing?.pending && <p role="status">{listing.refresh ? "Refreshing issues…" : "Loading issues…"}</p>}
      {listing?.error && <p className="notice" role="alert">{listing.error}</p>}
      {listing?.issues?.length === 0 && <p role="status">No open issues in {repository}.</p>}
      {listing?.issues?.length > 0 && <fieldset className="ticket-list" disabled={busy}>
        <legend>Source issue</legend>
        <div className="ticket-rows">{listing.issues.map(issue => <div className="ticket-row" key={issue.identity}>
          <input type="radio" name="source-ticket" checked={selection === issue.identity}
            aria-label={`Select ${issue.identity}`} onChange={() => setSelection(issue.identity)} />
          <div>
            <div className="ticket-heading"><a className="ticket-link" href={issue.url} target="_blank" rel="noreferrer">{issue.identity}</a><strong>{issue.title}</strong></div>
            <div className="ticket-labels">{issue.labels.length
              ? issue.labels.map(label => <Badge key={label}>{label}</Badge>)
              : <span className="muted">No labels</span>}</div>
          </div>
        </div>)}</div>
      </fieldset>}
      <section className="ticket-submission" aria-label="Run submission">
        <label className="field">Target Workspace
          <select className="input" value={workspaceId} disabled={busy || !workspaces.length || Boolean(resource.error)}
            onChange={event => setWorkspaceId(event.target.value)}>
            <option value="">Choose a Workspace</option>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name} · {item.repository}</option>)}
          </select>
        </label>
        {resource.error ? <p className="notice" role="alert">{resource.error} <Button variant="outline" onClick={resource.refresh}>Reload Workspaces</Button></p>
          : !resource.data ? <p role="status">Loading Workspaces…</p>
          : !workspaces.length ? <p><a href="/workspaces">Configure a Workspace</a> to queue a Run.</p>
          : null}
        <dl>
          <dt>Source issue</dt><dd>{ticket ? `${ticket.identity} · ${ticket.title}` : "Choose an issue"}</dd>
          <dt>Target Workspace</dt><dd>{workspace ? `${workspace.name} · ${workspace.repository}` : "Choose a Workspace"}</dd>
        </dl>
        <Button disabled={!canQueue} onClick={queue}>{busy ? "Queuing Run…" : "Queue Run"}</Button>
        {submission?.error && <p className="notice" role="alert">{submission.error}</p>}
        {submission?.runId && <p role="status">Run queued. <a className="ticket-link" href={`/runs/${submission.runId}`}>{submission.runId}</a></p>}
      </section>
    </div>
  </main>;
}
