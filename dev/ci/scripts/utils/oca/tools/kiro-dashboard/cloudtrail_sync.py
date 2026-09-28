"""CloudTrail fetch of Bedrock inference events into a day-partitioned cache.

Kiro's own telemetry cannot see BYOK inference: the
``GenerateAssistantResponse`` record has no provider, credential, or billing
field, and a BYOK request never transits Kiro's backend. CloudTrail does see
it, because a BYOK request is a Bedrock runtime call made with the user's own
IAM credentials. The discriminator is the principal: ``IAMUser`` is BYOK,
``AssumedRole`` is a service role (the MCP runtime's embeddings) and is never
BYOK.

Privacy contract
----------------
:data:`CLOUDTRAIL_ALLOWLIST` is the ONLY set of keys ever written to disk.
Projection happens before caching, so the raw ``LookupEvents`` response -- which
carries ``accessKeyId``, ``principalId``, ``arn``, ``sessionContext``,
``sourceIPAddress``, ``errorMessage``, ``tlsDetails`` and the full
``requestParameters`` -- is never persisted. There is no flag or configuration
that widens the allowlist; adding a key requires editing this constant.

Access path
-----------
``LookupEvents`` is the only available route: the trail's S3 bucket belongs to
the security account and is not readable from this host, and Bedrock model
invocation logging is not configured (enabling it would be new infrastructure).
The API allows one lookup attribute per call, 50 events per page, and 2 requests
per second, retains 90 days, and delivers events up to 15 minutes late. All of
those limits shape the algorithm below.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import (BotoCoreError, ClientError,
                                 EndpointConnectionError, NoCredentialsError)

logger = logging.getLogger(__name__)


# --- Constants -------------------------------------------------------------

# Per run; 50 events/page -> 50,000 events. A capped run leaves the partitions
# it did not finish marked incomplete so a later run resumes there.
CLOUDTRAIL_MAX_PAGES = 1000
# CloudTrail LookupEvents retention.
LOOKBACK_DAYS = 90
# 2 requests/second quota.
MIN_REQUEST_INTERVAL_S = 0.5
# 5 retries on ThrottlingException.
THROTTLE_BACKOFF_S = (1, 2, 4, 8, 16)
# A UTC day is "closed" this many minutes after it ends (max delivery lag).
DELIVERY_LAG_MIN = 15
# Page size; the API maximum.
LOOKUP_PAGE_SIZE = 50

EVENT_SOURCE = "bedrock.amazonaws.com"
DEFAULT_REGION = "us-east-1"

# Only these event names count as BYOK inference calls.
INFERENCE_EVENT_NAMES = frozenset({
    "Converse", "ConverseStream", "InvokeModel",
    "InvokeModelWithResponseStream",
})

# Shared sentinel for an absent categorical value. Parentheses rather than angle
# brackets so neither Plotly nor the HTML template reads it as a tag.
MODEL_SENTINEL = "(unknown)"

# The ONLY keys ever written to the cache (Requirement 9.1).
CLOUDTRAIL_ALLOWLIST = frozenset({
    "eventID", "eventTime", "eventName", "eventType", "awsRegion", "errorCode",
    "requestID", "userAgent",
    "principalType",       # userIdentity.type
    "userName",            # userIdentity.userName
    "modelArn",            # first resources[].ARN containing ":foundation-model/"
    "requestedModelId",    # requestParameters.modelId ONLY
    "parentRequestId",     # serviceEventDetails.parentRequestId
    # serviceEventDetails.AdditionalEventData.additionalEntries
    "inferenceRegion", "inputTokens", "outputTokens",
})

_FOUNDATION_MODEL_SEGMENT = ":foundation-model/"

_PARTITION_FILE = "bedrock-events.jsonl"
_SIDECAR_FILE = "_partition.json"

# Discard reason tally keys (Requirement 5.9).
_REASON_NOT_IAM_USER = "not_iam_user"
_REASON_NOT_INFERENCE = "not_inference"
_REASON_NO_PARENT = "no_parent_request_id"
_REASON_OTHER = "other"


@dataclass
class CloudTrailFetchResult:
    """Summary of one CloudTrail fetch run."""

    partitions: int = 0        # Day_Partitions processed (fetched + skipped)
    complete: int = 0          # Partitions recorded complete after the run
    requests: int = 0          # LookupEvents calls including retries
    retained: int = 0          # Records projected and cached
    discarded: int = 0         # Records dropped by the retention filter
    discard_reasons: dict[str, int] = field(default_factory=dict)
    # Exception class name of the failure that stopped the run; None on success.
    failure_class: str | None = None


# --- Projection and retention ---------------------------------------------


def _as_dict(value) -> dict:
    """Return ``value`` when it is a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def _additional_entries(record: dict) -> dict:
    """Read ``serviceEventDetails.AdditionalEventData.additionalEntries``.

    Tolerates both shapes CloudTrail has been observed to use: a mapping of
    key -> value, and a list of ``{"key": ..., "value": ...}`` objects.
    """
    details = _as_dict(record.get("serviceEventDetails"))
    additional = _as_dict(details.get("AdditionalEventData"))
    entries = additional.get("additionalEntries")
    if isinstance(entries, dict):
        return entries
    out: dict = {}
    if isinstance(entries, list):
        for item in entries:
            if not isinstance(item, dict):
                continue
            if "key" in item:
                out[str(item["key"])] = item.get("value")
            else:
                out.update(item)
    return out


