"""S3 Data Sync for Kiro Dashboard.

Downloads ``user_report`` CSVs, ``GenerateAssistantResponse`` event logs, and
``by_user_analytic`` CSVs from the ``kiro-logs/`` S3 prefix to the local cache
directory.

The syncer is offline-idempotent: an S3 object key maps deterministically to
a single local cache path (preserving the date-partitioned structure), so a
file already present in the cache is skipped rather than re-downloaded.

All diagnostics go through the ``logging`` module (stderr, once the CLI
configures handlers). ``sync_all`` prints a one-line summary to stdout.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import boto3

logger = logging.getLogger(__name__)


# --- Constants ---

S3_BUCKET = "mdc-mcp-rag-migration"
S3_PREFIX_USER_REPORT = (
    "kiro-logs/AWSLogs/903050880929/KiroLogs/user_report/us-east-1/"
)
S3_PREFIX_EVENTS = (
    "kiro-logs/AWSLogs/903050880929/KiroLogs/"
    "GenerateAssistantResponse/us-east-1/"
)
# Third log type, published since 2026-09-11: one daily CSV of per-user IDE
# feature counters keyed by an opaque UserId and an MM-DD-YYYY Date.
S3_PREFIX_ANALYTICS = (
    "kiro-logs/AWSLogs/903050880929/KiroLogs/by_user_analytic/us-east-1/"
)
# Anchored to this file, not the cwd: a relative path would create a second,
# ungitignored cache of raw prompt text when run from another directory.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"

# Maps the S3 log-type path segment to its local cache subdirectory.
_CACHE_SUBDIR = {
    "user_report": "user_reports",
    "GenerateAssistantResponse": "events",
    "by_user_analytic": "by_user_analytic",
}

# Extracts the YYYY/MM/DD date partition from an S3 key.
_DATE_PARTITION_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")


@dataclass
class SyncResult:
    """Summary of a sync operation."""

    downloaded: int = 0         # Files successfully downloaded
    skipped: int = 0            # Files already in cache
    failed: int = 0             # Files that failed to download
    bytes_transferred: int = 0  # Total bytes downloaded


def _key_partition_date(s3_key: str) -> date | None:
    """Extract the date partition (YYYY/MM/DD) from an S3 key, or None."""
    match = _DATE_PARTITION_RE.search(s3_key)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _list_s3_objects(
    s3_client: "boto3.client",
    prefix: str,
    since: date | None = None,
) -> list[str]:
    """Paginate ``list_objects_v2`` and return matching S3 object keys.

    Iterates every result page via the continuation token. Folder-marker keys
    (those ending in ``/``) are ignored. When ``since`` is provided, only keys
    whose date-partition (``.../YYYY/MM/DD/...``) is on or after ``since`` are
    returned, so earlier partitions are excluded from the download set.

    Parameters
    ----------
    s3_client : boto3.client
        S3 client (injectable for testing).
    prefix : str
        The S3 key prefix to list under.
    since : date | None
        Optional inclusive lower bound on the key's date partition.

    Returns
    -------
    list[str]
        Matching S3 object keys.
    """
    keys: list[str] = []
    kwargs = {"Bucket": S3_BUCKET, "Prefix": prefix}
    while True:
        response = s3_client.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []):
            key = obj.get("Key", "")
            if not key or key.endswith("/"):
                continue
            if since is not None:
                partition = _key_partition_date(key)
                if partition is None or partition < since:
                    continue
            keys.append(key)
        if response.get("IsTruncated") and response.get("NextContinuationToken"):
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
        else:
            break
    return keys


def _s3_key_to_cache_path(
    s3_key: str,
    log_type: str,
    cache_dir: Path,
) -> Path:
    """Map an S3 object key to its deterministic local cache path.

    Strips everything up to and including the ``{log_type}/`` segment and
    appends the remaining date-partitioned path under the cache subdirectory
    for that log type.

    Example
    -------
    >>> _s3_key_to_cache_path(
    ...     "kiro-logs/.../user_report/us-east-1/2026/09/04/00/report.csv",
    ...     "user_report", Path("cache"))
    PosixPath('cache/user_reports/us-east-1/2026/09/04/00/report.csv')
    """
    subdir = _CACHE_SUBDIR[log_type]
    marker = f"{log_type}/"
    idx = s3_key.find(marker)
    if idx == -1:
        # No log-type segment: fall back to the basename to stay deterministic.
        remainder = s3_key.rsplit("/", 1)[-1]
    else:
        remainder = s3_key[idx + len(marker):]
    return cache_dir / subdir / remainder


def _download_to_cache(
    s3_client: "boto3.client",
    s3_key: str,
    local_path: Path,
) -> int:
    """Download a single S3 object to ``local_path``. Returns bytes written.

    Creates parent directories as needed. Raises on failure; the caller
    catches and records the failure in the :class:`SyncResult`.
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)
    s3_client.download_file(S3_BUCKET, s3_key, str(local_path))
    try:
        return local_path.stat().st_size
    except OSError:
        return 0


