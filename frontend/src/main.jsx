import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Anchor, ChevronRight, Circle, FileText, FolderGit2, GitBranch, Inbox, Play, Plug, RefreshCw, Search, X } from "lucide-react";
import { useResource } from "./api";
import { GitHubDelivery } from "./github-delivery";
import { Integrations } from "./integrations";
import { TicketInbox } from "./tickets";
import { Workspaces } from "./workspaces";
import { NewRun, RunActions } from "./run-actions";
import { Badge, Button, Dialog, Input } from "./ui";
import "./style.css";

const stages = ["intake", "design", "plan", "build", "test", "review", "package"];
const filters = ["All", "Active", "Queued", "Needs attention"];
const groups = [...filters.slice(1), "History"];
const label = value => value?.toLowerCase().replaceAll("_", " ") || "Unavailable";
const runId = record => record.submission.run_id;
const repo = record => (record.repository || record.submission.repository)?.split("/").filter(Boolean).at(-1) || "Unavailable";
const lastStage = record => record.progress?.stage || stages.findLast(stage => record.stages?.[stage]);
const status = record => record.retirement ? (record.retirement.replacement ? "SUPERSEDED" : "CANCELLED") : record.run?.outcome || record.run?.failure_reason || record.state || record.run?.lifecycle;

function group(record) {
  if (record.retirement) return "History";
  if (record.state === "RUNNING") return "Active";
  if (record.state === "QUEUED") return "Queued";
  return ["FAILED", "INTERRUPTED"].includes(record.state) ||
    record.run?.failure_reason || (record.run?.outcome && record.run.outcome !== "VERIFIED")
    ? "Needs attention" : "History";
}

function selection() {
  return location.pathname.match(/^\/runs\/([^/]+)$/)?.[1] || location.hash.slice(1);
}

function Artifact({ id, name, attempt, title = name }) {
  const [open, setOpen] = useState(false);
  const resource = useResource(open ? `/runs/${id}/attempts/${attempt}/artifacts/${name}` : null);
  return <Dialog open={open} onOpenChange={setOpen} title={title}
    trigger={<Button className="artifact" variant="outline"><FileText size={15} />{title}<ChevronRight size={14} /></Button>}>
    {resource.error ? <p role="alert">{resource.error}</p> :
      resource.data ? <pre tabIndex={0}>{resource.data.content}</pre> : <p role="status">Loading evidence…</p>}
  </Dialog>;
}