def _model_arn(record: dict) -> str | None:
    """First ``resources[].ARN`` containing ``:foundation-model/``, else None."""
    resources = record.get("resources")
    if not isinstance(resources, list):
        return None
    for item in resources:
        if not isinstance(item, dict):
            continue
        arn = item.get("ARN")
        if isinstance(arn, str) and _FOUNDATION_MODEL_SEGMENT in arn:
            return arn
    return None


def _project(record: dict) -> dict:
    """Project a raw CloudTrail record onto :data:`CLOUDTRAIL_ALLOWLIST`.

    Reads ONLY the named source paths. ``userIdentity`` is never copied
    wholesale (it carries ``accessKeyId``, ``principalId``, ``arn`` and
    ``sessionContext``) and ``requestParameters`` contributes only ``modelId``.
    Keys whose source path is absent are omitted rather than nulled.

    Parameters
    ----------
    record : dict
        The parsed ``CloudTrailEvent`` document.

    Returns
    -------
    dict
        A dict whose keys are a subset of :data:`CLOUDTRAIL_ALLOWLIST`.
    """
    identity = _as_dict(record.get("userIdentity"))
    request_parameters = _as_dict(record.get("requestParameters"))
    details = _as_dict(record.get("serviceEventDetails"))
    entries = _additional_entries(record)

    candidates = {
        "eventID": record.get("eventID"),
        "eventTime": record.get("eventTime"),
        "eventName": record.get("eventName"),
        "eventType": record.get("eventType"),
        "awsRegion": record.get("awsRegion"),
        "errorCode": record.get("errorCode"),
        "requestID": record.get("requestID"),
        "userAgent": record.get("userAgent"),
        "principalType": identity.get("type"),
        "userName": identity.get("userName"),
        "modelArn": _model_arn(record),
        "requestedModelId": request_parameters.get("modelId"),
        "parentRequestId": details.get("parentRequestId"),
        "inferenceRegion": entries.get("inferenceRegion"),
        "inputTokens": entries.get("inputTokens"),
        "outputTokens": entries.get("outputTokens"),
    }
    projected = {key: value for key, value in candidates.items()
                 if value is not None}
    # Defence in depth: the comprehension keys are literals, but a future edit
    # must not be able to widen the written key set silently.
    return {key: value for key, value in projected.items()
            if key in CLOUDTRAIL_ALLOWLIST}


def _retain_reason(record: dict) -> str | None:
    """Classify a raw record: ``None`` to keep, else the discard reason.

    Keeps API_Call_Events that are BYOK_Principals with an inference event name,
    and Service_Events that name a parent request. Everything else -- including
    every ``AssumedRole`` service-role call -- is discarded.
    """
    event_type = record.get("eventType")
    if event_type == "AwsApiCall":
        identity = _as_dict(record.get("userIdentity"))
        if identity.get("type") != "IAMUser":
            return _REASON_NOT_IAM_USER
        if record.get("eventName") not in INFERENCE_EVENT_NAMES:
            return _REASON_NOT_INFERENCE
        return None
    if event_type == "AwsServiceEvent":
        details = _as_dict(record.get("serviceEventDetails"))
        parent = details.get("parentRequestId")
        if not parent or not str(parent).strip():
            return _REASON_NO_PARENT
        return None
    return _REASON_OTHER


# --- Partition helpers -----------------------------------------------------


def _partition_dir(cache_dir: Path, region: str, day: date) -> Path:
    """Directory holding one Day_Partition's files."""
    return (Path(cache_dir) / "cloudtrail" / region
            / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}")


def _sort_key(record: dict) -> tuple[str, str]:
    """Deterministic ordering key: ``(eventTime, eventID)`` as text."""
    return (str(record.get("eventTime") or ""), str(record.get("eventID") or ""))


