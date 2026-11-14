import React, { useState } from "react";
import { ExternalLink, RefreshCw, Upload } from "lucide-react";
import { useResource } from "./api";
import { CommandDialog, ContinuationAction, Field, command } from "./run-actions";
import { Badge, Button } from "./ui";

function Publish({ id, record, receipt, disabled, refresh }) {
  return <CommandDialog title="Approve GitHub publication"
    description={`Publish the verified commit from Attempt ${record.attempt_number + 1} to a GitHub pull request.`}
    trigger={<Button variant="outline" disabled={disabled}><Upload size={15} /> Publish…</Button>}
    submitLabel="Approve and publish"
    prepare={fields => [`/${id}/publish`, {
      approve: record.candidate_sha, expected_attempt: record.attempt_id,
      destination: fields.destination.trim(), base: fields.base.trim(),
      expect_head: receipt?.candidate || null,
    }]} onDone={refresh} onError={refresh}>
    <dl className="approval">
      <dt>Run</dt><dd className="mono">{id}</dd>
      <dt>Attempt</dt><dd className="mono">{record.attempt_id}</dd>
      <dt>Verified commit</dt><dd className="mono">{record.candidate_sha}</dd>
      <dt>Branch</dt><dd className="mono">shipyard/{id}</dd>
      {receipt?.pull && <><dt>Existing PR</dt><dd>#{receipt.pull}</dd>
        <dt>Expected head</dt><dd className="mono">{receipt.candidate}</dd></>}
    </dl>
    <Field label="Destination repository" name="destination" placeholder="owner/repository" defaultValue={receipt?.repository} readOnly={Boolean(receipt)} required />
    <Field label="Base branch" name="base" placeholder="main" defaultValue={receipt?.base} readOnly={Boolean(receipt)} required />
  </CommandDialog>;
}

function Collaboration({ id, record, data, disabled, onDone, onError }) {
  const observation = data.observation;
  const [selected, setSelected] = useState([]);
  const feedback = observation.feedback || [];
  const eligible = record.candidate_sha === observation.verified_candidate && !record.retirement &&
    !["QUEUED", "RUNNING"].includes(record.state);
  const checks = observation.checks.check_runs;
  const statuses = observation.statuses.statuses;
  return <>
    <dl>
      <dt>PR status</dt><dd>{observation.state}</dd>
      <dt>Observed</dt><dd>{new Date(observation.observed_at).toLocaleString()}</dd>
      <dt>PR head</dt><dd className="mono">{observation.head}</dd>
      <dt>Published commit</dt><dd className="mono">{observation.verified_candidate}</dd>
      <dt>Head verified</dt><dd>{observation.head_verified ? "Matches published verification" : "Head changed"}</dd>
      {observation.merge_commit_sha && <><dt>Merge commit</dt><dd className="mono">{observation.merge_commit_sha}</dd></>}
    </dl>
    <h4>GitHub checks</h4>
    {checks.length + statuses.length === 0 && <p className="muted">No GitHub checks in this observation.</p>}
    <ul className="github-checks">
      {checks.map((check, index) => <li key={index}>{check.name}<Badge>{check.conclusion || check.status}</Badge></li>)}
      {statuses.map((status, index) => <li key={index}>{status.context}<Badge>{status.state}</Badge></li>)}
    </ul>
    {observation.checks.total_count > checks.length || observation.statuses.total_count > statuses.length
      ? <p className="muted">GitHub returned a limited set of checks.</p> : null}
    <h4>Review feedback</h4>
    {feedback.length === 0 && <p className="muted">No feedback in this observation.</p>}
    {feedback.map(item => <label className="feedback-item" key={item.key}>
      {eligible && <input type="checkbox" checked={selected.includes(item.key)}
        disabled={disabled || (selected.length >= 32 && !selected.includes(item.key))}
        onChange={event => setSelected(current => event.target.checked ? [...current, item.key] : current.filter(key => key !== item.key))} />}
      <span><strong>{item.author}</strong><small>{item.key}</small><span>{item.body}</span></span>
    </label>)}
    {eligible && selected.length > 0 && <ContinuationAction action="rework" id={id} record={record}
      disabled={disabled} githubFeedback={{ observation: data.observation_path, ids: selected }}
      onDone={onDone} onError={onError} />}
  </>;
}

export function GitHubDelivery({ record, id, disabled, onDone, onError }) {
  const resource = useResource(`/runs/${id}/github`);
  const [error, setError] = useState("");
  const [observing, setObserving] = useState(false);
  const receipt = resource.data?.publication;
  const observation = resource.data?.observation;
  const canPublish = record.candidate_sha && record.attempt_id && !record.retirement &&
    record.package_available && !["QUEUED", "RUNNING"].includes(record.state);

  function refresh() {
    resource.refresh();
    onError?.();
  }

  async function observe() {
    setObserving(true);
    setError("");
    try {
      await command(`/${id}/observe`, {});
      resource.refresh();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setObserving(false);
    }
  }

  return <section className="github-delivery">
    <h3>GitHub delivery</h3>
    {!resource.data && !resource.error && <p role="status" className="muted">Loading GitHub delivery…</p>}
    {resource.error && <p role="alert" className="notice">{resource.error}</p>}
    {error && <p role="alert" className="notice">{error}</p>}
    {resource.data && !receipt && <p className="muted">No GitHub publication yet.</p>}
    {receipt && <dl>
      <dt>Destination</dt><dd>{receipt.repository} → {receipt.base}</dd>
      <dt>Published</dt><dd>{new Date(receipt.timestamp).toLocaleString()}</dd>
      <dt>Commit</dt><dd className="mono">{receipt.candidate}</dd>
      {receipt.pull && <><dt>Pull request</dt><dd><a href={`https://github.com/${receipt.repository}/pull/${receipt.pull}`} target="_blank" rel="noreferrer">#{receipt.pull} <ExternalLink size={13} /></a></dd></>}
    </dl>}
    <div className="github-actions">
      {canPublish && resource.data && !resource.error && <Publish key={record.attempt_id} id={id} record={record} receipt={receipt} disabled={disabled} refresh={refresh} />}
      {receipt?.pull && <Button variant="outline" disabled={disabled || observing} onClick={observe}><RefreshCw size={14} />{observing ? "Refreshing…" : "Refresh PR evidence"}</Button>}
    </div>
    {observation && <Collaboration key={resource.data.observation_path} id={id} record={record} data={resource.data}
      disabled={disabled} onDone={onDone} onError={refresh} />}
  </section>;
}
