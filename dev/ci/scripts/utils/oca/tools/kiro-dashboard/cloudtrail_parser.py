"""CloudTrail BYOK parser for Kiro Dashboard.

Pairs cached CloudTrail API-call and service-event records into one row per BYOK
inference call.

Pairing happens here rather than in the syncer because a service event can land
in a later page than its parent API call or, at a day boundary, in a later
partition; the parser reads every partition at once.

Nothing in this module touches AWS. It only reads
``cache/cloudtrail/**/bedrock-events.jsonl``, whose keys are already restricted
to ``cloudtrail_sync.CLOUDTRAIL_ALLOWLIST``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from cloudtrail_sync import (INFERENCE_EVENT_NAMES, MODEL_SENTINEL,
                             _FOUNDATION_MODEL_SEGMENT)

logger = logging.getLogger(__name__)


# Exactly the columns of Requirement 7.11, in order.
BYOK_COLUMNS = [
    "eventID", "eventTime", "userName", "eventName", "modelId",
    "requestedModelId", "success", "errorCode", "inputTokens", "outputTokens",
    "inferenceRegion", "clientFamily", "awsRegion", "tokens_available",
]

_VALID_EVENT_TYPES = frozenset({"AwsApiCall", "AwsServiceEvent"})


@dataclass
class CloudTrailParseResult:
    """Summary of a CloudTrail cache parse."""

    df: pd.DataFrame
    files_parsed: int = 0
    files_skipped: int = 0
    lines_skipped: int = 0
    api_calls_retained: int = 0
    api_calls_discarded: int = 0
    service_events_paired: int = 0
    service_events_discarded: int = 0
    warnings: list[str] = field(default_factory=list)


def normalize_model_id(model_arn: str | None,
                       requested_model_id: str | None) -> str:
    """Derive the display model id.

    Order: the text after ``:foundation-model/`` in ``model_arn``; else the text
    after the last ``/`` of ``requested_model_id`` (or the whole value when it
    has no ``/``); else :data:`MODEL_SENTINEL`. Idempotent on its own output and
    never empty (Requirement 7.8).
    """
    if model_arn:
        text = str(model_arn)
        if _FOUNDATION_MODEL_SEGMENT in text:
            tail = text.split(_FOUNDATION_MODEL_SEGMENT, 1)[1].strip()
            if tail:
                return tail
    if requested_model_id:
        text = str(requested_model_id).strip()
        if text:
            tail = text.rsplit("/", 1)[-1].strip() if "/" in text else text
            if tail:
                return tail
    return MODEL_SENTINEL


def client_family(user_agent: str | None) -> str:
    """``'aws-sdk-js/3.901.0 ...'`` -> ``'aws-sdk-js'``; absent -> sentinel."""
    if not user_agent:
        return MODEL_SENTINEL
    text = str(user_agent).strip()
    if not text:
        return MODEL_SENTINEL
    head = text.split("/", 1)[0].strip()
    return head if head else MODEL_SENTINEL


def normalize_user_name(user_name: str | None) -> str:
    """Lower-case and strip; empty -> sentinel.

    The same normalization ``render.normalize_email`` applies to ``User_Email``,
    so the two sources join on the user's email address (Requirement 7.10).
    """
    if not user_name:
        return MODEL_SENTINEL
    text = str(user_name).strip().lower()
    return text if text else MODEL_SENTINEL


def _empty_byok_dataframe() -> pd.DataFrame:
    """Empty frame carrying the exact schema of Requirement 7.11."""
    return pd.DataFrame({
        "eventID": pd.Series(dtype="object"),
        "eventTime": pd.Series(dtype="datetime64[ns, UTC]"),
        "userName": pd.Series(dtype="object"),
        "eventName": pd.Series(dtype="object"),
        "modelId": pd.Series(dtype="object"),
        "requestedModelId": pd.Series(dtype="object"),
        "success": pd.Series(dtype="bool"),
        "errorCode": pd.Series(dtype="object"),
        "inputTokens": pd.Series(dtype="Int64"),
        "outputTokens": pd.Series(dtype="Int64"),
        "inferenceRegion": pd.Series(dtype="object"),
        "clientFamily": pd.Series(dtype="object"),
        "awsRegion": pd.Series(dtype="object"),
        "tokens_available": pd.Series(dtype="bool"),
    })


def _as_int(value) -> int | None:
    """Coerce a token count to int, or None when it is not an integer."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if float(value).is_integer() else None
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("-")
    digits = text[1:] if text.startswith(("+", "-")) else text
    if not digits.isdigit():
        return None
    number = int(digits)
    return -number if negative else number


