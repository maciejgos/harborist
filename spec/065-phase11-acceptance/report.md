# Phase 11 acceptance audit

Completed 2026-11-04. Specifications 061–065 cover explicit local rework/recovery,
immutable Attempt history, frozen upstream reuse, cumulative budget accounting,
and CLI/service integration. GitHub publication remains Phase 12.

## Acceptance evidence

| Requirement | Evidence |
| --- | --- |
| New Attempt identity, same frozen Run | `tests/domain/test_continuation.py`; repeated real-Git rework in `tests/application/test_phase11_acceptance.py` |
| Rework starts at PLAN and the prior candidate | `test_rework_retests_descendant_with_frozen_spec`; actual Git parent-SHA assertions |
| Fresh execution after provider/output failure | Domain failure allowlist; `test_recovery_before_design_starts_fresh` and `test_recovery_after_review_failure_reverifies_new_candidate` |
| No session resume or inherited verification | NativeAgent requests remain fresh; each descendant runs trusted TEST and independent REVIEW with new Attempt/candidate attribution |
| Immutable predecessor records | `test_attempt_storage_preserves_predecessor_and_rejects_stale_request`; repeated rework checks every retained original evidence file |
| Spec survives interrupted rework | `test_interrupted_rework_preserves_already_frozen_spec` |
| Validated upstream after worker loss | `test_original_worker_loss_reuses_validated_design_and_requires_grant`; `test_damaged_interrupted_design_fails_closed` |
| Remaining time and explicit grants | `test_continuation_spends_prior_time_and_records_only_current_duration`; `test_recovery_never_silently_extends_budget`; repeated grants checked cumulatively |
| Feedback cannot change acceptance | `test_incompatible_feedback_requires_new_run`; terminal NEEDS_RESCOPING with unchanged frozen spec |
| Mandatory TEST failure prevents REVIEW | `test_rework_mandatory_failure_still_blocks_review` |
| Serialized and explicit delivery | `test_service_serial_rework_and_idempotent_old_delivery`; `test_interrupted_claim_requires_explicit_recovery_delivery`; active directory-lock rejection |
| Default background and explicit foreground CLI | `tests/cli/test_continuation_commands.py`, including submission through ControlService and real-Git application of latest verified candidate |
| Latest history without false verification | Current-Attempt projection tests; broken history and dangling-link regressions report unavailable instead of falling back |

## Audit findings resolved

The audit reproduced two defects before fixing them: an interrupted rework could
drop the frozen specification, and a dangling Attempt-history link could expose an
older VERIFIED snapshot. Recovery now validates and retains the inherited spec,
and history selection rejects malformed links before checking absence. A complete
DESIGN manifest can also be checked independently after original worker loss,
including frozen request/profile/guidance and artifact ownership/digests.

Preflight tests also caught lock files changing capture/root layouts during
implementation. The final implementation locks the original directory inode,
without adding persistent lock artifacts. Latest Run views discard old delivery
observations. Continuation reports identify prior spending and explicit cumulative
time grants, and application checks the exact current Attempt ref.

## Validation

Final required checks passed:

- `uv run pytest`: **926 passed** (87.84 seconds).
- `uv run ruff check .`: passed.
- `uv run pyright`: 0 errors, 0 warnings.

The validation commands used a temporary uv cache; full tests ran with local
socket/subprocess access. No dependencies changed.

Focused regression tests were run red before the corresponding behavior was added
or corrected. Full validation passed at each implementation slice (906, 908, 912
and 916 tests respectively), followed by the final acceptance set. Both command
help entry points were checked and `git diff --check` passed.

## Operational limits

- Execution remains trusted, local and synchronous inside one serial background
  service. Persistence is filesystem-based; locks and journals do not provide a
  multi-file/power-loss transaction or automatic repair.
- Worker loss needs explicit recovery and an additional-time grant. Unknown
  previous spending consumes the whole previous allowance. Partial checkout work
  is discarded; un-packaged candidate code does not become trusted upstream.
- Corrupt journals, incomplete admissions, missing Attempt identity and invalid
  upstream evidence fail closed. They are retained for inspection/new intake,
  rather than repaired or retried automatically.
- Rework is limited to TEST_FAILED/CHANGES_REQUIRED. VERIFIED, cancelled,
  clarification/rescoping and non-allowlisted failures require a new Run. Published
  PR feedback integration is deferred to Phase 12.
- Tests use synthetic NativeAgent responses with real Git, filesystem, subprocess
  checks and local control-service paths. No new live-provider quality evaluation
  or GitHub publication is claimed.
