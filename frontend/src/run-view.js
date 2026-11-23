export const stages = ["intake", "design", "plan", "build", "test", "review", "package"];
export const label = value => value?.toLowerCase().replaceAll("_", " ") || "Unavailable";
export const runId = record => record.submission.run_id;
export const runHref = record => "/runs/" + runId(record);
export const repo = record => (record.repository || record.submission.repository)?.split("/").filter(Boolean).at(-1) || "Unavailable";
export const lastStage = record => record.progress?.stage || stages.findLast(stage => record.stages?.[stage]);
export const status = record => record.retirement ? (record.retirement.replacement ? "SUPERSEDED" : "CANCELLED") : record.run?.outcome || record.run?.failure_reason || record.state || record.run?.lifecycle;

export function group(record) {
  if (record.retirement) return "History";
  if (record.state === "RUNNING") return "Active";
  if (record.state === "QUEUED") return "Queued";
  return ["FAILED", "INTERRUPTED"].includes(record.state) ||
    record.run?.failure_reason || (record.run?.outcome && record.run.outcome !== "VERIFIED")
    ? "Needs attention" : "History";
}

export function matchesRun(record, query) {
  return [record.title, runId(record), repo(record), status(record), record.state, lastStage(record), record.candidate_sha]
    .join(" ").toLowerCase().includes(query.trim().toLowerCase());
}
