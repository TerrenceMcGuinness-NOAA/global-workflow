# `.vscode/` — MCP tunnel and VS Code MCP server setup

This folder wires VS Code up to the shared EIB MCP gateway that runs on the
`oca-rocky9-mcp-v2` Parallel Works (PW) session under project `ca-infa-mdc`.
There is exactly **one** MCP gateway; every user reaches the same backend, so
multiple collaborators can use it concurrently without redundancy or name
clashes on the server side. Only the per-user client plumbing (PW auth, local
port, tunnel process) differs.

## Files

| File | Purpose |
|---|---|
| [mcp.json](mcp.json) | VS Code MCP server registry. Ships two working entries: `eib-mcp-gateway-ms-devtunnel` (public MS Dev Tunnel URL, no PW account required) and `eib-mcp-gateway-local` (points at `http://localhost:18888/mcp`, requires the PW tunnel below). |
| [start_mcp_tunnel.sh](start_mcp_tunnel.sh) | Opens a `pw sessions connect` SSH port-forward from your host to the MCP gateway on the session VM. Multi-user safe: `SESSION`, `PORT`, `PW`, `PW_API_KEY_FILE`, `LOGFILE` are all env-overridable. |
| `pw_api_key.txt` (git-ignored) | Optional. Terry's local PW API key for non-interactive `pw` use. Collaborators typically don't need this. |
| `pw_api_key_30d.txt`, `pw_api_token_24h.txt` | Local-only tokens for REST calls (`pw api GET /api/sessions`, etc.). Not used by VS Code. |
| [pw_tunnel_investigation.md](pw_tunnel_investigation.md), [pw_admin_mcp_request.md](pw_admin_mcp_request.md) | Historical notes on why the PW `/sessions/<user>/…/mcp` reverse-proxy path does **not** work with bearer tokens (browser OAuth cookies only). |

## Two ways to connect from VS Code

### Path A — MS Dev Tunnel (works from anywhere, no PW account needed)

Use the `eib-mcp-gateway-ms-devtunnel` entry in [mcp.json](mcp.json) as-is:

```jsonc
"eib-mcp-gateway-ms-devtunnel": {
  "type": "http",
  "url": "https://dktt6wzd-18888.use.devtunnels.ms/mcp",
  "headers": { "Authorization": "Bearer eib-mcp-gateway-token-2025" }
}
```

Nothing to install, no PW auth, no local port. This is the recommended path
for anyone outside project `ca-infa-mdc`, or anyone who just wants the fastest
setup.

### Path B — PW tunnel via `start_mcp_tunnel.sh` (for `ca-infa-mdc` users)

Use this when you're on an on-prem RDHPCS PW cluster that's already fully
workspace-authenticated (`pw auth whoami` works) and you want a direct SSH
port-forward rather than going through the public dev tunnel.

**Owner (Terry) — no changes to your workflow:**

```bash
bash .vscode/start_mcp_tunnel.sh
# uses SESSION=oca-rocky9-mcp-v2, PORT=18888, .vscode/pw_api_key.txt
```

**Collaborator in project `ca-infa-mdc`:**

```bash
# From your own on-prem RDHPCS PW cluster (pw already authenticated):
SESSION=Terry.McGuinness/oca-rocky9-mcp-v2 \
  bash /path/to/global-workflow_forked/.vscode/start_mcp_tunnel.sh
```

Then use the `eib-mcp-gateway-local` entry in your VS Code [mcp.json](mcp.json).

If port `18888` is already taken on your login node:

```bash
SESSION=Terry.McGuinness/oca-rocky9-mcp-v2 \
PORT=18899 \
  bash .../.vscode/start_mcp_tunnel.sh
```

…and change the `url` in your VS Code MCP entry to `http://localhost:18899/mcp`.

## Environment overrides accepted by `start_mcp_tunnel.sh`

| Variable | Default | Purpose |
|---|---|---|
| `SESSION` | `oca-rocky9-mcp-v2` | Bare session name (only resolvable if you own it) OR owner-qualified name like `Terry.McGuinness/oca-rocky9-mcp-v2` for collaborators. |
| `PORT` | `18888` | Local TCP port to bind. Change if there is a collision on your host. Remember to match the `url` in [mcp.json](mcp.json). |
| `PW` | `$HOME/pw/pw` | Path to the `pw` CLI. |
| `PW_API_KEY_FILE` | `.vscode/pw_api_key.txt` | Optional. If your `pw` CLI is already authenticated interactively, leave unset and don't create the file. |
| `LOGFILE` | `/tmp/pw_session_connect_${USER}_${PORT}.log` | Per-user, per-port log. Safe on shared login nodes. |

## Ownership and access model (important)

- The MCP session VM (`oca-rocky9-mcp-v2`) is owned by `Terry.McGuinness`
  under project `ca-infa-mdc`. The MCP gateway on it listens on port `18888`.
- PW **tunnel sessions are per-user objects**. `pw sessions ls` only shows
  sessions you own, so as a collaborator you will **not** see
  `oca-rocky9-mcp-v2` in your list. That is expected — the script no longer
  hard-fails on this; it warns and lets `pw sessions connect` render the
  authoritative authorization result.
- Two ways a collaborator gets authorized to connect:
  1. **Session sharing** — Terry shares the tunnel session with the
     collaborator's PW user in the PW UI. Then
     `SESSION=Terry.McGuinness/oca-rocky9-mcp-v2` works directly.
  2. **Own tunnel to the same cluster** — the collaborator creates their own
     tunnel session against the same MCP cluster host and passes its bare
     name: `SESSION=<their-tunnel-name>`. Both tunnels terminate at the same
     `:18888` gateway on the cluster; that's HTTP fan-in, not a conflict.
- Users **outside** project `ca-infa-mdc` cannot use Path B at all — `pw`
  cannot cross accounts. Use Path A (MS Dev Tunnel) instead.

## What does NOT work (documented so no one re-tries it)

The PW reverse-proxy URL `https://noaa.parallel.works/sessions/<user>/oca-rocky9-mcp/mcp`
looks tempting but only accepts browser OAuth cookies set during interactive
web login. It rejects:

- 30-day PW user API keys (as `Authorization: Bearer …` or `?apikey=…`)
- 24-hour PW JWT tokens
- `X-Api-Key` headers

Those tokens **are** still useful for REST calls via
`~/pw/pw api GET /api/sessions`, just not for VS Code's MCP HTTP client.
Details in [pw_tunnel_investigation.md](pw_tunnel_investigation.md).

## Troubleshooting

- **`pw auth whoami` fails** → your PW CLI isn't authenticated. Either run
  `pw auth` interactively or point `PW_API_KEY_FILE` at a file containing a
  valid API key.
- **Listener comes up on `:PORT` but MCP probe fails** → the script tails
  the log and prints a diagnosis. Most common cause: the PW session VM was
  restarted and got a new IP; stop and re-create the session, then re-run.
- **`pw sessions connect` returns "not authorized"** → you don't own the
  session and it hasn't been shared with you. Ask the owner to share it in
  the PW UI, or create your own tunnel session against the same cluster.
- **Port 18888 already in use** → run with `PORT=18899` (or any free port)
  and update the `url` in your VS Code [mcp.json](mcp.json) entry to match.
