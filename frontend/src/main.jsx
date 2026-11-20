import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ChevronRight, Circle, FileText, Folder, GitBranch, Inbox, Plug, RefreshCw, Search, X } from "lucide-react";
import { useResource } from "./api";
import { GitHubDelivery } from "./github-delivery";
import { Integrations } from "./integrations";
import { Evidence, Overview } from "./overview";
import { group, label, lastStage, matchesRun, repo, runId, stages, status } from "./run-view";
import { pageName, Shell } from "./shell";
import { TicketInbox } from "./tickets";
import { Workspaces } from "./workspaces";
import { NewRun, RunActions } from "./run-actions";
import { Badge, Button, Dialog, Input } from "./ui";
import "./style.css";
import "./dashboard.css";

const filters = ["All", "Active", "Queued", "Needs attention"];
const groups = [...filters.slice(1), "History"];

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
      <Button aria-label="Close Run detail" variant="ghost" asChild><a href="/runs" onClick={close}><X size={17} /></a></Button>
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

function Settings() {
  return <main>
    <div className="page-heading"><h1>Settings</h1></div>
    <div className="settings-list">
      <a className="settings-row" href="/workspaces"><Folder size={18} /><div><h2>Workspace defaults</h2><p className="muted">Manage local repositories and defaults for new Runs.</p></div><ChevronRight size={16} /></a>
      <a className="settings-row" href="/integrations"><Plug size={18} /><div><h2>Integrations</h2><p className="muted">Manage agent and execution settings.</p></div><ChevronRight size={16} /></a>
    </div>
  </main>;
}

function Workspace() {
  const [selected, setSelected] = useState(selection);
  const page = pageName(location.pathname, selected);
  const runsPage = page === "Runs";
  useEffect(() => { document.title = `Harborist · ${page}`; }, [page]);
  const workspaces = useResource("/workspaces");
  const history = useResource("/runs", true);
  const health = useResource("/health", true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(() => {
    const fromUrl = new URLSearchParams(location.search).get("filter");
    return filters.includes(fromUrl) ? fromUrl : "All";
  });
  useEffect(() => {
    const onRoute = () => setSelected(selection());
    window.addEventListener("popstate", onRoute);
    window.addEventListener("hashchange", onRoute);
    return () => {
      window.removeEventListener("popstate", onRoute);
      window.removeEventListener("hashchange", onRoute);
    };
  }, []);

  function navigate(event, id) {
    if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    if (id !== selected) window.history.pushState(null, "", id ? `/runs/${id}` : "/runs");
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
  const matched = runsPage ? records.filter(record => matchesRun(record, query)) : [];
  const visible = filter === "All" ? matched : matched.filter(record => group(record) === filter);
  const details = selected && records.find(record => runId(record) === selected);

  const checkout = details && (details.repository || details.submission.repository);
  const destinations = [...new Set((workspaces.data?.workspaces || [])
    .filter(item => item.repository === checkout && item.github_repository)
    .map(item => item.github_repository))];
  const destination = destinations.length === 1 ? destinations[0] : undefined;

  const detail = runsPage && selected ? <RunDetail destination={destination} key={selected} id={selected}
    record={details} close={event => navigate(event, "")} onDone={onDone} onError={history.refresh} disabled={Boolean(history.error)} /> : null;

  return <Shell page={page} health={health} workspaces={workspaces.data?.workspaces || []} records={records} detail={detail}>
    {page === "Overview" && <Overview history={history} health={health} workspaces={workspaces} records={records} onDone={onDone} />}
    {page === "Inbox" && <TicketInbox resource={workspaces} />}
    {page === "Integrations" && <Integrations resource={workspaces} />}
    {page === "Workspaces" && <Workspaces resource={workspaces} />}
    {page === "Evidence" && <Evidence history={history} records={records} />}
    {page === "Settings" && <Settings />}
    {runsPage && <main>
      <div className="page-heading"><h1>Runs</h1><span className="muted">{records.length} total</span><NewRun workspaces={workspaces.data?.workspaces || []} onDone={onDone} disabled={!history.data || Boolean(history.error)} /></div>
      <div className="toolbar">
        <div className="search"><Search size={15} /><Input type="search" aria-label="Search Runs" placeholder="Search runs…" value={query} onChange={event => setQuery(event.target.value)} /></div>
        <Button variant="ghost" aria-label="Refresh Runs" onClick={history.refresh}><RefreshCw size={15} /></Button>
        <div className="filters" aria-label="Filter Runs">{filters.map(value =>
          <Button key={value} variant={filter === value ? "outline" : "ghost"} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value}</Button>)}</div>
      </div>
      {history.error && <p className="notice" role="alert">{history.data ? "Disconnected. Showing the last available runs." : history.error}</p>}
      <div className="run-list">
        {!history.data && !history.error && <div className="empty" role="status">Loading Runs…</div>}
        {history.data && visible.length === 0 && <div className="empty"><Inbox size={21} /><h2>{records.length ? "No matching Runs" : "No Runs yet"}</h2><p>{records.length ? "Try a different search or filter." : "Runs submitted through Harborist appear here."}</p></div>}
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
  </Shell>;
}

createRoot(document.getElementById("root")).render(<Workspace />);
