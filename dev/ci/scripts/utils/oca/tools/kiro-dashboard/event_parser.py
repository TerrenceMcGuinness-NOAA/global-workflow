"""Event Log Parser for Kiro Dashboard.

Decompresses ``.json.gz`` event logs and extracts request-level metadata into
a pandas DataFrame. Prompt and response TEXT is never extracted, stored, or
returned — only character counts.

Privacy contract
----------------
``EXTRACTION_ALLOWLIST`` defines the ONLY fields that leave this module. Any
field not on the list is discarded at parse time. Privacy is enforced by *what
the code extracts* (a short explicit list), not by *what it filters out*.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# --- Privacy Enforcement: Extraction Allowlist ---

# These are the ONLY fields extracted from each event record. Adding a field
# here requires an explicit code change + review.
EXTRACTION_ALLOWLIST = frozenset({
    "timestamp",        # from generateAssistantResponseEventRequest.timeStamp
    "userId",           # from generateAssistantResponseEventRequest.userId
    "modelId",          # from generateAssistantResponseEventRequest.modelId
    "chatTriggerType",  # from generateAssistantResponseEventRequest.chatTriggerType
    "prompt_length",    # len(generateAssistantResponseEventRequest.prompt)
    "response_length",  # len(generateAssistantResponseEventResponse.assistantResponse)
    "requestId",        # from generateAssistantResponseEventResponse.requestId
})

# Canonical event DataFrame column order.
_EVENT_COLUMNS = [
    "timestamp", "userId", "modelId", "chatTriggerType",
    "prompt_length", "response_length", "requestId",
]

_REQUEST_KEY = "generateAssistantResponseEventRequest"
_RESPONSE_KEY = "generateAssistantResponseEventResponse"

# Model_Sentinel for a record whose modelId is null or absent. Parentheses
# rather than angle brackets so neither Plotly nor the HTML template ever reads
# the value as a tag. 28 of the 4,043 live records carry a null modelId; they
# are real requests, so skipping them made the hourly heatmap and the
# events-by-model chart disagree with the file totals (Requirement 12.1).
MODEL_ID_UNKNOWN = "(unknown)"


@dataclass
class EventParseResult:
    """Summary of an event log parse operation."""

    df: pd.DataFrame                       # Per-event metadata DataFrame
    files_parsed: int = 0                  # Successfully parsed file count
    files_skipped: int = 0                 # Failed files (gzip / JSON / records)
    records_parsed: int = 0                # Successfully extracted record count
    records_skipped: int = 0               # Records skipped (missing fields)
    warnings: list[str] = field(default_factory=list)
    # Retained records bucketed under MODEL_ID_UNKNOWN (Requirement 12.3).
    records_unknown_model: int = 0


def _normalize_user_id(raw_id: str) -> str:
    """Split on the first ``.`` and return the portion after the separator.

    ``'d-90661fb7b9.a408a438-...'`` -> ``'a408a438-...'``
    ``'simple-id'``                 -> ``'simple-id'`` (no separator)

    Always returns a non-empty string for a non-empty input: if the portion
    after the first ``.`` is empty (e.g. a trailing-dot id), the original value
    is returned unchanged so the column stays populated and joinable.
    """
    if "." not in raw_id:
        return raw_id
    after = raw_id.split(".", 1)[1]
    return after if after else raw_id


def _extract_record(
    record: dict,
    file_path: str,
    record_index: int,
) -> dict | None:
    """Extract allowlisted fields from a single event record.

    Returns a dict whose keys are exactly ``EXTRACTION_ALLOWLIST``, or ``None``
    if any required field (``timeStamp``, ``userId``, ``requestId``) is missing.

    ``modelId`` is NOT required: a null or absent value maps to
    :data:`MODEL_ID_UNKNOWN` and the record is retained, so event counts
    reconcile with the number of records in the files (Requirement 12.1).

    Privacy: the ``prompt`` and ``assistantResponse`` strings are read only to
    measure their ``len()``; the text is never stored or returned.
    """
    if not isinstance(record, dict):
        return None
    request = record.get(_REQUEST_KEY) or {}
    response = record.get(_RESPONSE_KEY) or {}
    if not isinstance(request, dict) or not isinstance(response, dict):
        return None

    timestamp = request.get("timeStamp")
    user_id = request.get("userId")
    model_id = request.get("modelId")
    request_id = response.get("requestId")

    # Required-field validation (Requirement 3.6 as narrowed by 12.1/12.2).
    if timestamp is None or user_id is None or request_id is None:
        return None

    # Measure prompt / response length only; discard the text immediately.
    prompt = request.get("prompt")
    response_text = response.get("assistantResponse")
    prompt_length = len(prompt) if isinstance(prompt, str) else 0
    response_length = len(response_text) if isinstance(response_text, str) else 0

    chat_trigger = request.get("chatTriggerType") or ""

    # Null / absent / blank modelId -> Model_Sentinel; the record is kept.
    model_text = "" if model_id is None else str(model_id).strip()
    if not model_text or model_text.lower() in {"none", "null"}:
        model_text = MODEL_ID_UNKNOWN

    return {
        "timestamp": timestamp,
        "userId": _normalize_user_id(str(user_id)),
        "modelId": model_text,
        "chatTriggerType": str(chat_trigger),
        "prompt_length": prompt_length,
        "response_length": response_length,
        "requestId": str(request_id),
    }


def _empty_event_dataframe() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical event schema."""
    return pd.DataFrame({
        "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
        "userId": pd.Series(dtype="object"),
        "modelId": pd.Series(dtype="object"),
        "chatTriggerType": pd.Series(dtype="object"),
        "prompt_length": pd.Series(dtype="Int64"),
        "response_length": pd.Series(dtype="Int64"),
        "requestId": pd.Series(dtype="object"),
    })