def _serialize(record: dict) -> str:
    """One JSONL line. ``sort_keys`` makes repeated writes byte-identical."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def read_partition(cache_dir: Path, region: str, day: date) -> list[dict]:
    """Read a cached partition's records; unparseable lines are skipped."""
    path = _partition_dir(cache_dir, region, day) / _PARTITION_FILE
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read cached partition %s (%s)",
                       path, exc.__class__.__name__)
        return []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping unparseable cached line %s:%d",
                           path, number)
            continue
        if isinstance(parsed, dict) and parsed.get("eventID"):
            records.append(parsed)
        else:
            logger.warning("Skipping cached line without eventID %s:%d",
                           path, number)
    return records


def read_partition_meta(cache_dir: Path, region: str, day: date) -> dict:
    """Read a partition sidecar; a missing/unparseable one reads as incomplete."""
    path = _partition_dir(cache_dir, region, day) / _SIDECAR_FILE
    if not path.exists():
        return {"complete": False}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Treating unparseable partition sidecar as incomplete: "
                       "%s", path)
        return {"complete": False}
    if not isinstance(parsed, dict):
        return {"complete": False}
    parsed.setdefault("complete", False)
    return parsed


def write_partition(
    cache_dir: Path,
    region: str,
    day: date,
    records: list[dict],
    *,
    complete: bool,
    requests: int,
    fetched_at: datetime,
) -> int:
    """Merge ``records`` into the cached partition and rewrite it.

    Merge is by ``eventID`` with the cached record winning, then the union is
    written sorted by ``(eventTime, eventID)``. Two consecutive fetches over
    identical CloudTrail state therefore leave ``bedrock-events.jsonl``
    byte-identical (Requirement 6.3); only the sidecar's ``fetched_at`` differs.

    A partition that received a request is always written, even with zero
    retained events, so an empty closed day is recorded complete and skipped by
    the next run.

    Returns
    -------
    int
        The merged event count.
    """
    directory = _partition_dir(cache_dir, region, day)
    directory.mkdir(parents=True, exist_ok=True)

    merged: dict[str, dict] = {}
    for record in records:
        event_id = str(record.get("eventID") or "")
        if event_id:
            merged.setdefault(event_id, record)
    for record in read_partition(cache_dir, region, day):
        # Cached record wins on conflict.
        merged[str(record.get("eventID"))] = record

    ordered = sorted(merged.values(), key=_sort_key)
    lines = "".join(f"{_serialize(record)}\n" for record in ordered)
    (directory / _PARTITION_FILE).write_text(lines, encoding="utf-8")
    sidecar = {
        "fetched_at": fetched_at.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "complete": bool(complete),
        "event_count": len(ordered),
        "requests": int(requests),
    }
    (directory / _SIDECAR_FILE).write_text(
        json.dumps(sidecar, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return len(ordered)


def is_closed_partition(day: date, fetch_start: datetime) -> bool:
    """True when ``day`` ended at least ``DELIVERY_LAG_MIN`` before the fetch.

    CloudTrail delivers events up to 15 minutes late, so a day whose end is
    further in the past than that can be trusted once fetched completely. Today
    (and yesterday for a few minutes after midnight) is re-fetched every run,
    which is what makes daily cron runs cheap.
    """
    day_end = datetime(day.year, day.month, day.day,
                       tzinfo=timezone.utc) + timedelta(days=1)
    return day_end + timedelta(minutes=DELIVERY_LAG_MIN) <= _as_utc(fetch_start)


def _as_utc(moment: datetime) -> datetime:
    """Interpret a naive datetime as UTC; convert an aware one to UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _resolve_region() -> str:
    """Region from the boto3 default session, else ``us-east-1`` with INFO."""
    try:
        region = boto3.session.Session().region_name
    except Exception:  # pragma: no cover - defensive
        region = None
    if region:
        return str(region)
    logger.info("No AWS region configured; using the %s fallback for "
                "CloudTrail LookupEvents", DEFAULT_REGION)
    return DEFAULT_REGION


# --- Fetch -----------------------------------------------------------------


class _FetchStopped(Exception):
    """Internal signal: the run must stop after persisting the partition."""

    def __init__(self, failure_class: str | None):
        super().__init__(failure_class or "page_cap")
        self.failure_class = failure_class


def _days_newest_first(window_start: datetime,
                       window_end: datetime) -> list[date]:
    """UTC calendar days covered by the window, newest first."""
    first = window_start.date()
    last = window_end.date()
    days: list[date] = []
    cursor = last
    while cursor >= first:
        days.append(cursor)
        cursor -= timedelta(days=1)
    return days


def _lookup_with_retries(
    cloudtrail_client,
    kwargs: dict,
    result: CloudTrailFetchResult,
    sleep,
    region: str,
) -> dict:
    """One ``LookupEvents`` call, retried on throttling with bounded backoff.

    Raises
    ------
    _FetchStopped
        When throttling persists past the last backoff step, or on any other
        client / credential / endpoint error. The caller persists what it has,
        marks the partition incomplete, and stops the run.
    """
    attempt = 0
    while True:
        try:
            result.requests += 1
            return cloudtrail_client.lookup_events(**kwargs)
        except ClientError as exc:
            code = (exc.response or {}).get("Error", {}).get("Code", "")
            if code in ("ThrottlingException", "Throttling",
                        "TooManyRequestsException"):
                if attempt >= len(THROTTLE_BACKOFF_S):
                    logger.error(
                        "CloudTrail LookupEvents still throttled after %d "
                        "retries in region %s; stopping the fetch",
                        len(THROTTLE_BACKOFF_S), region)
                    raise _FetchStopped("ThrottlingException") from exc
                delay = THROTTLE_BACKOFF_S[attempt]
                attempt += 1
                logger.warning(
                    "CloudTrail LookupEvents throttled; retry %d of %d in %ds",
                    attempt, len(THROTTLE_BACKOFF_S), delay)
                sleep(delay)
                continue
            logger.error("%s calling LookupEvents in region %s",
                         exc.__class__.__name__, region)
            raise _FetchStopped(exc.__class__.__name__) from exc
        except (NoCredentialsError, EndpointConnectionError,
                BotoCoreError) as exc:
            logger.error("%s calling LookupEvents in region %s",
                         exc.__class__.__name__, region)
            raise _FetchStopped(exc.__class__.__name__) from exc


def _parse_cloudtrail_event(entry: dict) -> dict | None:
    """Parse the ``CloudTrailEvent`` JSON string out of a LookupEvents entry."""
    if not isinstance(entry, dict):
        return None
    raw = entry.get("CloudTrailEvent")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def fetch_bedrock_events(
    cache_dir: Path,
    since: date | None = None,
    cloudtrail_client=None,
    now: datetime | None = None,
    sleep=time.sleep,
) -> CloudTrailFetchResult:
    """Fetch Bedrock CloudTrail events into the day-partitioned local cache.

    One ``LookupEvents`` request series per UTC day, newest day first. The API
    supports one lookup attribute and no principal filter, so every Bedrock
    event in the window comes back and is filtered client-side; splitting by day
    makes completeness trackable per partition, makes the page cap resumable,
    and puts the most recent activity first so a capped run still shows current
    data.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory. Writes under ``cache_dir/cloudtrail/``.
    since : date | None
        Lower bound for the Lookback_Window, clamped to the 90-day retention.
    cloudtrail_client : optional
        Pre-configured CloudTrail client. Injected by the tests; when provided
        it is used exclusively and no client is created.
    now : datetime | None
        Fetch start, captured once. Injected for deterministic tests.
    sleep : callable
        Pacing / backoff sleeper. Injected so the tests assert the delays the
        syncer requests rather than waiting for them.

    Returns
    -------
    CloudTrailFetchResult
        Counts and the failure class, if the run stopped early. Never raises:
        a failure degrades to cached-only rendering.
    """
    fetch_start = _as_utc(now or datetime.now(timezone.utc))
    result = CloudTrailFetchResult()

    window_end = fetch_start
    retention_start = fetch_start - timedelta(days=LOOKBACK_DAYS)
    window_start = retention_start
    if since is not None:
        requested = datetime(since.year, since.month, since.day,
                             tzinfo=timezone.utc)
        if requested < retention_start:
            logger.warning(
                "--since %s is earlier than the CloudTrail LookupEvents "
                "90-day retention limit; clamping the window start to %s",
                since.isoformat(), retention_start.date().isoformat())
        else:
            window_start = requested

    region = _resolve_region()
    if cloudtrail_client is None:
        cloudtrail_client = boto3.client("cloudtrail", region_name=region)

    total_pages = 0
    first_request_done = False
    oldest_reached: date | None = None
    stopped: _FetchStopped | None = None

    for day in _days_newest_first(window_start, window_end):
        oldest_reached = day
        closed = is_closed_partition(day, fetch_start)
        cached_meta = read_partition_meta(cache_dir, region, day)
        if closed and bool(cached_meta.get("complete")):
            result.partitions += 1
            result.complete += 1
            continue

        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1) - timedelta(microseconds=1)
        start_time = max(day_start, window_start)
        end_time = min(day_end, window_end)

        retained: list[dict] = []
        partition_requests = 0
        token: str | None = None
        partition_complete = True

        try:
            while True:
                if first_request_done:
                    # Pace at 2 requests/second across the whole run.
                    sleep(MIN_REQUEST_INTERVAL_S)
                kwargs = {
                    "LookupAttributes": [{
                        "AttributeKey": "EventSource",
                        "AttributeValue": EVENT_SOURCE,
                    }],
                    "StartTime": start_time,
                    "EndTime": end_time,
                    "MaxResults": LOOKUP_PAGE_SIZE,
                }
                if token:
                    kwargs["NextToken"] = token
                response = _lookup_with_retries(
                    cloudtrail_client, kwargs, result, sleep, region)
                first_request_done = True
                partition_requests += 1
                total_pages += 1

                for entry in (response.get("Events") or []):
                    record = _parse_cloudtrail_event(entry)
                    if record is None:
                        result.discarded += 1
                        result.discard_reasons[_REASON_OTHER] = (
                            result.discard_reasons.get(_REASON_OTHER, 0) + 1)
                        continue
                    reason = _retain_reason(record)
                    if reason is not None:
                        result.discarded += 1
                        result.discard_reasons[reason] = (
                            result.discard_reasons.get(reason, 0) + 1)
                        continue
                    projected = _project(record)
                    if not projected.get("eventID"):
                        result.discarded += 1
                        result.discard_reasons[_REASON_OTHER] = (
                            result.discard_reasons.get(_REASON_OTHER, 0) + 1)
                        continue
                    retained.append(projected)
                    result.retained += 1

                token = response.get("NextToken") or None
                if total_pages >= CLOUDTRAIL_MAX_PAGES and token:
                    partition_complete = False
                    logger.warning(
                        "CloudTrail page cap of %d reached; oldest partition "
                        "reached is %s. Re-run to resume from the incomplete "
                        "partitions.", CLOUDTRAIL_MAX_PAGES, day.isoformat())
                    raise _FetchStopped(None)
                if not token:
                    break
        except _FetchStopped as exc:
            stopped = exc
            if exc.failure_class is not None:
                partition_complete = False

        merged = write_partition(
            cache_dir, region, day, retained,
            complete=partition_complete, requests=partition_requests,
            fetched_at=fetch_start,
        )
        del merged
        result.partitions += 1
        if partition_complete:
            result.complete += 1

        if stopped is not None:
            result.failure_class = stopped.failure_class
            break

    if result.discard_reasons:
        logger.info(
            "CloudTrail discards by reason: %s",
            ", ".join(f"{reason}={count}" for reason, count
                      in sorted(result.discard_reasons.items())),
        )
    if oldest_reached is not None:
        logger.info("CloudTrail fetch window %s to %s in region %s; oldest "
                    "partition reached %s",
                    window_start.date().isoformat(),
                    window_end.date().isoformat(), region,
                    oldest_reached.isoformat())

    print(
        f"[cloudtrail] partitions={result.partitions} "
        f"complete={result.complete} requests={result.requests} "
        f"retained={result.retained} discarded={result.discarded} "
        f"failed={1 if result.failure_class else 0}"
    )
    return result


def load_partition_meta(cache_dir: Path) -> dict:
    """Summarize the cached partitions for the renderer.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory.

    Returns
    -------
    dict
        ``partition_count``, ``window_start``, ``window_end`` (``YYYY-MM-DD``),
        ``latest_fetched_at`` and ``latest_complete_fetched_at``
        (``YYYY-MM-DD HH:MM``). Empty strings and 0 when nothing is cached.
    """
    root = Path(cache_dir) / "cloudtrail"
    days: list[date] = []
    fetched: list[str] = []
    complete_fetched: list[str] = []
    if root.exists():
        for sidecar in sorted(root.glob("*/*/*/*/" + _SIDECAR_FILE)):
            parts = sidecar.parent.parts
            try:
                day = date(int(parts[-3]), int(parts[-2]), int(parts[-1]))
            except (ValueError, IndexError):
                continue
            days.append(day)
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            stamp = str(meta.get("fetched_at") or "")
            if stamp:
                fetched.append(stamp)
                if meta.get("complete"):
                    complete_fetched.append(stamp)

    def _display(stamps: list[str]) -> str:
        if not stamps:
            return ""
        newest = max(stamps)
        return newest.replace("T", " ").rstrip("Z")[:16]

    return {
        "partition_count": len(days),
        "window_start": min(days).isoformat() if days else "",
        "window_end": max(days).isoformat() if days else "",
        "latest_fetched_at": _display(fetched),
        "latest_complete_fetched_at": _display(complete_fetched),
    }