function RunDetail({ record: latest, id, close, onDone, onError, disabled, destination }) {
  const [attempt, setAttempt] = useState(null);
  const number = attempt ?? latest?.attempt_number;
  const prefix = `/runs/${id}/attempts`;
  const attempts = useResource(latest ? prefix : null, true);
  const evidence = useResource(number == null ? null : `${prefix}/${number}`, true);
  const record = evidence.data || (attempt == null ? latest : null);
  const failed = (evidence.data?.checks || []).map((check, index) => ({ ...check, index })).filter(check => !check.passed);
  return <aside className="detail" aria-label="Run detail">
    <header className="detail-header">
      <span className="muted">Run detail</span>
      <Button aria-label="Close Run detail" variant="ghost" asChild><a href="/" onClick={close}><X size={17} /></a></Button>
    </header>
    {latest && <label className="attempt-picker">Attempt
      <select className="input" value={attempt ?? ""} onChange={event => setAttempt(event.target.value === "" ? null : Number(event.target.value))}>
        <option value="">Latest · {latest.attempt_number + 1}</option>
        {(attempts.data?.attempts || []).filter(value => value < latest.attempt_number).map(value => <option key={value} value={value}>Attempt {value + 1}</option>)}
      </select>
    </label>}
    {evidence.error && <p className="notice" role="alert">{evidence.error}</p>}
    {record ? <>
      <div className="detail-heading">
        <Status record={record} />
        <h2>{record.title || "Untitled request"}</h2>
        <p className="mono muted">{id}</p>
      </div>
      {attempt == null && <RunActions record={latest} id={id} onDone={onDone} onError={onError} disabled={disabled} />}
      {failed.length > 0 && <section>
        <h3>Failed checks</h3>
        {failed.map(check => <div className="notice" key={check.id}>
          <strong>{check.id}</strong><p>{check.error || (check.timed_out ? "Timed out" : `Exit code ${check.returncode}`)}</p>
          <div className="artifact-list">{["stdout", "stderr"].map(stream =>
            <Artifact key={stream} id={id} attempt={number}
              name={`test-${String(check.index).padStart(4, "0")}-${stream}`}
              title={`${stream}${check[stream + "_truncated"] ? " · truncated" : ""}`} />)}</div>
        </div>)}
      </section>}
      <section>
        <h3>Execution</h3>
        <dl>
          {record.source_url && <><dt>Source ticket</dt><dd><a className="ticket-link" href={record.source_url} target="_blank" rel="noreferrer">{record.source_ref?.replace(/^github:/, "")}</a></dd></>}
          <dt>Repository</dt><dd>{repo(record)}</dd>
          <dt>Delivery</dt><dd>{label(record.state)}</dd>
          <dt>Lifecycle</dt><dd>{label(record.run?.lifecycle)}</dd>
          <dt>Outcome</dt><dd>{label(record.run?.outcome)}</dd>
          <dt>Attempt</dt><dd className="mono">{record.attempt_id || "Unavailable"}</dd>
          {record.candidate_sha && <><dt>Verified commit</dt><dd className="mono">{record.candidate_sha}</dd></>}
          {record.retirement && <><dt>Reason</dt><dd>{record.retirement.reason}</dd></>}
          {record.retirement?.replacement && <><dt>Replacement</dt><dd><a href={`/runs/${record.retirement.replacement}`}>{record.retirement.replacement}</a></dd></>}
        </dl>
        {[record.error, record.run_error, record.run?.failure_reason].filter(Boolean).map((error, index) => <p key={index} className="notice">{error}</p>)}
      </section>
      <section>
        <h3>Stage timeline</h3>
        <ol className="timeline">{stages.map(stage => {
          const observation = record.stages?.[stage];
          let state = observation?.state || (stage === "intake" && record.run ? "completed" : "not recorded");
          if (state === "started") state = record.state === "RUNNING" ? "running" : "interrupted";
          if (state !== "skipped" && observation?.reason && ["TEST_FAILED", "CHANGES_REQUIRED", "NEEDS_CLARIFICATION", "NEEDS_RESCOPING"].includes(observation.reason)) state = label(observation.reason);
          return <li key={stage}><Circle size={13} data-stage-status={state} /><span>{stage.toUpperCase()}</span>
            <span className="muted">{state}</span>{record.stage_errors?.[stage] && <small>{record.stage_errors[stage]}</small>}</li>;
        })}</ol>
      </section>
      {record.run?.verification && <section>
        <h3>Verification</h3>
        <ul className="github-checks">{record.run.verification.checks.map(check =>
          <li key={check.id}>{check.id}<Badge>TEST passed</Badge></li>)}
          {record.run.verification.review.criteria.map(criterion =>
            <li key={criterion.criterion_id}>{criterion.criterion_id}<Badge>REVIEW passed</Badge></li>)}</ul>
      </section>}
      <section>
        <h3>Evidence</h3>
        <div className="artifact-list">{["report.md", "evidence.json"].filter(name => record.artifacts?.[name]).map(name =>
          <Artifact key={name} id={id} attempt={number} name={name} />)}
        {evidence.data?.has_specification && <Artifact id={id} attempt={number} name="spec.md" />}</div>
        {!evidence.data?.has_specification && !Object.values(record.artifacts || {}).some(Boolean) && <p className="muted">No terminal evidence available.</p>}
      </section>
      {attempt == null && <GitHubDelivery destination={destination} record={latest} id={id} disabled={disabled} onDone={onDone} onError={onError} />}
    </> : <p className="notice">{latest && !evidence.error ? "Loading Attempt…" : "This Run is unavailable in the current history."}</p>}
  </aside>;
}

function Status({ record }) {
  return <Badge className={`status status-${group(record).toLowerCase().replaceAll(" ", "-")}`}>
    <span className="dot" />{label(status(record))}
  </Badge>;
}

