import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Anchor, ChevronRight, Circle, FileText, GitBranch, Inbox, RefreshCw, Search, X } from "lucide-react";
import { useResource } from "./api";
import { Badge, Button, Dialog, Input } from "./ui";
import "./style.css";

const stages = ["intake", "design", "plan", "build", "test", "review", "package"];
const filters = ["All", "Active", "Queued", "Needs attention"];
const groups = [...filters.slice(1), "History"];
const label = value => value?.toLowerCase().replaceAll("_", " ") || "Unavailable";
const runId = record => record.submission.run_id;
const repo = record => record.submission.repository?.split("/").filter(Boolean).at(-1) || "Unavailable";
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

function Artifact({ id, name }) {
  const [open, setOpen] = useState(false);
  const resource = useResource(open ? `/runs/${id}/artifacts/${name}` : null);
  return <Dialog open={open} onOpenChange={setOpen} title={name}
    trigger={<Button className="artifact" variant="outline"><FileText size={15} />{name}<ChevronRight size={14} /></Button>}>
    {resource.error ? <p role="alert">{resource.error}</p> :
      resource.data ? <pre tabIndex={0}>{resource.data.content}</pre> : <p role="status">Loading evidence…</p>}
  </Dialog>;
}

function RunDetail({ record, id, close }) {
  return <aside className="detail" aria-label="Run detail">
    <header className="detail-header">
      <span className="muted">Run detail</span>
      <Button aria-label="Close Run detail" variant="ghost" asChild><a href="/" onClick={close}><X size={17} /></a></Button>
    </header>
    {record ? <>
      <div className="detail-heading">
        <Status record={record} />
        <h2>{record.title || "Untitled request"}</h2>
        <p className="mono muted">{id}</p>
      </div>
      <section>
        <h3>Execution</h3>
        <dl>
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
          if (observation?.reason && ["TEST_FAILED", "CHANGES_REQUIRED", "NEEDS_CLARIFICATION", "NEEDS_RESCOPING"].includes(observation.reason)) state = label(observation.reason);
          return <li key={stage}><Circle size={13} data-stage-status={state} /><span>{stage.toUpperCase()}</span>
            <span className="muted">{state}</span>{record.stage_errors?.[stage] && <small>{record.stage_errors[stage]}</small>}</li>;
        })}</ol>
      </section>
      <section>
        <h3>Evidence</h3>
        <div className="artifact-list">{["report.md", "evidence.json"].filter(name => record.artifacts?.[name]).map(name =>
          <Artifact key={name} id={id} name={name} />)}</div>
        {!Object.values(record.artifacts || {}).some(Boolean) && <p className="muted">No terminal evidence available.</p>}
      </section>
    </> : <p className="notice">This Run is unavailable in the current history.</p>}
  </aside>;
}

function Status({ record }) {
  return <Badge className={`status status-${group(record).toLowerCase().replaceAll(" ", "-")}`}>
    <span className="dot" />{label(status(record))}
  </Badge>;
}

function Workspace() {
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

  const records = history.data?.runs.toReversed() || [];
  const matched = records.filter(record => [record.title, runId(record), repo(record), status(record), record.state, lastStage(record), record.candidate_sha]
    .join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  const visible = filter === "All" ? matched : matched.filter(record => group(record) === filter);
  const details = selected && records.find(record => runId(record) === selected);

  return <div className="workspace" data-detail={Boolean(selected)}>
    <aside className="sidebar" aria-label="Workspace">
      <a className="brand" href="/" onClick={event => navigate(event, "")}><span><Anchor size={16} /></span>Shipyard</a>
      <nav><a className="nav-link" href="/" onClick={event => navigate(event, "")} aria-current="page"><Inbox size={16} /> Runs</a></nav>
      <div className="service-status" role="status"><span className={cnService(history)} /><span>{history.error ? "Disconnected" : history.data ? "Local service" : "Connecting…"}</span></div>
    </aside>
    <main>
      <header className="topbar"><Activity size={15} /><span>Runs</span><Button variant="ghost" aria-label="Refresh Runs" onClick={history.refresh}><RefreshCw size={15} /></Button></header>
      <div className="page-heading"><h1>Runs</h1><span className="muted">{records.length} total</span></div>
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
              <span className="run-title"><strong>{record.title || "Untitled request"}</strong><small className="mono">{runId(record).slice(0, 8)}</small></span>
              <span className="repo"><GitBranch size={13} />{repo(record)}</span>
              <span className="run-stage">{lastStage(record)?.toUpperCase() || "—"}</span>
              <Status record={record} />
            </a>)}
          </section>;
        })}
      </div>
    </main>
    {selected && <RunDetail key={selected} id={selected} record={details} close={event => navigate(event, "")} />}
  </div>;
}

function cnService(resource) {
  return resource.error ? "dot disconnected" : resource.data ? "dot connected" : "dot";
}

createRoot(document.getElementById("root")).render(<Workspace />);
