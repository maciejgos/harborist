# Local GitHub integration

The Integrations screen checks the existing GitHub CLI login on demand.
Selecting a configured Workspace also checks access to its repository.
Show specific next steps for missing CLI, missing login, inaccessible
repositories, and failed checks. Do not expose credentials or CLI output.
When a Workspace has a supported GitHub origin, use it as the suggested
repository unless the operator supplies an explicit value.

Suggest the Workspace repository when publishing a Run if its checkout has
a single configured destination. Existing publication receipts take priority.

Browser verification confirmed that the GitHub origin appeared in Workspace
settings and as a repository option on Integrations. Automated tests cover
CLI status handling without using live credentials.
