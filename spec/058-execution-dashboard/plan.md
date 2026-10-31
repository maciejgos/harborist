# Plan

Add a buildless HTML/CSS/JavaScript adapter served by a small loopback-only Python HTTP server. It proxies allowlisted GETs to the existing Unix-socket ControlClient; execution and queue ownership stay in ControlService. Keep frontend assets packaged under shipyard/web, independent of control-plane orchestration. Add validated title/candidate fields to the read model and persist per-stage observational updates in queue snapshots. Add allowlisted bounded report/evidence reads to the canonical service API. The dashboard polls without overlapping requests and treats missing history as unknown rather than successful. Test backend boundaries first, then real-service browser behavior and the full repository suite.

Visual direction: white surfaces, dark system typography, teal selected/active state, a compact Run-history rail, an open detail pane and seven-step stage timeline. No client-side execution authority or separate persistence.