def _rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Assemble extracted record dicts into the canonical event DataFrame."""
    if not rows:
        return _empty_event_dataframe()
    df = pd.DataFrame(rows, columns=_EVENT_COLUMNS)
    # Parse timestamps as timezone-aware UTC, forcing ns resolution for schema
    # stability (pandas 3.0 may otherwise infer second/microsecond precision).
    df["timestamp"] = (
        pd.to_datetime(df["timestamp"], utc=True, format="ISO8601",
                       errors="coerce")
        .astype("datetime64[ns, UTC]")
    )
    df["prompt_length"] = df["prompt_length"].astype("Int64")
    df["response_length"] = df["response_length"].astype("Int64")
    for col in ("userId", "modelId", "chatTriggerType", "requestId"):
        df[col] = df[col].astype("object")
    return df


def parse_events(cache_dir: Path) -> EventParseResult:
    """Parse all cached event log files into a metadata DataFrame.

    Steps:
      1. Glob ``cache_dir/events/**/*.json.gz``.
      2. For each file: decompress, parse JSON, validate top-level ``records``.
      3. For each record: extract ONLY allowlisted fields.
      4. Normalize ``userId`` and parse ``timestamp`` as UTC.
      5. Return an :class:`EventParseResult` summary.

    Bad files (gzip / JSON / missing ``records``) are skipped with a warning;
    records missing required fields are skipped individually.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory. Reads from ``cache_dir/events/``.

    Returns
    -------
    EventParseResult
        Metadata DataFrame and parsing summary.
    """
    events_dir = cache_dir / "events"
    warnings: list[str] = []
    files_parsed = 0
    files_skipped = 0
    records_parsed = 0
    records_skipped = 0
    records_unknown_model = 0
    rows: list[dict] = []

    gz_paths = sorted(events_dir.glob("**/*.json.gz")) if events_dir.exists() else []

    for path in gz_paths:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:  # BadGzipFile / JSONDecodeError / OSError / ...
            files_skipped += 1
            msg = f"Skipping bad event file: {path} ({exc.__class__.__name__})"
            warnings.append(msg)
            logger.warning("%s", msg)
            continue

        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            files_skipped += 1
            msg = f"Skipping event file with missing/invalid 'records': {path}"
            warnings.append(msg)
            logger.warning("%s", msg)
            continue

        files_parsed += 1
        for index, record in enumerate(data["records"]):
            extracted = _extract_record(record, str(path), index)
            if extracted is None:
                records_skipped += 1
                msg = (
                    f"Skipping record {index} in {path}: "
                    f"missing required field(s)"
                )
                warnings.append(msg)
                logger.warning("%s", msg)
                continue
            records_parsed += 1
            if extracted["modelId"] == MODEL_ID_UNKNOWN:
                records_unknown_model += 1
            rows.append(extracted)

    df = _rows_to_dataframe(rows)

    summary = (
        f"Parsed {files_parsed} event file(s), skipped {files_skipped}; "
        f"{records_parsed} record(s) parsed, {records_skipped} skipped, "
        f"{records_unknown_model} with modelId {MODEL_ID_UNKNOWN}"
    )
    logger.info("%s", summary)

    return EventParseResult(
        df=df,
        files_parsed=files_parsed,
        files_skipped=files_skipped,
        records_parsed=records_parsed,
        records_skipped=records_skipped,
        warnings=warnings,
        records_unknown_model=records_unknown_model,
    )
