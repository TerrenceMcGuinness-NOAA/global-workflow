# PW Admin Request: MCP Service Access from Gaea C6 VS Code

**Date:** 2026-08-20  
**Prepared by:** Terry McGuinness  
**Session:** Gaea C6 VS Code web service (`vscode_valid_octopus`)

---

## How the PW Agent Tunnel Architecture Applies to This Use Case

### What Gaea C6 Is in PW Terms

Gaea C6 is configured as an **"Existing Cluster"** (per-user, externally-managed auth via
**Proxy Certificate Server** / DoD PKI). The PW agent on Gaea maintains a **persistent outbound
WebSocket tunnel to `noaa.parallel.works:443`** — already working (that is how this VS Code
session exists).

### The Gap

The PW agent tunnel enables the **control plane to reach back into Gaea C6**. But the reverse —
reaching the AWS cluster (`emcmcpawsrocky9copyfour`) **from** Gaea C6 — requires either:

1. The `pw forward` SSH tunnel (current workaround), or
2. The PW platform **brokering** a cross-cluster connection through its control plane

### The Admin Ask

The PW platform already has bi-directional tunnel visibility into **both** clusters (Gaea C6 and
the AWS Rocky9 cluster). What is needed is for NOAA/PW admins to enable one of the following:

| Option | What It Requires | Result |
|--------|-----------------|--------|
| **Enable session proxy API auth** | Allow `X-Api-Key` header to authenticate `/sessions/` proxy paths (not just browser cookies) | `https://noaa.parallel.works/sessions/Terry.McGuinness/omd-oca-mcp/mcp` works directly in mcp.json — no tunnel process needed |
| **Enable cross-cluster agent routing** | Expose a routable internal URL between existing clusters via the agent tunnel mesh | `http://sessions/...` resolves from Gaea C6's VS Code extension host |
| **Expose port forwarding via API** | Allow `pw forward` equivalent via a persistent platform-managed tunnel URL | Stable HTTPS URL usable without a running background process |

---

## Message to Admins

We are using VS Code served via PW's browser-based service on **Gaea C6** (Existing Cluster,
Proxy Certificate Server auth). We want to reach an HTTP service (MCP server) on port 18888 of
a **separate AWS cluster** (`emcmcpawsrocky9copyfour`) from within VS Code's extension host
process on Gaea C6.

The PW tunnel session (`omd-oca-mcp`, type=tunnel, slug=mcp) correctly proxies port 18888 and
works when accessed from a browser with a `noaa.parallel.works` session cookie. However, VS
Code's MCP extension host makes direct HTTP requests with no browser cookie, so it receives the
PW SPA instead of the proxied service.

**Request:** Can the session proxy for tunnel-type sessions be made accessible via `X-Api-Key`
header authentication (bypassing the browser cookie requirement), or can the
`http://sessions/<user>/<name>` internal hostname be made resolvable from VS Code extension host
processes running on on-prem Existing Clusters?

Per the agent connectivity docs, both clusters already have live outbound WebSocket tunnels to
the control plane on port 443 — the infrastructure is in place, we just need the proxy
authentication policy adjusted.

---

## Supporting Technical Details

### Tunnel Session Configuration (Already Running)

| Field | Value |
|-------|-------|
| Session name | `omd-oca-mcp` |
| Type | tunnel |
| Status | running |
| Internal URL | `/sessions/Terry.McGuinness/omd-oca-mcp` |
| External URL | `/me/session/Terry.McGuinness/omd-oca-mcp/mcp` |
| Slug | `mcp` |
| Remote host | localhost |
| Remote port | 18888 |
| Target cluster | `Terry.McGuinness/emcmcpawsrocky9copyfour` (AWS) |

### What Was Tested and Why It Fails

| Method | Result | Root Cause |
|--------|--------|------------|
| `https://noaa.parallel.works/sessions/.../mcp` with `X-Api-Key` | 200 — PW SPA HTML | Session proxy requires browser cookie, not API key |
| `https://noaa.parallel.works/me/session/.../mcp` with `X-Api-Key` | 307 → login SPA | Same — browser cookie required |
| `http://sessions/Terry.McGuinness/omd-oca-mcp/mcp` | DNS resolution failure | `sessions` hostname only resolves inside native PW nodes; not available on on-prem existing clusters |
| Platform proxy at `172.25.62.53:45429` | Connection refused | Proxy daemon runs on a different host in the same subnet; not cross-host accessible |
| `pw forward -L 18888:localhost:18888 emcmcpawsrocky9copyfour` | ✅ **Works** | SSH tunnel through PW agent; requires background process per session |

### Why the Browser Works but VS Code Does Not

VS Code is served via PW's browser-based web service. The VS Code **UI** runs in the browser
and has the `noaa.parallel.works` session cookie. However, the VS Code **MCP extension host**
runs as a server-side Node.js process on gaea66 (`172.25.62.55`) with `--useHostProxy=false`.
It makes direct HTTP requests with no browser cookie and no HTTP proxy configured, so it cannot
authenticate to the PW session proxy.

### Current Workaround

```bash
# Run at the start of each Gaea C6 VS Code session:
.vscode/start_mcp_tunnel.sh

# Or manually:
nohup pw forward -L 18888:localhost:18888 emcmcpawsrocky9copyfour &
```

Then connect the `eib-mcp-gateway-local` MCP server in VS Code (`http://localhost:18888/mcp`).
This works but requires a running background process and must be restarted each session.

### PW Agent Connectivity Reference

From `https://parallelworks.com/docs/self-hosting/ports#agent-connectivity`:

> Once access is routed entirely through an agent tunnel, the cluster needs only an **egress rule
> allowing HTTPS traffic to the platform hostname on TCP port 443**; **no public inbound rule or
> port forwarding is required**. The control plane can open new streams on the agent's existing
> WebSocket connection to reach the agent — effectively a reverse tunnel — without the agent
> needing any inbound ports.

Both Gaea C6 and the AWS Rocky9 cluster already satisfy this requirement. The agent tunnels are
live. The remaining gap is purely a **platform policy decision** on how session proxy
authentication is handled for programmatic (non-browser) clients.
