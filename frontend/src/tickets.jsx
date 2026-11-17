import React, { useEffect, useRef, useState } from "react";
import { Github } from "lucide-react";
import { ApiResponseError } from "./api";
import { Field, write } from "./run-actions";
import { Badge, Button } from "./ui";

const repositoryPattern = /^[A-Za-z0-9][A-Za-z0-9-]*\/(?!\.{1,2}$)[A-Za-z0-9_.-]+$/;
const runIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const githubActions = [
  "install GitHub CLI (gh), ensure it is on PATH, and try again.",
  "GitHub CLI timed out. Check network connectivity and retry.",
  "GitHub request failed. Run gh auth login and check access to the selected repository or issue.",
  "cannot start GitHub CLI (gh). Check installation, PATH and permissions.",
  "invalid response; check GitHub CLI (gh) installation and access to the selected issue.",
];
const invalidIssueList = "GitHub CLI returned an invalid issue list. Check the repository and GitHub CLI installation, then retry.";

function serviceGuidance(error, context, otherAction) {
  // The proxy's 400 envelope also carries generic exceptions and validation details.
  if (!(error instanceof ApiResponseError) || error.status !== 400) return undefined;
  if (error.message === otherAction) return otherAction;
  return githubActions.find(action => error.message === `${context}: ${action}`);
}

function validTicket(issue, repository) {
  const prefix = `${repository}#`;
  if (typeof issue?.identity !== "string" || !issue.identity.startsWith(prefix)) return false;
  const number = issue.identity.slice(prefix.length);
  const expectedUrl = `https://github.com/${repository}/issues/${number}`;
  return /^[1-9][0-9]*$/.test(number) &&
    typeof issue.title === "string" &&
    Array.isArray(issue.labels) && issue.labels.every(label => typeof label === "string") &&
    typeof issue.url === "string" && /^[\x00-\x7f]+$/.test(issue.url) &&
    issue.url.toLowerCase() === expectedUrl.toLowerCase();
}

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
      const response = await write("/tickets/list", { repository }, controller.signal);
      const issues = response?.issues;
      if (!Array.isArray(issues) || !issues.every(issue => validTicket(issue, repository))) {
        throw new Error("Invalid issue list");
      }
      if (!controller.signal.aborted) {
        setListing({ issues });
        setSelection(current => issues.some(issue => issue.identity === current) ? current : "");
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const guidance = serviceGuidance(error, `Cannot list issues in ${repository}`, invalidIssueList);
        const summary = error?.name === "TimeoutError" ? "The issue request timed out." : "Could not load issues.";
        setListing({
          error: guidance ?? `${summary} Check the local service and retry loading issues for ${repository}.`,
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
      const response = await write("/tickets/queue", {
        source,
        workspace_id: workspaceId,
        request_id: requestId,
      });
      const runId = response?.run_id;
      if (typeof runId !== "string" || !runIdPattern.test(runId)) throw new Error("Invalid Run ID");
      queueRequest.current = null;
      setSubmission({ source, workspaceId, runId });
    } catch (error) {
      queueRequest.current = { ...request, pending: false };
      const guidance = serviceGuidance(error, `Cannot capture GitHub issue github:${source}`);
      const missingWorkspace = error instanceof ApiResponseError && error.status === 400 && error.message === "Workspace was not found";
      const summary = error?.name === "TimeoutError" ? "The service response timed out." : "Could not confirm that the Run was queued.";
      setSubmission({
        source, workspaceId,
        error: guidance ?? (missingWorkspace
          ? "The selected Workspace was not found. Reload the Workspaces and choose an available target."
          : `${summary} Check the local service and retry with the same issue and Workspace.`),
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
        {submission?.error && submission.source === selection && submission.workspaceId === workspaceId &&
          <p className="notice" role="alert">{submission.error}</p>}
        {submission?.runId && <p role="status">Run queued. <a className="ticket-link" href={`/runs/${submission.runId}`}>{submission.runId}</a></p>}
      </section>
    </div>
  </main>;
}
