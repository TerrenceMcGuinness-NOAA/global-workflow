# PW Tunnel Session Proxy — Investigation Notes

**Date:** 2026-08-20  
**Session:** Gaea C6 VS Code (`vscode_valid_octopus`, target: `Terry.McGuinness/gaeac6`)  
**MCP Service:** port 18888 on `terrymcguinness-emcmcpawsrocky9copyfour-00009-mgmt.pw-noaa-us-east-1.pw.local`

---

## Tunnel Session Under Test

| Field        | Value |
|--------------|-------|
| Name         | `omd-oca-mcp` |
| Type         | tunnel |
| Status       | running |
| External URL | `/me/session/Terry.McGuinness/omd-oca-mcp/mcp` |
| Internal URL | `/sessions/Terry.McGuinness/omd-oca-mcp` |
| Slug         | `mcp` |
| Protocol     | HTTP |
| Remote host  | localhost |
| Remote port  | 18888 |
| Target       | `Terry.McGuinness/emcmcpawsrocky9copyfour` (AWS) |

---

## What Was Tested

### 1. Internal URL with `Authorization: Bearer` header

```
GET https://noaa.parallel.works/sessions/Terry.McGuinness/omd-oca-mcp/mcp
Authorization: Bearer eib-mcp-gateway-token-2025
```

**Response:** `HTTP/2 200` — body is the PW React SPA (`text/html`)  
**Expected:** MCP server response from the proxied service

### 2. Internal URL with `X-Api-Key` header (PW API token)

```
GET https://noaa.parallel.works/sessions/Terry.McGuinness/omd-oca-mcp/mcp
X-Api-Key: <pw-api-token>
```

**Response:** `HTTP/2 200` — body is the PW React SPA  

### 3. External URL with `X-Api-Key` header

```
GET https://noaa.parallel.works/me/session/Terry.McGuinness/omd-oca-mcp/mcp
X-Api-Key: <pw-api-token>
```

**Response:** `HTTP/2 307` → redirect to `/` (login page)

### 4. Both headers combined

```
GET https://noaa.parallel.works/sessions/Terry.McGuinness/omd-oca-mcp/mcp
X-Api-Key: <pw-api-token>
Authorization: Bearer eib-mcp-gateway-token-2025
```

**Response:** `HTTP/2 200` — body is the PW React SPA

---

## Root Cause

The NOAA `noaa.parallel.works` PW instance has the **public session proxy view disabled**.

The PW platform serves its React SPA at all `/sessions/...` and `/me/session/...` paths for
programmatic (non-browser) clients. The actual reverse proxy to the tunnel target only activates
when the request carries a valid **browser cookie session** — i.e., the user is logged into
`noaa.parallel.works` in a browser.

VS Code's MCP HTTP client makes raw HTTP requests with no browser cookie, so every request
receives the SPA HTML (`200 OK`, `content-type: text/html`) rather than being forwarded to
port 18888 on the AWS cluster.

This was confirmed by observing that the URL **does** work when opened in a browser while
logged into `noaa.parallel.works` (the `SUCCESS!` response), but fails immediately when
called programmatically with the same URL and any combination of API tokens.

**This is a NOAA PW instance policy, not a URL format or authentication problem.**  
The tunnel session itself (`omd-oca-mcp`) is correctly configured and running.

---

## Earlier Failed Attempts (Same Root Cause)

| Session name         | Notes |
|----------------------|-------|
| `tunnel_sensible_pony` | Original attempt in mcp.json — same SPA response |
| `tunnel_distinct_martin` | Plain tunnel, no slug — same SPA response |
| `omd-oca-pw_pf`      | Launched with "OpenAI-compatible API" checked — PW registered it as a chat AI provider instead of a proxy; `externalHref` pointed to `/chat?session=...` |
| `omd-oca-mcp`        | Correct configuration (no OpenAI flag, slug=mcp) — proxy works in browser only |

---

## Working Alternatives from Gaea C6 VS Code

| Method | URL | Notes |
|--------|-----|-------|
| MS Dev Tunnel | `https://dktt6wzd-18888.use.devtunnels.ms/mcp` | Works anywhere, browser-managed |
| `pw forward` SSH tunnel | `http://localhost:18888/mcp` | Run `.vscode/start_mcp_tunnel.sh` first |

---

## Why Browser-Based VS Code Still Can't Use the Session Proxy

This VS Code session is served via PW's browser-based VS Code web service (auth method:
**Proxy Certificate Server**), so the user's browser IS authenticated to `noaa.parallel.works`.
This explains why opening the session URL in the browser works.

However, VS Code's MCP extension makes HTTP requests from the **VS Code extension host process**,
which runs as a server-side process on **gaea66 (172.25.62.55)**. It does not go through the
browser. The execution layers are:

| Layer | Runs on | Has PW cookie? |
|-------|---------|----------------|
| Browser (UI) | User's local machine | ✅ yes |
| VS Code UI | Served via browser by PW | ✅ yes |
| VS Code MCP extension host | gaea66 (172.25.62.55) — server process | ❌ no |
| Terminal / curl | gaea66 (172.25.62.55) | ❌ no |

The PW platform proxy daemon (which makes `http://sessions/` resolve) is recorded in
`~/.pw/platform_proxy.json` as running on **172.25.62.53:45429** — a different host.
TCP connection from gaea66 to that port returns `Connection refused (errno 111)`.

So even in a browser-based VS Code session, the MCP HTTP client cannot use PW session proxy
URLs because those requests originate from the gaea66 server process, not the browser.

---

## Potential Future Fix

If NOAA enables the PW session proxy for programmatic access (API key auth on `/sessions/`
paths), the correct mcp.json entry would be:

```jsonc
"eib-mcp-gateway-pw": {
    "type": "http",
    "url": "https://noaa.parallel.works/sessions/Terry.McGuinness/omd-oca-mcp/mcp",
    "headers": {
        "Authorization": "Bearer eib-mcp-gateway-token-2025"
    }
}
```

This would require no tunnel or local port forward — the PW tunnel session handles the
routing from `noaa.parallel.works` → AWS cluster port 18888 automatically.
