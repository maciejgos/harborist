---
name: harborist-release-notes
description: Draft, create, or update GitHub release descriptions for maciejgos/harborist using the project’s standard format.
---

# Harborist release notes

Use the [v0.3.0 release](https://github.com/maciejgos/harborist/releases/tag/v0.3.0) as the format reference. Write the description in this order:

1. Open with one short paragraph naming Harborist and the release tag and explaining the most important user-visible change.
2. Under `## Highlights`, use a short bullet list of concrete changes and what users can do with them. Use Harborist terminology such as Run, Attempt, and Workspace where appropriate. Skip generated pull request and contributor lists.
3. Under `## Install`, link to the quickstart at the release tag and show the checkout commands below, replacing `TAG` with the release tag. Follow with a brief paragraph from that tag's quickstart covering Docker requirements and the uv and Codex CLI option when available.
4. End with a link to the comparison from the previous release tag to the new tag. If there is no previous release, link to the relevant changelog entry at the release tag when one exists.

```bash
git clone --branch TAG https://github.com/maciejgos/harborist.git
cd harborist
```

Check the release tags and compare their revisions before drafting. Use the target tag's source and documentation to verify highlights, prerequisites, and links. If tags diverge, inspect the actual target tree and changes before describing what's new. Use the released tag in all documentation links so later changes on the default branch cannot alter the instructions.

For a draft request, return the Markdown. When asked to fix a published description, update the notes field only and read the release back to verify the result. A GitHub release tag and the package version can differ. Use the release tag in the notes and follow the repository's versioning rules for any changelog changes.
