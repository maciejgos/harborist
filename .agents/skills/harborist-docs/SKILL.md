---
name: harborist-docs
description: Write and maintain Harborist's user-facing documentation for implemented features and behavior changes, or review existing Harborist docs for stale claims, missing instructions, and incorrect examples.
---

# Harborist documentation

Work from the repository root. Read `AGENTS.md` and inspect the existing
guides before deciding what to change.

## Document an implementation

1. Inspect the feature diff, CLI or browser entry points, tests, and relevant
   configuration or deployment scripts. Use the spec to understand intent
   and the implementation to confirm what ships. Check defaults, supported
   environments, prerequisites, failure behavior, and older configurations
   where they affect the reader's task.
2. Search for affected commands, settings, paths, labels, and concepts across
   `README.md`, `COMMANDS.md`, `docs/`, and the website. Update affected
   user journeys, including migration and troubleshooting when relevant.
   For internal-only work, review documentation impact and record why a
   public update is unnecessary.
3. Extend the guide readers already use. Add a page when it serves a distinct
   task or reference need. For a new public page, update `docs/README.md`, the
   source list in `website/scripts/prepare-docs.mjs`, and the sidebar in
   `website/astro.config.mjs`. Edit the canonical Markdown. Preserve existing
   routes and anchors or update the links that point to them.

## Review existing docs

Trace the requested workflow from prerequisites to expected results and
failure recovery. For a general review, start with the overview, quickstart,
deployment guide, and CLI reference. Compare claims with the current code and
tests. Prioritize instructions that fail, imply unsupported capabilities, or
send readers to the wrong environment. Check for missing prerequisites,
conflicting defaults, incorrect labels and paths, and broken links.

For a findings-only review, report the document location, reader impact,
implementation evidence, and needed correction. For an update request, fix
confirmed gaps in scope and report open questions or unverified claims.

## Write for the reader

- Use task-based headings and concise prose. Quickstarts give prerequisites,
  copyable commands in order, and expected results. Operating guides cover
  common failures and recovery. References list syntax, defaults, constraints,
  and errors.
- Use Harborist's published guides as the local style reference. Borrow the
  prerequisite-first approach from OpenAI and Anthropic quickstarts and the
  separation of tutorials from lookup material from HashiCorp. Keep internal
  phase numbers and milestone history in engineering records.
- Label where commands run and what placeholders to replace. Distinguish
  Mac-host commands from `./deploy/harborist exec` and worker paths. The worker
  and web workspace run in containers. Fresh host VMs apply when the Workspace
  uses Docker Sandboxes. Describe native and trusted-local execution where
  relevant.
- Keep queue acceptance, terminal Run outcome, exact-SHA verification,
  application, and GitHub publication distinct. Follow the repository's
  changelog rule.

## Verify the result

Run safe examples in a disposable checkout or data directory where practical.
Check command syntax against help or source, expected outcomes against tests,
and UI tasks against the running workspace when available. For public docs,
run `npm --prefix website run build`, inspect the affected pages, and check
navigation, links, and anchors under the deployment base path. Follow
`AGENTS.md` for repository validation.

Report what passed, what has historical evidence, and what could not be run.
A successful site build verifies rendering. Confirm documented behavior
separately. Keep deployment changes, paid model calls, and publication within
the user's authorization.