def _sync_prefix(
    prefix: str,
    log_type: str,
    cache_dir: Path,
    since: date | None,
    s3_client: "boto3.client",
) -> SyncResult:
    """Shared sync loop for a single log type. Returns a SyncResult."""
    result = SyncResult()
    try:
        keys = _list_s3_objects(s3_client, prefix, since=since)
    except Exception as exc:  # boto3 ClientError and friends
        logger.error(
            "Failed to list S3 objects under s3://%s/%s (%s)",
            S3_BUCKET, prefix, exc.__class__.__name__,
        )
        return result

    for s3_key in keys:
        local_path = _s3_key_to_cache_path(s3_key, log_type, cache_dir)
        if local_path.exists():
            result.skipped += 1
            continue
        try:
            written = _download_to_cache(s3_client, s3_key, local_path)
            result.downloaded += 1
            result.bytes_transferred += written
        except Exception as exc:  # boto3 ClientError and friends
            result.failed += 1
            logger.error(
                "Failed to download s3://%s/%s (%s)",
                S3_BUCKET, s3_key, exc.__class__.__name__,
            )
    return result


def sync_user_reports(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    since: date | None = None,
    s3_client: "boto3.client" | None = None,
) -> SyncResult:
    """Download user_report CSVs from S3 to ``cache_dir/user_reports/``.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory. User reports go to ``cache_dir/user_reports/``.
    since : date | None
        If set, only sync files whose date partition is on or after this date.
    s3_client : boto3.client | None
        Optional pre-configured S3 client (for testing / injection). If None,
        a default ``boto3.client('s3')`` is created.

    Returns
    -------
    SyncResult
        Summary of downloaded, skipped, and failed file counts.
    """
    if s3_client is None:
        s3_client = boto3.client("s3")
    (cache_dir / "user_reports").mkdir(parents=True, exist_ok=True)
    return _sync_prefix(
        S3_PREFIX_USER_REPORT, "user_report", cache_dir, since, s3_client
    )


def sync_events(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    since: date | None = None,
    s3_client: "boto3.client" | None = None,
) -> SyncResult:
    """Download GenerateAssistantResponse event logs to ``cache_dir/events/``.

    Same interface and behaviour as :func:`sync_user_reports` but for gzipped
    JSON event logs. Preserves the date-partitioned directory structure.
    """
    if s3_client is None:
        s3_client = boto3.client("s3")
    (cache_dir / "events").mkdir(parents=True, exist_ok=True)
    return _sync_prefix(
        S3_PREFIX_EVENTS, "GenerateAssistantResponse", cache_dir, since, s3_client
    )


def sync_analytics(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    since: date | None = None,
    s3_client: "boto3.client" | None = None,
) -> SyncResult:
    """Download by_user_analytic CSVs to ``cache_dir/by_user_analytic/``.

    Same interface and behaviour as :func:`sync_user_reports` but for the
    per-user IDE feature-counter CSVs, which carry no prompt or response text.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory.
    since : date | None
        If set, only sync files whose date partition is on or after this date.
    s3_client : boto3.client | None
        Optional pre-configured S3 client (for testing / injection).

    Returns
    -------
    SyncResult
        Summary of downloaded, skipped, and failed file counts.
    """
    if s3_client is None:
        s3_client = boto3.client("s3")
    (cache_dir / "by_user_analytic").mkdir(parents=True, exist_ok=True)
    return _sync_prefix(
        S3_PREFIX_ANALYTICS, "by_user_analytic", cache_dir, since, s3_client
    )


def format_summary(
    user_result: SyncResult,
    event_result: SyncResult,
    analytics_result: SyncResult | None = None,
) -> str:
    """Build the one-line stdout summary for a completed sync.

    ``analytics_result`` is optional so a caller that predates the third log
    type still produces the parent's two-source totals.
    """
    results = [user_result, event_result]
    if analytics_result is not None:
        results.append(analytics_result)
    downloaded = sum(result.downloaded for result in results)
    skipped = sum(result.skipped for result in results)
    failed = sum(result.failed for result in results)
    total_bytes = sum(result.bytes_transferred for result in results)
    return (
        f"[sync] downloaded={downloaded} skipped={skipped} "
        f"failed={failed} bytes={total_bytes}"
    )


def sync_all(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    since: date | None = None,
    s3_client: "boto3.client" | None = None,
) -> tuple[SyncResult, SyncResult]:
    """Run the user_report, event, and by_user_analytic prefix syncs.

    Returns ``(user_result, event_result)`` for backward compatibility; the
    analytics counts are folded into the printed ``[sync]`` line
    (Requirement 13.2).
    """
    if s3_client is None:
        s3_client = boto3.client("s3")
    user_result = sync_user_reports(cache_dir, since=since, s3_client=s3_client)
    event_result = sync_events(cache_dir, since=since, s3_client=s3_client)
    analytics_result = sync_analytics(
        cache_dir, since=since, s3_client=s3_client)
    print(format_summary(user_result, event_result, analytics_result))
    return user_result, event_result
