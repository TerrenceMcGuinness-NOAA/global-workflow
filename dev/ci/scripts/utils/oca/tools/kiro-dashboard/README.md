# Kiro IDE Usage Dashboard

A standalone Python CLI that turns raw AWS Kiro IDE telemetry (deposited in the
`mdc-mcp-rag-migration` S3 bucket) into a single self-contained HTML dashboard
with interactive Plotly charts. It follows a strict **Sync → Parse → Render**
pipeline and requires no web server, database, or CDN — just open the output
HTML in any browser.

## What the dashboard shows

**Executive summary panel**
- Total distinct users, total messages, total credits consumed
- Data date range and number of active days
- 30-day projected credit cost (flagged when based on limited data)
- Organization overage cap and total overage credits used
- Kiro-billed messages per `Client_Type` (`KIRO_IDE`, `KIRO_CLI`)
- BYOK users, BYOK successful calls, BYOK input tokens, BYOK output tokens

**Per-user summary table** (sorted by total credits, capacity color-coded
green/yellow/red)
- Email, subscription tier, client types, days active, conversations, messages,
  credits, capacity utilization %, average credits/message, last active date

**BYOK versus Kiro-billed section** (see [BYOK visibility](#byok-visibility))
- Side-by-side per-user table: Kiro-billed messages and credits next to BYOK
  successful/failed calls, input/output tokens, models, client families, and
  last-seen timestamp
- Failed-call count with a breakdown by CloudTrail `errorCode`

**Thirteen charts**

| Chart | Type | Source |
|-------|------|--------|
| Daily credits by user | stacked area | user reports |
| Daily messages by user | grouped bar | user reports |
| Capacity utilization | horizontal bar (color-coded) | user reports |
| Subscription tier distribution | pie | user reports |
| Cost efficiency (credits/message) | line | user reports |
| Monthly credit projection | bar | user reports (needs >=2 days) |
| Weekend vs weekday usage | grouped bar | user reports (needs both) |
| Hourly activity heatmap | heatmap | event logs |
| Events by model | bar | event logs |
| Kiro-billed messages by model | bar | user reports (per-model columns) |
| BYOK Bedrock calls per day | grouped bar | CloudTrail |
| BYOK tokens per day (input/output) | stacked bar | CloudTrail |
| BYOK successful calls by model | bar | CloudTrail |

Charts that require data not present (e.g. events not synced, only one day of
data, CloudTrail never fetched) are omitted and replaced with an inline notice.

## How to run

Interpreter selection is the launcher's job. Use it and you never have to know
which `python3.x` on the current host carries the libraries:

```bash
# From the repository root. Sync the latest telemetry, render, and open it:
tools/kiro-dashboard/kiro-dashboard.sh --sync --open

# Include BYOK Bedrock usage from CloudTrail:
tools/kiro-dashboard/kiro-dashboard.sh --sync --cloudtrail --open

# Render from whatever is already in the local cache (no AWS access at all):
tools/kiro-dashboard/kiro-dashboard.sh

# Bound both fetches and write to a custom path:
tools/kiro-dashboard/kiro-dashboard.sh --sync --cloudtrail \
    --since 2026-09-04 --output /tmp/kiro.html

# Print the interpreter the launcher resolved, and nothing else:
tools/kiro-dashboard/kiro-dashboard.sh --print-python
```

`cli.py` also remains directly invocable with any Python 3.10+ that has the five
runtime libraries -- `python3.12 tools/kiro-dashboard/cli.py` on the AWS host,
`python3 tools/kiro-dashboard/cli.py` on the Parallel Works host.

The command prints the output HTML path to **stdout**; all diagnostics
(warnings, errors, the `[sync]` and `[cloudtrail]` summary lines) go to
**stderr** or are single stdout summary lines, so it is cron- and
pipeline-friendly.

### Platform matrix

The AWS host and the Parallel Works host are not interchangeable: on AWS
`python3` is 3.9.25 without pandas, and on Parallel Works `python3.12` does not
exist. Neither host's toolchain is referenced from the other's commands. The
launcher probes `python3.12`, then `python3.11`, then `python3` on PATH and
picks the first that reports 3.10+ and imports all five libraries;
`KIRO_DASHBOARD_PYTHON` overrides the probe.

| | AWS_Platform | PW_Platform |
|---|---|---|
| OS / arch | Amazon Linux 2023, aarch64 | RHEL 9, x86_64 (Parallel Works COTS) |
| Interpreter | `python3.12` (`/usr/bin/python3.12`) | `python3` (Spack `python/3.11.14`) |
| Install | `python3.12 -m pip install --user -r tools/kiro-dashboard/requirements-dev.txt` | `python3 -m pip install --user -r tools/kiro-dashboard/requirements-dev.txt` |
| Run | `tools/kiro-dashboard/kiro-dashboard.sh --sync --cloudtrail` | `tools/kiro-dashboard/kiro-dashboard.sh --sync --cloudtrail` |
| Test | `"$(tools/kiro-dashboard/kiro-dashboard.sh --print-python)" -m pytest tests/test_kiro_dashboard/ -q` | `"$(tools/kiro-dashboard/kiro-dashboard.sh --print-python)" -m pytest tests/test_kiro_dashboard/ -q` |
| Verified Python | 3.12.12 (2026-09-16) | 3.11.14 (2026-09-11) |
| Verified packages | boto3 1.42.70, pandas 3.0.1, numpy 2.4.2, plotly 6.6.0, Jinja2 3.1.6 | see the platform's own `pip list`; floors in `requirements.txt` |

A system-wide `pip install` without `--user` is not permitted on either host.
The full policy, including the commit that motivated it, is in
`.kiro/steering/15-platform-python-policy.md`.

### CLI flags

| Flag | Description |
|------|-------------|
| `--sync` | Download the latest telemetry from S3 before rendering (three prefixes: user reports, event logs, by_user_analytic). |
| `--cloudtrail` | Fetch BYOK Bedrock events from CloudTrail `LookupEvents` into the local cache before rendering. Requires `cloudtrail:LookupEvents`. Without it, no CloudTrail API call is made and the BYOK section renders from whatever is already cached. |
| `--since YYYY-MM-DD` | Restrict `--sync` **and** `--cloudtrail` to data on or after this date. The CloudTrail window is clamped to the 90-day retention limit with a warning. No effect when neither `--sync` nor `--cloudtrail` is given (a warning is logged). |
| `--output PATH` | HTML output path. Default: `tools/kiro-dashboard/output/dashboard.html`. |
| `--open` | Open the rendered HTML in the default browser. A failure to open is logged but does not fail the run. |
| `--print-python` | Launcher only, as the sole argument: print the resolved interpreter path and exit 0. |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success -- dashboard rendered (even if a sync or the CloudTrail fetch was partial or failed, or some files were unparseable). |
| `1` | No data available to render: an empty cache with neither `--sync` nor `--cloudtrail`, or zero user reports **and** zero event logs **and** zero CloudTrail partitions parsed. `by_user_analytic` data alone never counts as data. |
| `2` | Invalid arguments (e.g. a bad `--since` date). |
| `3` | Environment error: the interpreter is older than 3.10, or a runtime library is missing. Produced by the launcher (no eligible interpreter) or by `cli.py`'s dependency preflight. Wins over code 2, because the preflight runs before argument parsing. |

## Data sources

| Source | S3 prefix or AWS API | Cache directory | Cadence | Retention |
|--------|----------------------|-----------------|---------|-----------|
| User_Report | `s3://mdc-mcp-rag-migration/kiro-logs/AWSLogs/903050880929/KiroLogs/user_report/us-east-1/` | `cache/user_reports/` | daily, about 02:01 UTC for the prior day | none known |
| Event_Log | `.../KiroLogs/GenerateAssistantResponse/us-east-1/` | `cache/events/` | near-real-time, hour-partitioned | none known |
| By_User_Analytic | `.../KiroLogs/by_user_analytic/us-east-1/` | `cache/by_user_analytic/` | daily (published since 2026-09-11) | none known |
| CloudTrail Bedrock events | `cloudtrail:LookupEvents`, `EventSource=bedrock.amazonaws.com` | `cache/cloudtrail/{region}/{YYYY}/{MM}/{DD}/` | delivered up to 15 minutes late | **90 days** |

Downloaded files are cached preserving the date-partitioned structure.
Re-running `--sync` is idempotent: files already in the cache are skipped, never
re-downloaded. Re-running `--cloudtrail` is idempotent too: a UTC day whose end
is more than 15 minutes in the past and which was fetched completely is skipped,
so a daily cron run touches one or two partitions.

### User report columns

`Date, UserId, Client_Type, Chat_Conversations, Credits_Used, Overage_Cap,
Overage_Credits_Used, Overage_Enabled, ProfileId, Subscription_Tier,
Total_Messages, New_User, User_Email, Usage_Limit` plus a growing family of
per-model counters matching `^[a-z0-9_.]+_messages$` (`auto_messages`,
`claude_opus_4.6_messages`, `claude_opus_5_messages`,
`claude_opus_4.8_messages`, ...). Every family member is preserved; any other
unrecognized column is dropped and named in one INFO line per parse, so schema
drift is visible in cron output. Two derived columns are computed,
`capacity_pct` and `credits_per_message`.

Rows are deduplicated on `(Date, User_Email, Client_Type)`. Since 2026-09-10 AWS
publishes a `KIRO_CLI` report alongside the `KIRO_IDE` report for the same day,
so one user-day legitimately has two rows; both are counted.

### Event log records

Each file has a top-level `records` array; each record has a
`generateAssistantResponseEventRequest` (`prompt`, `chatTriggerType`, `userId`,
`timeStamp`, `modelId`) and a `generateAssistantResponseEventResponse`
(`assistantResponse`, `codeReferenceEvents`, `requestId`). `timeStamp`,
`userId`, and `requestId` are required; a null or absent `modelId` is bucketed
under `(unknown)` and the record is kept, so parsed + skipped equals the number
of records in the files.

## BYOK visibility

**BYOK** is bring-your-own-key inference: a direct Amazon Bedrock inference
call made under the user's own IAM credentials rather than through Kiro's
service backend. The key may be used from Kiro in BYOK mode, from VS Code with
a Bedrock-backed extension, or from a script; CloudTrail records the principal
and the client family (`userAgent`, shown as the BYOK client families column),
not the product name, so the issuing tool is inferred rather than proven. It is
billed to the AWS account as Bedrock on-demand usage and consumes zero Kiro
credits.

**Why Kiro telemetry cannot show it.** The `GenerateAssistantResponse` record
carries exactly five request fields (`prompt`, `chatTriggerType`, `userId`,
`timeStamp`, `modelId`) and three response fields (`assistantResponse`,
`codeReferenceEvents`, `requestId`). There is no provider, credential, billing,
or endpoint field, and a BYOK request bypasses Kiro's backend entirely, so it
produces no event-log record and no credit line.

**How CloudTrail discriminates it.** A BYOK request is a Bedrock runtime call in
account `903050880929`, and the IAM principal type separates the two paths
cleanly:

| Path | `eventName` | `userIdentity.type` | Principal |
|------|-------------|---------------------|-----------|
| BYOK | `ConverseStream` (or `Converse`, `InvokeModel`, `InvokeModelWithResponseStream`) | `IAMUser` | `userName` is the user's email, identical to the user report's `User_Email` |
| Not BYOK (always excluded) | `InvokeModel` | `AssumedRole` | `mdc-mcp-rag-ecs-task-role` -- the AgentCore MCP runtime's Titan embeddings |

Token counts come from the paired `AwsServiceEvent` record whose
`serviceEventDetails.parentRequestId` equals the API call's `requestID`.

**The two sources are disjoint and shown side by side, never joined per
request.** A BYOK call and a Kiro message are different units. The dashboard
aggregates each source independently and keys the side-by-side table on the
lower-cased, whitespace-stripped email.

**Required permission:** `cloudtrail:LookupEvents`. That is the only permission
`--cloudtrail` needs.

**Limitations.**
- `LookupEvents` retains 90 days. Anything older is unrecoverable through this
  path; `--since` earlier than that is clamped with a warning.
- Events are delivered up to 15 minutes late, so today's partition is re-fetched
  on every run.
- Bedrock model invocation logging is **not** configured; enabling it would be
  new infrastructure and is out of scope.
- The trail's S3 bucket belongs to the security account and is not readable from
  these hosts, so `LookupEvents` is the only available access path.
- Inference that does not go through Bedrock in account `903050880929` (for
  example a personal Anthropic API key) produces no CloudTrail record and cannot
  be observed by this tool at all.

**Zero infrastructure.** This feature creates no AWS resource, enables no
Bedrock invocation logging, and requires no IAM change beyond the
already-granted `cloudtrail:LookupEvents`.

## Privacy guarantees

Prompt and response **content is never stored or displayed.** The event parser
uses a structural extraction allowlist (`EXTRACTION_ALLOWLIST` in
`event_parser.py`): it reads the `prompt` and `assistantResponse` strings only
to measure their character length, then discards the text. The only fields that
leave the parser are `timestamp`, `userId`, `modelId`, `chatTriggerType`,
`prompt_length`, `response_length`, and `requestId`. Any other field in the
event JSON -- including future additions -- is discarded unless the allowlist is
explicitly updated.

CloudTrail records are reduced the same way, by an allowlist applied *before*
anything reaches disk (`CLOUDTRAIL_ALLOWLIST` in `cloudtrail_sync.py`). The 16
permitted keys are:

`eventID`, `eventTime`, `eventName`, `eventType`, `awsRegion`, `errorCode`,
`requestID`, `userAgent`, `principalType` (from `userIdentity.type`), `userName`
(from `userIdentity.userName`), `modelArn` (the first `resources[].ARN`
containing `:foundation-model/`), `requestedModelId` (from
`requestParameters.modelId` only), `parentRequestId`, `inferenceRegion`,
`inputTokens`, `outputTokens`.

Never written, returned, or logged: `userIdentity.accessKeyId`,
`userIdentity.principalId`, `userIdentity.arn`, `userIdentity.accountId`,
`userIdentity.sessionContext`, `sourceIPAddress`, `errorMessage`,
`responseElements`, any `requestParameters` key other than `modelId`,
`tlsDetails`, `vpcEndpointId`, `recipientAccountId`. There is no flag or
configuration that widens the allowlist; adding a key requires editing the
frozenset in source. A Hypothesis property test synthesizes records containing
arbitrary extra keys plus every denylisted field and asserts that the projected
keys are a subset of the allowlist and that no denylisted value appears in the
serialized cache line.

BYOK data reaches the dashboard **only as aggregates** (per user, per day, per
model, per error code, per client family). No `eventID`, `requestID`, or
`parentRequestId` value is passed into the template context.

Note: the raw `.json.gz` files downloaded by `--sync` do contain prompt/response
text and are written to the local `cache/` directory. The cache is gitignored
and never leaves the machine; only the metadata derived by the parser reaches
the dashboard.

## Modules

```
tools/kiro-dashboard/
|-- kiro-dashboard.sh      # Launcher: resolves an interpreter, execs cli.py
|-- cli.py                 # CLI entry point / orchestrator + dependency preflight
|-- sync.py                # S3 data sync (three prefixes, skip-if-cached)
|-- cloudtrail_sync.py     # CloudTrail LookupEvents fetch -> day-partitioned cache
|-- parser.py              # User report CSV parser -> consolidated DataFrame
|-- event_parser.py        # Event log parser (privacy allowlist enforcement)
|-- analytics_parser.py    # by_user_analytic CSV parser
|-- cloudtrail_parser.py   # Pairs CloudTrail records -> byok_df
|-- render.py              # Executive summary, tables, 13 charts, HTML render
|-- requirements.txt       # Five runtime dependencies (lower bounds only)
|-- requirements-dev.txt   # -r requirements.txt + pytest, hypothesis
|-- templates/
|   `-- dashboard.html.j2  # Jinja2 template with inline Plotly.js
|-- cache/                 # Local AWS cache (gitignored)
`-- output/                # Rendered dashboard (gitignored)
```

## Viewing in Parallel Works

`serve_pw_session.sh` publishes the dashboard as a Parallel Works **endpoint
session**: a normal HTTPS URL in your browser, no VNC desktop involved.

```bash
cd tools/kiro-dashboard
./serve_pw_session.sh --sync --open

# Stable, readable URL instead of a random subdomain:
./serve_pw_session.sh --subdomain kiro-dashboard --open
```

This renders the dashboard, then runs `pw endpoints serve`, which starts its own
static file server and dials out to register a reverse tunnel — so no inbound
network access to this machine is required. Ctrl-C stops serving, but the
session is kept by default so the URL stays live for anyone you shared it with;
pass `--no-keep` to delete it on exit, or `pw endpoints delete kiro-dashboard`
later.

`--name` and `--subdomain` are different things: `--name` is only the session
label in `pw endpoints list`, while `--subdomain` sets the hostname. Without
`--subdomain` you get a random one (e.g. `solid-eel`), so pass it when you want
a URL you can bookmark or share:
`https://kiro-dashboard.noaa-sessions.parallel.works/`

| Flag | Description |
|------|-------------|
| `--sync`, `--cloudtrail`, `--since` | Passed through to `cli.py` before rendering. |
| `--name NAME` | Endpoint session name. Default: `kiro-dashboard`. |
| `--subdomain LABEL` | Request a specific subdomain instead of a random one. |
| `--open` | Open the endpoint URL in a browser. |
| `--public` | Anyone with the link can view it without logging in. **Currently rejected by NOAA org policy** (`Public sessions are not allowed by your organization's policy`), verified 2026-09-11. |
| `--no-keep` | Delete the endpoint session on exit. Default is to keep it, so the URL survives Ctrl-C. |
| `--output text` | Plain log output instead of the live dashboard (for cron/non-TTY). |

The script renders into `output/pw_session/` rather than `output/`, because
`pw endpoints serve` publishes an entire directory — pointing it at the tool
root would also expose `cache/`, which contains raw prompt text.

### Sharing the session

Endpoint URLs require an ACTIVATE login, and login alone is not enough: a new
session is owner-only (`shared: {teams: [], organization: false}`), so other
users get `You do not have access to this session` until it is shared.

Sharing is **per session**, not per subdomain. Every `serve` run mints a new
session id, so re-share after each restart.

Grant a group access (verified working 2026-09-14):

```bash
pw api -X POST -F access=true -F groupId=<GROUP_ID> \
  organizations/noaademo/users/<YOUR_USERNAME>/sessions/kiro-dashboard/access
```

Revoke with `-F access=false`. Both return `204 No Content`. Verify with:

```bash
pw api -q '.[] | select(.name=="kiro-dashboard") | .shared' sessions
```

Group ids come from `pw api -q '.[] | {id, name}' groups`; `pw groups get NAME`
lists members. For this project the group is `ca-infra-mdc`
(`69f3c5564f578d0776757f39`) — Jacob Carley, Rahul Mahajan, Terry McGuinness.

`teams` is additive, so revoking one group leaves the others intact. Omit
`groupId` and pass `-F organization=true` to share with the entire
organization — 565 members, so don't.

The API reference calls this route "system-level", implying admin rights, but it
works for a plain `org:member` on their own session.

There is no `pw` subcommand for this, and the UI path has moved between
releases; the API call above is the stable route. Note that PW treats sharing as
"allow the group to run the workflow as you", so only share with groups you
trust.

`--public` would bypass login entirely, but NOAA org policy currently rejects it.
Since the dashboard shows per-user credit consumption and NOAA email addresses,
group sharing is the appropriate route regardless.

If an endpoint is left registered, `pw endpoints list` and
`pw endpoints delete NAME` clean it up.

## Dependencies

Python >= 3.10. The five runtime packages are declared with lower bounds only in
`requirements.txt`; the test extras (`pytest`, `hypothesis`) are in
`requirements-dev.txt`, which includes `requirements.txt` by reference.

```bash
# Install for the interpreter the launcher resolves on this host.
"$(tools/kiro-dashboard/kiro-dashboard.sh --print-python)" -m pip install \
    --user -r tools/kiro-dashboard/requirements-dev.txt
```

Per-platform install commands are in the [platform matrix](#platform-matrix). A
system-wide `pip install` without `--user` is not permitted.

| Package | Used by |
|---------|---------|
| `boto3` | `sync.py` (S3 list + download), `cloudtrail_sync.py` (LookupEvents) |
| `pandas`, `numpy` | `parser.py`, `event_parser.py`, `analytics_parser.py`, `cloudtrail_parser.py`, `render.py` |
| `plotly` | `render.py` (charts + inline Plotly.js) |
| `Jinja2` | `render.py` (template rendering) |

`argparse`, `gzip`, `json`, `calendar`, and `datetime` are from the standard
library. The Plotly.js library (~4.9 MB) is embedded inline at render time via
`plotly.offline.get_plotlyjs()`, so the output HTML is fully self-contained.

**Why pip and not Spack:** `py-plotly` has no Spack package, and the
`py-pandas/2.3.3-44wibvs` module fails to load because its dependency closure
(`llvm`, `py-tzdata`, `py-numexpr`, `py-python-dateutil`, `py-setuptools`) is not
installed as modules. `pip install --user` is therefore the supported path for
this tool. The shared `/mnt/mdc-mcp-rag/spack/var/mcp-venv` is scoped to
`mcp_server_python/` and is not a candidate for the dashboard libraries.


## Tests

The same command works on both platforms, because the interpreter comes from the
launcher rather than from a hard-coded name:

```bash
"$(tools/kiro-dashboard/kiro-dashboard.sh --print-python)" -m pytest \
    tests/test_kiro_dashboard/ -q
```

The suite runs with **no AWS access**: the S3 and CloudTrail clients are injected
fakes, and `sleep` and the fetch start are injected so the pacing, backoff, and
Closed_Partition arithmetic are deterministic. Every write goes to a pytest
`tmp_path`; the real `tools/kiro-dashboard/cache/` is never touched.

It combines example-based unit tests with eighteen Hypothesis property tests:
the nine from the parent spec (privacy allowlist enforcement, zero-division
safety, path-mapping determinism, dedup idempotency, userId normalization,
executive-summary consistency, capacity classification, schema normalization,
date validation) plus nine added here -- CloudTrail allowlist projection,
`eventID` dedup idempotence, partition merge determinism, model-id normalization
idempotence, the per-model column family regex, `Client_Type`-aware
deduplication, the Closed_Partition predicate, the `MM-DD-YYYY` round trip, and
BYOK executive consistency.