def _text(value) -> str:
    """Empty string for an absent value, else the stripped text."""
    if value is None:
        return ""
    return str(value).strip()


def _read_records(cache_dir: Path,
                  result: CloudTrailParseResult) -> list[dict]:
    """Read every cached partition file in sorted path order."""
    root = Path(cache_dir) / "cloudtrail"
    paths = sorted(root.glob("**/bedrock-events.jsonl")) if root.exists() else []
    records: list[dict] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            result.files_skipped += 1
            msg = (f"Skipping unreadable CloudTrail partition {path} "
                   f"({exc.__class__.__name__})")
            result.warnings.append(msg)
            logger.warning("%s", msg)
            continue
        result.files_parsed += 1
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                result.lines_skipped += 1
                msg = f"Skipping unparseable JSON line {path}:{number}"
                result.warnings.append(msg)
                logger.warning("%s", msg)
                continue
            if not isinstance(parsed, dict) or not parsed.get("eventID"):
                result.lines_skipped += 1
                msg = f"Skipping line without eventID {path}:{number}"
                result.warnings.append(msg)
                logger.warning("%s", msg)
                continue
            if parsed.get("eventType") not in _VALID_EVENT_TYPES:
                result.lines_skipped += 1
                msg = (f"Skipping line with invalid eventType "
                       f"'{parsed.get('eventType')}' {path}:{number}")
                result.warnings.append(msg)
                logger.warning("%s", msg)
                continue
            stamp = pd.to_datetime(parsed.get("eventTime"), utc=True,
                                   errors="coerce")
            if pd.isna(stamp):
                result.lines_skipped += 1
                msg = f"Skipping line with unparseable eventTime {path}:{number}"
                result.warnings.append(msg)
                logger.warning("%s", msg)
                continue
            parsed["_eventTime"] = stamp
            records.append(parsed)
    return records


