import React, { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "./api";
import { Button, Dialog, Input } from "./ui";

export function command(path, payload) {
  return api("/workspace/runs" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Shipyard-Workspace": "1" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(185000),
  });
}

export function Field({ label, ...props }) {
  return <label className="field"><span>{label}</span><Input {...props} /></label>;
}

function CaptureFields({ repository }) {
  return <>
    <Field label="Repository path" name="repository" defaultValue={repository} placeholder="/path/to/repository" required />
    <Field label="Markdown path or GitHub issue" name="source" placeholder="file:/path/request.md or github:owner/repo#123" required />
    <Field label="Settings path (optional)" name="settings" placeholder="Defaults to shipyard.settings.yaml in the repository" />
    <Field label="Base Git ref" name="ref" defaultValue="HEAD" required />
    <div className="field-pair">
      <Field label="Total time (seconds)" name="timeout" type="number" min="1" defaultValue="1800" required />
      <Field label="Verification reserve (seconds)" name="verification_reserve" type="number" min="1" defaultValue="300" required />
    </div>
  </>;
}

export function CommandDialog({ title, trigger, description, submitLabel, prepare, onDone, onError, children }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [request, setRequest] = useState(null);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    const fingerprint = JSON.stringify(fields);
    const id = request?.fingerprint === fingerprint ? request.id : crypto.randomUUID();
    setRequest({ fingerprint, id });
    setBusy(true);
    setError("");
    try {
      const [path, data] = prepare(fields, id);
      const result = await command(path, data);
      setOpen(false);
      setRequest(null);
      onDone(result);
    } catch (cause) {
      setError(cause.message);
      onError?.();
    } finally {
      setBusy(false);
    }
  }

  return <Dialog title={title} description={description} trigger={trigger} open={open}
    onOpenChange={value => { if (!busy) { setOpen(value); setError(""); } }}>
    <form className="command-form" onSubmit={submit}>
      <fieldset disabled={busy}>
        {children}
        {error && <p role="alert" className="notice">{error}</p>}
        <footer><Button type="submit" disabled={busy}>{busy ? "Submitting…" : submitLabel}</Button></footer>
      </fieldset>
    </form>
  </Dialog>;
}

function capturePayload(fields, request_id) {
  return {
    request_id,
    source: fields.source.trim(),
    repository: fields.repository.trim(),
    settings: fields.settings.trim() || null,
    ref: fields.ref.trim(),
    timeout: Number(fields.timeout),
    verification_reserve: Number(fields.verification_reserve),
  };
}

export function NewRun({ onDone, disabled }) {
  return <CommandDialog title="New Run" description="Review the source and execution settings before adding this Run to the local queue."
    trigger={<Button disabled={disabled}><Plus size={15} /> New Run</Button>} submitLabel="Queue Run"
    prepare={(fields, id) => ["", capturePayload(fields, id)]} onDone={onDone}>
    <CaptureFields />
  </CommandDialog>;
}

const recoverable = new Set(["EXECUTION_FAILED", "INVALID_STAGE_OUTPUT", "CREDENTIAL_UNAVAILABLE", "CREDENTIAL_REJECTED"]);
const reworkable = new Set(["TEST_FAILED", "CHANGES_REQUIRED"]);

export function RunActions({ record, id, onDone, onError, disabled }) {
  if (record.retirement || !record.run) return null;
  const deliveryActive = ["RUNNING", "QUEUED"].includes(record.state);
  const action = !deliveryActive && (reworkable.has(record.run.outcome) ? "rework" :
    recoverable.has(record.run.failure_reason) ? "recover" : null);

  return <div className="run-actions">
    {action && record.attempt_id && <ContinuationAction key={record.attempt_id} action={action}
      record={record} id={id} onDone={onDone} onError={onError} disabled={disabled} />}
    {record.run.lifecycle !== "CANCELLED" && <>
      <CommandDialog title="Cancel Run" description={`Cancel ${id}. Active execution will stop and the Run’s evidence will be retained.`}
        trigger={<Button disabled={disabled} variant="outline">Cancel Run</Button>} submitLabel="Confirm cancellation"
        prepare={fields => [`/${id}/cancel`, { reason: fields.reason }]} onDone={onDone} onError={onError}>
        <Field label="Reason" name="reason" maxLength="1000" required />
      </CommandDialog>
      <CommandDialog title="Supersede Run" description={`Retire ${id} and queue a Run with a new source and frozen contract.`}
        trigger={<Button disabled={disabled} variant="outline">Supersede</Button>} submitLabel="Queue replacement"
        prepare={(fields, requestId) => [`/${id}/supersede`, { ...capturePayload(fields, requestId), reason: fields.reason }]}
        onDone={onDone} onError={onError}>
        <Field label="Reason" name="reason" maxLength="1000" required />
        <CaptureFields repository={record.repository || record.submission.repository} />
      </CommandDialog>
    </>}
  </div>;
}

export function ContinuationAction({ action, record, id, onDone, onError, disabled, githubFeedback }) {
  const title = action === "rework" ? "Rework" : "Recover";
  return <CommandDialog title={`${title} Run`}
    description={`Start a new Attempt from Attempt ${record.attempt_number + 1} (${record.attempt_id}).`}
    trigger={<Button disabled={disabled} variant="outline">{githubFeedback ? "Rework with selected feedback" : title}</Button>}
    submitLabel={`Approve ${action}`}
    prepare={(fields, request_id) => [`/${id}/continue`, {
      request_id, action, expected_attempt_id: record.attempt_id, feedback: fields.feedback,
      additional_seconds: Number(fields.additional_seconds), github_feedback: githubFeedback,
    }]} onDone={onDone} onError={onError}>
    {githubFeedback && <p>{githubFeedback.ids.length} selected feedback items will be included.</p>}
    <label className="field"><span>{action === "rework" ? "Rework feedback" : "Recovery notes"}</span>
      <textarea className="input" name="feedback" rows="4" maxLength="32768" required={action === "rework" && !githubFeedback} />
    </label>
    <Field label="Additional time (seconds)" name="additional_seconds" type="number" min="0" defaultValue="0" required />
  </CommandDialog>;
}
