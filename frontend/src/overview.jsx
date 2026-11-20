import React from "react";
import { ArrowRight, Check, ChevronRight, CircleX, FlaskConical, Folder, Play, ShieldCheck, TriangleAlert } from "lucide-react";
import { NewRun } from "./run-actions";
import { group, label, lastStage, repo, runHref, runId, stages, status } from "./run-view";
import { serviceStatus } from "./shell";
import { Badge } from "./ui";

const week = 7 * 24 * 60 * 60 * 1000;
const time = record => Date.parse(record.updated_at || "") || 0;
const shortId = record => record.source_ref?.match(/#\d+$/)?.[0] || runId(record).slice(0, 8);

function Metric({ title, value, caption, icon: Icon, tone, href }) {
  return <a href={href} className="overview-card metric">
    <span className="overview-icon" data-tone={tone}><Icon size={22} /></span>
    <strong className="metric-value">{value}</strong>
    <strong className="metric-title">{title}</strong>
    <small>{caption}</small>
  </a>;
}

function StageTrack({ run }) {
  return <ol className="stage-track" aria-label="Run stages">
    {stages.map(stage => {
      const observation = run.stages?.[stage];
      const current = run.progress?.stage === stage && run.progress.state === "started";
      const state = current ? "running" : observation?.state || "not recorded";
      return <li key={stage} data-stage-state={state} aria-current={current ? "step" : undefined}>
        <span className="stage-marker" aria-hidden="true">{state === "completed" && <Check size={14} />}</span>
        <span>{stage.toUpperCase()}<span className="sr-only"> {state}</span></span>
      </li>;
    })}
  </ol>;
}

function ActiveExecution({ run, empty }) {
  const stage = run && lastStage(run)?.toUpperCase();
  const testing = run?.progress?.stage === "test" && run.progress.state === "started";
  return <section className="overview-card active-execution" aria-labelledby="active-execution">
    <header className="card-heading"><h2 id="active-execution">Active execution</h2>
      {run && <Badge data-tone="blue">Running{stage && " · " + stage}</Badge>}
    </header>
    {run ? <>
      <h3>{run.title || "Untitled request"}</h3>
      <p className="execution-meta">{shortId(run)} · {repo(run)} · Attempt {run.attempt_number + 1}</p>
      <StageTrack run={run} />
      <div className="checks-panel">
        <FlaskConical size={22} />
        <div><strong>Mandatory checks</strong>
          <p>{testing ? "TEST is running. REVIEW follows passing mandatory checks." : "Harborist runs mandatory checks during TEST."}</p>
        </div>
      </div>
      <footer><a href={runHref(run)}>Inspect Run <ArrowRight size={15} /></a></footer>
    </> : <p className="overview-empty">{empty}</p>}
  </section>;
}

function LocalSystem({ health, activeCount, queuedCount }) {
  const service = serviceStatus(health);
  const queue = activeCount == null ? "Unavailable" : [`${activeCount} active`, queuedCount ? `${queuedCount} queued` : null].filter(Boolean).join(" · ");
  return <section className="overview-card local-system" aria-labelledby="local-system">
    <header className="card-heading"><h2 id="local-system">Local system</h2></header>
    <dl>
      <dt>Orchestrator service</dt><dd><Badge data-tone={service === "Running" ? "green" : health.error ? "red" : undefined}>{service}</Badge></dd>
      <dt>Execution queue</dt><dd><a href="/runs?filter=Active"><Badge data-tone="blue">{queue}</Badge></a></dd>
      <dt>Codex CLI</dt><dd><a href="/integrations"><Badge>Check status</Badge></a></dd>
      <dt>GitHub CLI</dt><dd><a href="/integrations"><Badge>Check status</Badge></a></dd>
    </dl>
    <p>The local service continues executing after you close the browser.</p>
  </section>;
}

function OverviewRunRows({ records, verified = false }) {
  return <ul className="overview-rows">{records.map(record => {
    const result = status(record);
    const failed = result === "TEST_FAILED" || Boolean(record.run?.failure_reason) || ["FAILED", "INTERRUPTED"].includes(record.state);
    const Icon = verified ? ShieldCheck : failed ? CircleX : TriangleAlert;
    const tone = verified ? "green" : failed ? "red" : "orange";
    const badge = verified ? "Verified" : failed ? "Inspect logs" : result === "CHANGES_REQUIRED" && record.attempt_id ? "Rework eligible" : "Inspect Run";
    return <li key={runId(record)}><a href={runHref(record)}>
      <span className="overview-icon" data-tone={tone}><Icon size={21} /></span>
      <span className="overview-row-title"><strong>{record.title || "Untitled request"}</strong>
        <small>{shortId(record)} · {verified ? `Verified on candidate ${record.candidate_sha.slice(0, 7)}` : label(result)}</small>
      </span>
      <Badge data-tone={tone}>{badge}</Badge><ChevronRight className="row-chevron" size={15} />
    </a></li>;
  })}</ul>;
}

export function Overview({ history, health, workspaces, records, onDone }) {
  const active = records.filter(record => group(record) === "Active");
  const activeStage = active[0] && lastStage(active[0]);
  const attention = records.filter(record => group(record) === "Needs attention");
  const verified = records.filter(record => record.run?.outcome === "VERIFIED" && record.candidate_sha)
    .sort((first, second) => time(second) - time(first));
  const cutoff = Date.now() - week;
  const recentCount = verified.filter(record => time(record) >= cutoff).length;
  const workspaceList = workspaces.data?.workspaces;
  const empty = history.error ? "Run history is unavailable." : history.data ? "No active Run." : "Loading Runs…";
  const listEmpty = fallback => history.data ? fallback : empty;

  return <main className="overview">
    <div className="overview-heading">
      <div><h1>Overview</h1><p>Your engineering control center.</p></div>
      <NewRun workspaces={workspaceList || []} onDone={onDone} disabled={!history.data || Boolean(history.error)} />
    </div>
    {history.error && <p className="notice overview-notice" role="alert">{history.data ? "Disconnected. Showing the last available Runs." : history.error}</p>}
    <section className="overview-metrics" aria-label="Run and workspace summary">
      <Metric title="Active Run" value={history.data ? active.length : "—"} caption={activeStage ? activeStage.toUpperCase() + " stage" : "Execution queue"} icon={Play} tone="blue" href="/runs?filter=Active" />
      <Metric title="Needs attention" value={history.data ? attention.length : "—"} caption="Human decisions" icon={TriangleAlert} tone="orange" href="/runs?filter=Needs%20attention" />
      <Metric title="Verified · 7 days" value={history.data ? recentCount : "—"} caption="Exact commits" icon={ShieldCheck} tone="green" href="/evidence" />
      <Metric title="Workspaces" value={workspaceList?.length ?? "—"} caption="Local repositories" icon={Folder} tone="blue" href="/workspaces" />
    </section>
    <div className="overview-execution">
      <ActiveExecution run={active[0]} empty={empty} />
      <LocalSystem health={health} activeCount={history.data ? active.length : null} queuedCount={records.filter(record => group(record) === "Queued").length} />
    </div>
    <div className="overview-lists">
      <section className="overview-card" aria-labelledby="attention-title">
        <header className="card-heading"><h2 id="attention-title">Needs your attention</h2>
          {history.data && <a href="/runs?filter=Needs%20attention"><Badge data-tone="orange">{attention.length} {attention.length === 1 ? "item" : "items"}</Badge></a>}
        </header>
        {attention.length ? <OverviewRunRows records={attention.slice(0, 2)} /> : <p className="overview-empty">{listEmpty("No Runs need attention.")}</p>}
      </section>
      <section className="overview-card" aria-labelledby="verified-title">
        <header className="card-heading"><h2 id="verified-title">Recently verified</h2><a href="/runs">See all Runs <ArrowRight size={14} /></a></header>
        {verified.length ? <OverviewRunRows records={verified.slice(0, 2)} verified /> : <p className="overview-empty">{listEmpty("No verified Runs yet.")}</p>}
      </section>
    </div>
  </main>;
}

export function Evidence({ history, records }) {
  const evidence = records.filter(record => Object.keys(record.artifacts || {}).length);
  return <main>
    <div className="page-heading"><h1>Evidence</h1></div>
    {history.error && <p className="notice settings-notice" role="alert">{history.error}</p>}
    {!history.data && !history.error && <p className="empty" role="status">Loading evidence…</p>}
    {history.data && !evidence.length && <p className="empty">Packaged Run evidence will appear here.</p>}
    <div className="settings-list">{evidence.map(record => <a key={runId(record)} className="settings-row" href={runHref(record)}>
      <Folder size={18} /><div><h2>{record.title || "Untitled request"}</h2><p className="muted">{Object.keys(record.artifacts).join(" · ")}</p></div><ChevronRight size={16} />
    </a>)}</div>
  </main>;
}
