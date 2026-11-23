import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, House, Inbox, Play, Plug, Search, Settings } from "lucide-react";
import mark from "../../website/public/harborist-mark.png?no-inline";
import { matchesRun, runHref, runId } from "./run-view";
import { Badge, Button, Dialog, Input } from "./ui";

const pages = [
  ["Overview", "/", House],
  ["Inbox", "/tickets", Inbox],
  ["Runs", "/runs", Play],
  ["Workspaces", "/workspaces", Folder],
  ["Evidence", "/evidence", FileText],
  ["Integrations", "/integrations", Plug],
  ["Settings", "/settings", Settings],
];

export function pageName(path, selected) {
  if (selected || path.startsWith("/runs/")) return "Runs";
  return pages.find(([, href]) => href === path)?.[0] || "Overview";
}

export function serviceStatus(health) {
  if (health.error) return "Disconnected";
  if (!health.data) return "Connecting…";
  return health.data.stopping ? "Stopping" : "Running";
}

function CommandSearch({ records }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const input = useRef(null);
  useEffect(() => {
    function onKey(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !document.querySelector('[role="dialog"]')) {
        event.preventDefault();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const search = query.trim().toLowerCase();
  const destinations = pages.filter(([title]) => title.toLowerCase().includes(search));
  const runs = search ? records.filter(record => matchesRun(record, search)).slice(0, 8) : [];
  return <Dialog open={open} onOpenChange={next => { setOpen(next); if (!next) setQuery(""); }}
    title="Search Harborist" onOpenAutoFocus={event => { event.preventDefault(); input.current?.focus(); }}
    trigger={<Button className="command-search" variant="outline" aria-label="Search Harborist">
      <Search size={15} /><span>Search or run a command...</span><kbd>⌘ K</kbd>
    </Button>}>
    <Input ref={input} type="search" aria-label="Search pages and Runs" placeholder="Search pages and Runs…" value={query} onChange={event => setQuery(event.target.value)} />
    <ul className="command-results">
      {destinations.map(([title, href, Icon]) => <li key={href}><a href={href}><Icon size={16} />{title}</a></li>)}
      {runs.map(record => <li key={runId(record)}><a href={runHref(record)}><Play size={16} />{record.title || runId(record)}</a></li>)}
    </ul>
    {!destinations.length && !runs.length && <p className="muted">No matching pages or Runs.</p>}
  </Dialog>;
}

export function Shell({ page, health, workspaces, records, children, detail }) {
  const workspace = workspaces.length === 1 ? workspaces[0].name : null;
  const initials = workspace?.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase() || "H";
  const service = serviceStatus(health);

  return <div className="workspace" data-detail={Boolean(detail)}>
    <aside className="sidebar" aria-label="Workspace">
      <div className="window-lights" aria-hidden="true"><span /><span /><span /></div>
      <a className="brand" href="/"><img src={mark} width="40" height="40" alt="" /><span><strong>harborist</strong><small>harborist.dev</small></span></a>
      <p className="brand-tagline">Autonomous engineering.<br />Verified delivery.</p>
      <nav aria-label="Main navigation">{pages.map(([title, href, Icon]) =>
        <a className="nav-link" href={href} key={href} aria-current={page === title ? "page" : undefined}>
          <Icon size={17} /><span>{title}</span>
        </a>
      )}</nav>
      <div className="service-status" role="status">
        <span className="dot" data-tone={service === "Running" ? "green" : health.error ? "red" : "orange"} />
        <span><strong>Local service</strong><small>{service} · Loopback</small></span>
      </div>
      <a className="workspace-link" href="/workspaces"><span className="avatar" aria-hidden="true">{initials}</span>
        <span><strong>Local workspace</strong><small>{workspace || "Manage workspaces"}</small></span><ChevronDown size={13} />
      </a>
    </aside>
    <header className="shell-header">
      <div className="breadcrumb"><a href="/">harborist</a><ChevronRight size={13} /><span>{page}</span></div>
      <div className="header-tools"><CommandSearch records={records} /><Badge data-tone="green">Local</Badge>
        <a className="avatar" href="/settings" aria-label="Local settings">{initials}</a>
      </div>
    </header>
    {children}
    {detail}
  </div>;
}
