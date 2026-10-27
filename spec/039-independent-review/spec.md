# Specification: Independent REVIEW and semantic decision

- AC-001: Before REVIEW, validate the supplied TEST capture against frozen Run configuration, Attempt, Candidate, ordered check IDs/commands and successful receipt. Reject missing, contradictory or foreign evidence before invoking the agent.
- AC-002: Validate exact spec criterion coverage after independent read-only REVIEW. Persist review.md and a machine-readable decision, spec reference, TEST evidence digest and revision-bound verification record in the create-only stage capture.
- AC-003: All required criteria PASS plus all mandatory checks passing yields VERIFIED; FAIL or UNVERIFIED yields CHANGES_REQUIRED. Failed trusted TEST yields TEST_FAILED and cannot invoke REVIEW. Invalid coverage is INVALID_STAGE_OUTPUT, without a success manifest.
- AC-004: Guidance teaches explicit AC-NNN declarations and complete structured assessments. Preserve spec bytes and exact-candidate workspace guards.