def parse_cloudtrail(cache_dir: Path) -> CloudTrailParseResult:
    """Parse the cached CloudTrail partitions into the BYOK DataFrame.

    Steps:
      1. Read every ``cache_dir/cloudtrail/**/bedrock-events.jsonl``; WARN and
         skip an unreadable file, a bad JSON line, or a line missing
         ``eventID`` / a parseable ``eventTime`` / a valid ``eventType``.
      2. Deduplicate by ``eventID`` (first occurrence wins).
      3. Retain API calls with ``principalType == "IAMUser"`` and an inference
         ``eventName``; count and log every other API call as discarded.
      4. Pair each retained call with the service event whose
         ``parentRequestId`` equals its ``requestID`` (earliest wins on
         duplicates); orphan service events are discarded and counted.
      5. Emit the 14 columns of Requirement 7.11, sorted by
         ``(eventTime, eventID)``.

    An unmatched call is kept with ``pd.NA`` tokens and
    ``tokens_available=False`` rather than dropped: in the verified data the
    unpaired calls are exactly the failed ones, and the failure count is real
    signal.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory.

    Returns
    -------
    CloudTrailParseResult
        The BYOK frame and the parse counts.
    """
    result = CloudTrailParseResult(df=_empty_byok_dataframe())
    records = _read_records(cache_dir, result)

    # Deduplicate by eventID, first occurrence wins (Requirement 7.2).
    unique: dict[str, dict] = {}
    for record in records:
        unique.setdefault(str(record["eventID"]), record)

    calls: list[dict] = []
    services: dict[str, dict] = {}
    duplicate_service_events = 0
    for record in unique.values():
        if record.get("eventType") == "AwsApiCall":
            if (record.get("principalType") == "IAMUser"
                    and record.get("eventName") in INFERENCE_EVENT_NAMES):
                calls.append(record)
            else:
                result.api_calls_discarded += 1
            continue
        parent = _text(record.get("parentRequestId"))
        if not parent:
            result.service_events_discarded += 1
            continue
        existing = services.get(parent)
        if existing is None:
            services[parent] = record
        else:
            duplicate_service_events += 1
            candidate_key = (record["_eventTime"], str(record["eventID"]))
            existing_key = (existing["_eventTime"], str(existing["eventID"]))
            if candidate_key < existing_key:
                services[parent] = record

    if duplicate_service_events:
        # The losers are neither paired nor orphaned; count them as discarded so
        # paired + discarded reconciles with the service events read.
        result.service_events_discarded += duplicate_service_events
        msg = (f"{duplicate_service_events} service event(s) share a "
               f"parentRequestId with another; using the earliest of each")
        result.warnings.append(msg)
        logger.warning("%s", msg)

    if result.api_calls_discarded:
        logger.info(
            "Discarded %d cached API call(s) that are not BYOK inference "
            "(non-IAMUser principal or non-inference event name)",
            result.api_calls_discarded)

    rows: list[dict] = []
    for call in calls:
        request_id = _text(call.get("requestID"))
        service = services.pop(request_id, None) if request_id else None
        input_tokens = output_tokens = None
        inference_region = ""
        if service is not None:
            result.service_events_paired += 1
            input_tokens = _as_int(service.get("inputTokens"))
            output_tokens = _as_int(service.get("outputTokens"))
            inference_region = _text(service.get("inferenceRegion"))
        tokens_available = (input_tokens is not None
                            and output_tokens is not None)
        error_code = _text(call.get("errorCode"))
        rows.append({
            "eventID": str(call["eventID"]),
            "eventTime": call["_eventTime"],
            "userName": normalize_user_name(call.get("userName")),
            "eventName": _text(call.get("eventName")),
            "modelId": normalize_model_id(call.get("modelArn"),
                                          call.get("requestedModelId")),
            "requestedModelId": _text(call.get("requestedModelId")),
            "success": error_code == "",
            "errorCode": error_code,
            "inputTokens": input_tokens if tokens_available else pd.NA,
            "outputTokens": output_tokens if tokens_available else pd.NA,
            "inferenceRegion": inference_region if tokens_available else "",
            "clientFamily": client_family(call.get("userAgent")),
            "awsRegion": _text(call.get("awsRegion")),
            "tokens_available": tokens_available,
        })
    result.api_calls_retained = len(rows)
    # Whatever is left never matched a retained call (Requirement 7.6).
    result.service_events_discarded += len(services)

    if not rows:
        msg = ("No CloudTrail BYOK data was found in the cache; run with "
               "--cloudtrail to fetch it")
        result.warnings.append(msg)
        logger.warning("%s", msg)
        logger.info(
            "CloudTrail parse: %d file(s) parsed, %d skipped, %d line(s) "
            "skipped, %d API call(s) retained, %d discarded, %d service "
            "event(s) paired, %d discarded",
            result.files_parsed, result.files_skipped, result.lines_skipped,
            result.api_calls_retained, result.api_calls_discarded,
            result.service_events_paired, result.service_events_discarded)
        return result

    frame = pd.DataFrame(rows, columns=BYOK_COLUMNS)
    frame["eventTime"] = (
        pd.to_datetime(frame["eventTime"], utc=True)
        .astype("datetime64[ns, UTC]")
    )
    frame["inputTokens"] = frame["inputTokens"].astype("Int64")
    frame["outputTokens"] = frame["outputTokens"].astype("Int64")
    frame["success"] = frame["success"].astype("bool")
    frame["tokens_available"] = frame["tokens_available"].astype("bool")
    for column in ("eventID", "userName", "eventName", "modelId",
                   "requestedModelId", "errorCode", "inferenceRegion",
                   "clientFamily", "awsRegion"):
        frame[column] = frame[column].astype("object")
    frame = (frame.sort_values(["eventTime", "eventID"])
             .reset_index(drop=True))
    result.df = frame

    logger.info(
        "CloudTrail parse: %d file(s) parsed, %d skipped, %d line(s) skipped, "
        "%d API call(s) retained, %d discarded, %d service event(s) paired, "
        "%d discarded",
        result.files_parsed, result.files_skipped, result.lines_skipped,
        result.api_calls_retained, result.api_calls_discarded,
        result.service_events_paired, result.service_events_discarded)
    return result
