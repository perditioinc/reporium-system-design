# 16 - MCP HTTP Bridge and Workato Authentication Model

One decision about how the Reporium MCP tool suite is exposed to external orchestrators — in particular Workato — when those orchestrators cannot speak the stdio MCP transport directly.

---

## Decision 16: MCP HTTP Bridge with Per-Caller Token Auth

**Context.** The Reporium MCP server (`reporium-mcp`) exposes 18 tools over the Model Context Protocol. The native MCP transport is stdio: a client launches the server as a subprocess, pipes JSON-RPC frames over stdin/stdout, and terminates the process when done. This works well for desktop clients (Claude Desktop, Cursor, VS Code extensions) that run locally and trust the user's environment.

Workato is not such a client. Workato recipes execute in Workato's cloud, cannot fork subprocesses into the Reporium network, and have no way to hold a long-lived stdio pipe open against a remote process. The Workato connector SDK speaks HTTP with configurable auth — nothing else. To unlock the entire Workato integration surface (recipes that call `ask_portfolio`, `get_portfolio_gaps`, `search_repos_semantic`, the cross-dimension analytics, etc.), we need the same 18 tools reachable over HTTPS.

A secondary consideration: the same HTTP surface is useful for any non-MCP caller — a n8n flow, a GitHub Action, an internal Cron script, a legacy RPA bot. If we are going to build it for Workato we should build it once, correctly, and let any HTTP-speaking client use it.

**What we tried first.** One option was to embed Workato-specific logic in the MCP server itself — a second authentication scheme, a second set of endpoints. This would have meant the MCP server grew a FastAPI app alongside its stdio handler, coupling protocol transport to auth model. Changes to either would risk breaking the other. It would also have forced the Workato connector to understand MCP framing, which the connector SDK is not designed for.

A second option was to let Workato call `reporium-api` directly, skipping MCP entirely. This would have worked for simple read endpoints but bypassed the higher-level tool composition that lives in `reporium-mcp/tools/*.py` — tool functions that join multiple API calls, post-process responses, and present domain-shaped outputs. The value of the MCP tool layer is exactly that composition; forcing Workato to reassemble it inside recipes would duplicate logic and keep diverging from MCP callers over time.

**Decision.** Build a dedicated HTTP bridge as a separate deployable — `reporium-mcp-http` — that re-exposes every MCP tool as a REST endpoint, sharing the tool implementations from the stdio server.

The bridge is a FastAPI app (`reporium-mcp/http_server.py`). It imports the same tool functions that the stdio server uses (`from tools.search import search_repos`, etc.) and wraps each one in a thin HTTP handler. Stdio transport (`mcp_server.py`) and HTTP transport (`http_server.py`) are two entrypoints over one shared tool implementation — no code duplication at the tool level, and no risk of the two surfaces drifting in behavior.

Deployment is Cloud Run, public ingress, token-gated. The production URL is `https://reporium-mcp-http-wypbzj5gpa-uc.a.run.app`. A separate `Dockerfile.http` builds the HTTP variant; the stdio server ships unchanged.

**Auth model.** Two layers of token, never conflated.

The outer layer is `X-MCP-Token`: a single pre-shared bearer token that every incoming HTTP request must present. The bridge rejects any request to a non-health endpoint without a matching `MCP_API_TOKEN` env var value. This token is the bridge's front door — it authenticates the caller (Workato, or any other HTTP client) to the bridge itself.

The inner layer is `X-App-Token`: the token the bridge uses when calling `reporium-api`. This is the same `REPORIUM_APP_TOKEN` used by every server-to-server caller in the platform. The bridge injects it into every upstream request via `httpx.AsyncClient(headers={"X-App-Token": REPORIUM_APP_TOKEN})`. HTTP callers never see or provide this token — it stays on the bridge.

This separation matters. If we had routed Workato straight to `reporium-api`, we would have had to hand Workato the platform-wide `X-App-Token` — a token that also gates ingestion, admin endpoints, and internal batch jobs. Any compromise of the Workato vault would have exposed the platform's core API auth. With the two-layer model, compromising `X-MCP-Token` gives an attacker exactly the 18 read-shaped tool endpoints that the bridge exposes, at the bridge's rate limit. Blast radius is bounded to the tool surface.

Workato stores `X-MCP-Token` in its own vault, configured on the connection object, never logged. The Ruby connector (`perditio-workato-integration/connector/reporium_mcp_connector.rb`) declares the token as `control_type: 'password'` and injects it via `custom_auth` — the standard Workato pattern for credential-bearing connectors.

**Rate limiting.** The bridge applies slowapi per-IP limits inline: 60 requests/minute for every tool except `/ask`, which is 30/minute. These limits are generous for interactive Workato recipes but tight enough to contain runaway loops or misconfigured retries. The limits are independent of `reporium-api`'s own rate limits — the bridge acts as a second layer, and either layer can reject a request. If Workato blows past 60/min, the bridge returns 429 before any load reaches `reporium-api`.

**Secret rotation.** Both tokens (`X-MCP-Token` and `X-App-Token`) live in Google Secret Manager, mounted as env vars on the Cloud Run revision. Rotation is a secret-version update followed by a no-op redeploy. A documented gotcha from the April 15 incident: `gcloud secrets versions add` reads from stdin via shell heredoc or `echo` and pipes a trailing `\r\r\n` into the secret value, which then fails constant-time comparison in the auth middleware. The correct form is `printf '%s' "$VALUE" | gcloud secrets versions add ...`. This is documented in the deployment runbook.

**Tradeoff.** Running two entrypoints against one tool layer means the tool functions must be safe to call from both contexts — no stdio-specific assumptions, no globals that survive a stdio session, no logging that assumes a TTY. This was already true by construction (the tools are pure async functions that take an `httpx.AsyncClient`), but the constraint now has a name and must be respected by future tool authors. A "stdio-only" tool would silently break Workato; CI enforces this via the shared import test in `tests/test_http_tools_importable.py`.

The alternative — one deployable, two transports in one process — would have avoided the separate Cloud Run service but entangled stdio process lifecycle with HTTP request handling. Cloud Run cost of the second service is negligible (scales to zero, roughly $0/mo at current traffic). The cost of conflated transports would have been paid every time either side needed to change.

---

## Status

Deployed 2026-04-15. Production URL: `https://reporium-mcp-http-wypbzj5gpa-uc.a.run.app`. Workato connector ready at `perditio-workato-integration/connector/reporium_mcp_connector.rb`. Workato connection activation tracked in reporium-api issue #349.

## Related Decisions

- Decision 12 (`12-ingest-runs-provenance.md`) — the platform's broader stance on token-based inter-service auth.
- Decision 15 (`15-phase-2-3-followups.md`) — the observability gates that the HTTP bridge inherits (alert policies for 5xx >1% and p95 >2000ms are active).