function Workspace() {
  const ticketPage = location.pathname === "/tickets";
  const integrationsPage = location.pathname === "/integrations";
  const workspacePage = location.pathname === "/workspaces";
  const page = ticketPage ? "Inbox" : integrationsPage ? "Integrations" : workspacePage ? "Workspaces" : "Runs";
  const runsPage = page === "Runs";
  useEffect(() => {
    document.title = `Shipyard · ${page}`;
  }, [page]);
  const workspaces = useResource("/workspaces");
  const history = useResource("/runs", true);
  const [selected, setSelected] = useState(selection);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const search = useRef(null);
  useEffect(() => {
    function onKey(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !document.querySelector('[role="dialog"]')) {
        event.preventDefault();
        search.current?.focus();
      }
    }
    const onRoute = () => setSelected(selection());
    window.addEventListener("popstate", onRoute);
    window.addEventListener("hashchange", onRoute);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("popstate", onRoute);
      window.removeEventListener("hashchange", onRoute);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  function navigate(event, id) {
    if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    if (id !== selected) window.history.pushState(null, "", id ? `/runs/${id}` : "/");
    setSelected(id);
  }

  function onDone(result) {
    history.refresh();
    setQuery("");
    setFilter("All");
    if (result.run_id && result.run_id !== selected) {
      window.history.pushState(null, "", `/runs/${result.run_id}`);
      setSelected(result.run_id);
    }
  }

  const records = history.data?.runs.toReversed() || [];
  const matched = records.filter(record => [record.title, runId(record), repo(record), status(record), record.state, lastStage(record), record.candidate_sha]
    .join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  const visible = filter === "All" ? matched : matched.filter(record => group(record) === filter);
  const details = selected && records.find(record => runId(record) === selected);

  const checkout = details && (details.repository || details.submission.repository);
  const destinations = [...new Set((workspaces.data?.workspaces || [])
    .filter(item => item.repository === checkout && item.github_repository)
    .map(item => item.github_repository))];
  const destination = destinations.length === 1 ? destinations[0] : undefined;

  return <div className="workspace" data-detail={runsPage && Boolean(selected)}>
    <aside className="sidebar" aria-label="Workspace">
      <a className="brand" href="/"><span><Anchor size={16} /></span>Shipyard</a>
      <nav><a className="nav-link" href="/tickets" aria-current={ticketPage ? "page" : undefined}><Inbox size={16} /> Inbox</a><a className="nav-link" href="/" aria-current={runsPage ? "page" : undefined}><Play size={16} /> Runs</a><a className="nav-link" href="/workspaces" aria-current={workspacePage ? "page" : undefined}><FolderGit2 size={16} /> Workspaces</a><a className="nav-link" href="/integrations" aria-current={integrationsPage ? "page" : undefined}><Plug size={16} /> Integrations</a></nav>
      <div className="service-status" role="status"><span className={cnService(history)} /><span>{history.error ? "Disconnected" : history.data ? "Local service" : "Connecting…"}</span></div>
    </aside>
    {ticketPage ? <TicketInbox resource={workspaces} /> : integrationsPage ? <Integrations resource={workspaces} /> : workspacePage ? <Workspaces resource={workspaces} /> : <main>
      <header className="topbar"><Activity size={15} /><span>Runs</span><Button variant="ghost" aria-label="Refresh Runs" onClick={history.refresh}><RefreshCw size={15} /></Button></header>
      <div className="page-heading"><h1>Runs</h1><span className="muted">{records.length} total</span><NewRun workspaces={workspaces.data?.workspaces || []} onDone={onDone} disabled={!history.data || Boolean(history.error)} /></div>
      <div className="toolbar">
        <div className="search"><Search size={15} /><Input type="search" ref={search} aria-label="Search Runs" placeholder="Search runs…" value={query} onChange={event => setQuery(event.target.value)} /><kbd>⌘ K</kbd></div>
        <div className="filters" aria-label="Filter Runs">{filters.map(value =>
          <Button key={value} variant={filter === value ? "outline" : "ghost"} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value}</Button>)}</div>
      </div>
      {history.error && <p className="notice" role="alert">{history.data ? "Disconnected. Showing the last available runs." : history.error}</p>}
      <div className="run-list">
        {!history.data && !history.error && <div className="empty" role="status">Loading Runs…</div>}
        {history.data && visible.length === 0 && <div className="empty"><Inbox size={21} /><h2>{records.length ? "No matching Runs" : "No Runs yet"}</h2><p>{records.length ? "Try a different search or filter." : "Runs submitted through Shipyard appear here."}</p></div>}
        {groups.map(name => {
          const rows = visible.filter(record => group(record) === name);
          return rows.length > 0 && <section key={name} className="run-group" aria-label={name}>
            <h2>{name} <Badge>{rows.length}</Badge></h2>
            {rows.map(record => <a key={runId(record)} href={`/runs/${runId(record)}`} className="run-row" aria-current={selected === runId(record) ? "page" : undefined} onClick={event => navigate(event, runId(record))}>
              <span className="run-title"><strong>{record.title || "Untitled request"}</strong><small className="mono">{runId(record).slice(0, 8)}{record.state && record.state !== status(record) ? ` · ${label(record.state)}` : ""}</small></span>
              <span className="repo"><GitBranch size={13} />{repo(record)}</span>
              <span className="run-stage">{lastStage(record)?.toUpperCase() || "—"}</span>
              <Status record={record} />
            </a>)}
          </section>;
        })}
      </div>
    </main>}
    {runsPage && selected && <RunDetail destination={destination} key={selected} id={selected} record={details} close={event => navigate(event, "")} onDone={onDone} onError={history.refresh} disabled={Boolean(history.error)} />}
  </div>;
}

function cnService(resource) {
  return resource.error ? "dot disconnected" : resource.data ? "dot connected" : "dot";
}

createRoot(document.getElementById("root")).render(<Workspace />);
