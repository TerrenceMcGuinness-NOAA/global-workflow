"""By_User_Analytic CSV Parser for Kiro Dashboard.

Reads the daily ``by_user_analytic`` CSVs (per-user IDE feature counters) from
the local cache into a pandas DataFrame.

Two things differ from the User_Report parser and are the reason this is a
separate module rather than a branch inside ``parser.py``:

* the ``Date`` column is ``MM-DD-YYYY``, not ISO-8601; and
* the 46 feature-counter columns are not enumerated anywhere. Their types are
  inferred per column (all-integer -> ``Int64``, otherwise string) so the
  parser stays correct when AWS adds or renames a counter.

Rendering is deferred (Requirement 13.8); this module exists so the data is
captured and the cache is complete when the team decides to chart it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# Columns a well-formed analytics CSV must carry; a file lacking any of them is
# skipped with a warning.
REQUIRED_COLUMNS = ("Date", "UserId", "Chat_MessagesSent")

# NOTE: this differs from the user_report ISO dates.
DATE_FORMAT = "%m-%d-%Y"

# Deduplication natural key.
_DEDUP_KEY = ["Date", "UserId"]


@dataclass
class AnalyticsParseResult:
    """Summary of a by_user_analytic parse operation."""

    df: pd.DataFrame                       # Per-user feature counter frame
    files_parsed: int = 0                  # Successfully parsed file count
    files_skipped: int = 0                 # Malformed / missing-column files
    rows_dropped: int = 0                  # Rows with an unparseable Date
    duplicates_removed: int = 0            # Rows collapsed by deduplication
    warnings: list[str] = field(default_factory=list)


def _empty_analytics_dataframe() -> pd.DataFrame:
    """Empty frame carrying at least the three required columns."""
    return pd.DataFrame({
        "Date": pd.Series(dtype="datetime64[ns]"),
        "UserId": pd.Series(dtype="object"),
        "Chat_MessagesSent": pd.Series(dtype="Int64"),
    })


def _is_integer_column(series: pd.Series) -> bool:
    """True when every non-empty value in ``series`` is an integer numeral."""
    for value in series.tolist():
        if value is None:
            continue
        if not isinstance(value, str):
            try:
                if pd.isna(value):
                    continue
            except (TypeError, ValueError):
                return False
        text = str(value).strip()
        if not text:
            continue
        if text.startswith(("+", "-")):
            text = text[1:]
        if not text.isdigit():
            return False
    return True


def _cast_counter(series: pd.Series) -> pd.Series:
    """Cast a counter column to ``Int64`` with fill default 0."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.round().astype("Int64").fillna(0)


def _cast_text(series: pd.Series) -> pd.Series:
    """Cast a column to python ``str`` in an ``object`` series.

    Mirrors ``parser._cast_column``'s string handling so the dtype is stable
    across pandas versions (pandas 3.0 would otherwise infer its new ``str``
    dtype).
    """
    filled = series.fillna("")
    values = ["" if value is None else str(value) for value in filled.tolist()]
    return pd.Series(values, index=series.index, dtype="object")


def parse_analytics(cache_dir: Path) -> AnalyticsParseResult:
    """Parse all cached by_user_analytic CSVs into one DataFrame.

    Steps:
      1. Glob ``cache_dir/by_user_analytic/**/*.csv`` in sorted path order.
      2. Require ``Date``, ``UserId``, ``Chat_MessagesSent``; skip + WARN
         otherwise.
      3. Parse ``Date`` as ``MM-DD-YYYY``; drop + WARN per unparseable row.
      4. ``UserId`` verbatim string; ``Chat_MessagesSent`` ``Int64`` fill 0;
         every other column ``Int64`` when all non-empty values are integer
         numerals, else string.
      5. Deduplicate ``(Date, UserId)`` keeping the last occurrence; sort.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory. Reads from ``cache_dir/by_user_analytic/``.

    Returns
    -------
    AnalyticsParseResult
        Consolidated DataFrame and parsing summary. Never raises: a bad file is
        skipped, a bad row is dropped.
    """
    analytics_dir = cache_dir / "by_user_analytic"
    warnings: list[str] = []
    files_parsed = 0
    files_skipped = 0
    frames: list[pd.DataFrame] = []

    csv_paths = (sorted(analytics_dir.glob("**/*.csv"))
                 if analytics_dir.exists() else [])

    for path in csv_paths:
        try:
            raw = pd.read_csv(path, dtype=str, keep_default_na=True)
        except Exception as exc:  # malformed / encoding / empty
            files_skipped += 1
            msg = (f"Skipping malformed analytics CSV: {path} "
                   f"({exc.__class__.__name__})")
            warnings.append(msg)
            logger.warning("%s", msg)
            continue
        missing = [name for name in REQUIRED_COLUMNS if name not in raw.columns]
        if missing:
            files_skipped += 1
            msg = (f"Skipping analytics CSV missing required columns "
                   f"{missing}: {path}")
            warnings.append(msg)
            logger.warning("%s", msg)
            continue
        files_parsed += 1
        # Remember the source path so a bad Date can be reported precisely.
        raw = raw.copy()
        raw["_source_path"] = str(path)
        frames.append(raw)

    if not frames:
        msg = f"No valid by_user_analytic CSV files found under {analytics_dir}"
        warnings.append(msg)
        logger.warning("%s", msg)
        return AnalyticsParseResult(
            df=_empty_analytics_dataframe(),
            files_parsed=files_parsed,
            files_skipped=files_skipped,
            warnings=warnings,
        )

    combined = pd.concat(frames, ignore_index=True)
    source_paths = combined.pop("_source_path")

    parsed_dates = pd.to_datetime(
        combined["Date"], format=DATE_FORMAT, errors="coerce")
    bad_mask = parsed_dates.isna()
    rows_dropped = int(bad_mask.sum())
    for position in combined.index[bad_mask]:
        msg = (f"Dropping analytics row with unparseable Date "
               f"'{combined.at[position, 'Date']}' "
               f"(expected {DATE_FORMAT}) in {source_paths.at[position]}")
        warnings.append(msg)
        logger.warning("%s", msg)

    out = pd.DataFrame(index=combined.index)
    out["Date"] = parsed_dates.astype("datetime64[ns]")
    out["UserId"] = _cast_text(combined["UserId"])
    out["Chat_MessagesSent"] = _cast_counter(combined["Chat_MessagesSent"])
    for column in combined.columns:
        if column in ("Date", "UserId", "Chat_MessagesSent"):
            continue
        if _is_integer_column(combined[column]):
            out[column] = _cast_counter(combined[column])
        else:
            out[column] = _cast_text(combined[column])

    out = out[~bad_mask.to_numpy()].copy()

    before = len(out)
    deduped = out.drop_duplicates(subset=_DEDUP_KEY, keep="last")
    duplicates_removed = before - len(deduped)
    sorted_df = deduped.sort_values(_DEDUP_KEY).reset_index(drop=True)

    logger.info(
        "Parsed %d analytics file(s), skipped %d; %d row(s), %d dropped, "
        "%d duplicate(s) removed",
        files_parsed, files_skipped, len(sorted_df), rows_dropped,
        duplicates_removed,
    )

    return AnalyticsParseResult(
        df=sorted_df,
        files_parsed=files_parsed,
        files_skipped=files_skipped,
        rows_dropped=rows_dropped,
        duplicates_removed=duplicates_removed,
        warnings=warnings,
    )
