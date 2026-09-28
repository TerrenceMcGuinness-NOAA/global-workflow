"""User Report CSV Parser for Kiro Dashboard.

Reads daily per-user CSV reports from the local cache, handles schema
evolution (missing columns), computes derived metrics, deduplicates, and
returns a consolidated pandas DataFrame.

Resilience: a single malformed file never aborts the parse. Unparseable
files are skipped with a warning; rows with unparseable dates are dropped.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# --- Schema Definition ---

# Canonical column schema: name -> (logical dtype, fill-default). This is the
# single source of truth for the expected CSV columns, their pandas types, and
# the defaults used to backfill columns absent from a given file.
COLUMN_SCHEMA: dict[str, tuple[str, object]] = {
    "Date":                     ("datetime64[ns]", pd.NaT),
    "UserId":                   ("str",            ""),
    "Client_Type":              ("str",            ""),
    "Chat_Conversations":       ("Int64",          0),
    "Credits_Used":             ("float64",        0.0),
    "Overage_Cap":              ("float64",        0.0),
    "Overage_Credits_Used":     ("float64",        0.0),
    "Overage_Enabled":          ("bool",           False),
    "ProfileId":                ("str",            ""),
    "Subscription_Tier":        ("str",            ""),
    "Total_Messages":           ("Int64",          0),
    "New_User":                 ("bool",           False),
    "User_Email":               ("str",            ""),
    "Usage_Limit":              ("Int64",          0),
    "auto_messages":            ("Int64",          0),
    "claude_opus_4.6_messages": ("Int64",          0),
}

# Derived columns added during parsing.
DERIVED_COLUMNS = ["capacity_pct", "credits_per_message"]

# Per_Model_Column_Family: AWS keeps adding one `<model>_messages` counter per
# model release (auto, claude_opus_4.6, claude_opus_5, claude_opus_4.8 in the
# first twelve days). Enumerating them would need a code change per release and
# would silently drop data until someone noticed, so the family is matched by
# rule and every member is preserved. Case-sensitive: `Total_Messages` has
# upper-case letters and so cannot match, and is excluded by name as well.
PER_MODEL_COLUMN_RE = re.compile(r"^[a-z0-9_.]+_messages$")
_FAMILY_EXCLUDE = {"Total_Messages"}

# Columns that must be present for a CSV to be considered well-formed. A file
# lacking either is treated as malformed and skipped.
_REQUIRED_COLUMNS = ("Date", "User_Email")

# Deduplication natural key. Client_Type is part of the key because AWS began
# publishing a KIRO_CLI report alongside the KIRO_IDE report for the same day on
# 2026-09-10; the same user then has two legitimately distinct rows. The empty
# string is a valid key value (COLUMN_SCHEMA backfills it), so a file lacking
# the column still deduplicates correctly.
_DEDUP_KEY = ["Date", "User_Email", "Client_Type"]

# Truthy string tokens for boolean coercion (lowercased).
_TRUE_TOKENS = {"true", "1", "yes", "t", "y"}
_FALSE_TOKENS = {"false", "0", "no", "f", "n", ""}


@dataclass
class ParseResult:
    """Summary of a CSV parse operation."""

    df: pd.DataFrame                       # Consolidated DataFrame
    files_parsed: int = 0                  # Successfully parsed file count
    files_skipped: int = 0                 # Malformed / unparseable file count
    total_rows: int = 0                    # Row count in the final DataFrame
    warnings: list[str] = field(default_factory=list)
    # Per_Model_Column_Family names observed in this parse, in DataFrame column
    # order. A name only backfilled from COLUMN_SCHEMA is NOT listed here.
    per_model_columns: list[str] = field(default_factory=list)


def is_per_model_column(name: str) -> bool:
    """True when ``name`` belongs to the Per_Model_Column_Family.

    Parameters
    ----------
    name : str
        A source column name.

    Returns
    -------
    bool
        True for a lower-case ``<model>_messages`` counter, False for
        ``Total_Messages`` and for anything else.
    """
    if name in _FAMILY_EXCLUDE:
        return False
    return PER_MODEL_COLUMN_RE.match(name) is not None


def _pandas_dtype(logical: str) -> str:
    """Map a logical COLUMN_SCHEMA dtype to a concrete pandas dtype string."""
    return {
        "str": "object",
        "datetime64[ns]": "datetime64[ns]",
        "bool": "bool",
        "Int64": "Int64",
        "float64": "float64",
    }[logical]


def _to_bool(series: pd.Series, default: bool) -> pd.Series:
    """Coerce a series of mixed true/false representations to bool."""

    def _conv(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or (not isinstance(value, str) and pd.isna(value)):
            return default
        token = str(value).strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        return default

    return series.map(_conv).astype("bool")


def _cast_column(series: pd.Series, logical: str, default: object) -> pd.Series:
    """Cast a single column to its logical schema dtype, filling defaults."""
    if logical == "datetime64[ns]":
        # Invalid dates -> NaT (rows dropped later). Mixed ISO formats allowed.
        # pandas 3.0 may infer second-resolution; force ns for schema stability.
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        return parsed.astype("datetime64[ns]")
    if logical == "Int64":
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.round().astype("Int64").fillna(default)
    if logical == "float64":
        numeric = pd.to_numeric(series, errors="coerce").astype("float64")
        return numeric.fillna(default)
    if logical == "bool":
        return _to_bool(series, bool(default))
    # str -> object dtype holding python str (stable across pandas versions;
    # pandas 3.0 would otherwise infer its new `str` dtype).
    filled = series.fillna(default)
    values = ["" if value is None else str(value) for value in filled.tolist()]
    return pd.Series(values, index=series.index, dtype="object")


def _empty_user_dataframe() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical schema + derived columns."""
    data = {
        col: pd.Series(dtype=_pandas_dtype(dtype))
        for col, (dtype, _default) in COLUMN_SCHEMA.items()
    }
    df = pd.DataFrame(data)
    for col in DERIVED_COLUMNS:
        df[col] = pd.Series(dtype="float64")
    return df


def _normalize_schema(
    df: pd.DataFrame,
    per_model_columns: "list[str] | tuple[str, ...]" = (),
) -> pd.DataFrame:
    """Add missing columns with defaults; cast types per COLUMN_SCHEMA.

    Columns named in ``per_model_columns`` that are not already part of
    ``COLUMN_SCHEMA`` are preserved as ``Int64`` with fill default 0, so a
    newly published ``<model>_messages`` counter survives the normalization.
    Every other extra column is dropped so the consolidated schema stays
    stable and deterministic; the caller logs the dropped names once per parse.

    Output column order: ``COLUMN_SCHEMA`` in schema order, then the extra
    Per_Model_Column_Family columns sorted by code point.

    Parameters
    ----------
    df : pd.DataFrame
        Concatenated raw (all-string) rows.
    per_model_columns : list[str] | tuple[str, ...]
        Per_Model_Column_Family names observed across the parsed files.

    Returns
    -------
    pd.DataFrame
        Normalized frame with the canonical dtypes.
    """
    out = pd.DataFrame(index=df.index)
    for col, (logical, default) in COLUMN_SCHEMA.items():
        source = df[col] if col in df.columns else pd.Series(
            [default] * len(df), index=df.index
        )
        out[col] = _cast_column(source, logical, default)
    extra_family = sorted(
        name for name in set(per_model_columns) if name not in COLUMN_SCHEMA
    )
    for col in extra_family:
        source = df[col] if col in df.columns else pd.Series(
            [0] * len(df), index=df.index
        )
        out[col] = _cast_column(source, "Int64", 0)
    return out


def _compute_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``capacity_pct`` and ``credits_per_message`` columns.

    - ``capacity_pct``      = Total_Messages / Usage_Limit * 100
                              (0.0 when Usage_Limit is 0 / missing)
    - ``credits_per_message`` = Credits_Used / Total_Messages
                              (0.0 when Total_Messages is 0)

    Zero-division cases yield 0.0 rather than NaN/Inf, so the outputs are
    always finite float64.
    """
    out = df.copy()
    total_messages = np.nan_to_num(
        out["Total_Messages"].astype("float64").to_numpy(), nan=0.0)
    usage_limit = np.nan_to_num(
        out["Usage_Limit"].astype("float64").to_numpy(), nan=0.0)
    credits_used = np.nan_to_num(
        out["Credits_Used"].astype("float64").to_numpy(), nan=0.0)

    capacity = np.zeros_like(total_messages, dtype="float64")
    cap_mask = usage_limit > 0
    capacity[cap_mask] = (
        total_messages[cap_mask] / usage_limit[cap_mask] * 100.0
    )

    cpm = np.zeros_like(total_messages, dtype="float64")
    cpm_mask = total_messages > 0
    cpm[cpm_mask] = credits_used[cpm_mask] / total_messages[cpm_mask]

    out["capacity_pct"] = capacity
    out["credits_per_message"] = cpm
    return out


def parse_user_reports(cache_dir: Path) -> ParseResult:
    """Parse all cached User_Report CSVs into a consolidated DataFrame.

    Steps:
      1. Glob ``cache_dir/user_reports/**/*.csv``.
      2. Read each CSV (all columns as string); skip malformed with a warning.
      3. Concatenate; normalize columns per ``COLUMN_SCHEMA`` plus every
         observed Per_Model_Column_Family column.
      4. Drop rows whose ``Date`` failed to parse (warn).
      5. Deduplicate on ``(Date, User_Email, Client_Type)`` keeping the last
         occurrence.
      6. Compute derived columns.
      7. Sort by ``(Date, User_Email, Client_Type)`` ascending.

    Parameters
    ----------
    cache_dir : Path
        Root cache directory. Reads from ``cache_dir/user_reports/``.

    Returns
    -------
    ParseResult
        Consolidated DataFrame and parsing summary, including the
        Per_Model_Column_Family names observed in this parse.
    """
    reports_dir = cache_dir / "user_reports"
    warnings: list[str] = []
    files_parsed = 0
    files_skipped = 0
    frames: list[pd.DataFrame] = []
    observed_family: set[str] = set()
    dropped_columns: set[str] = set()

    csv_paths = sorted(reports_dir.glob("**/*.csv")) if reports_dir.exists() else []

    for path in csv_paths:
        try:
            raw = pd.read_csv(path, dtype=str, keep_default_na=True)
        except Exception as exc:  # malformed / encoding / empty
            files_skipped += 1
            msg = f"Skipping malformed CSV: {path} ({exc.__class__.__name__})"
            warnings.append(msg)
            logger.warning("%s", msg)
            continue
        missing_required = [c for c in _REQUIRED_COLUMNS if c not in raw.columns]
        if missing_required:
            files_skipped += 1
            msg = (
                f"Skipping CSV missing required columns "
                f"{missing_required}: {path}"
            )
            warnings.append(msg)
            logger.warning("%s", msg)
            continue
        files_parsed += 1
        for column in raw.columns:
            name = str(column)
            if is_per_model_column(name):
                observed_family.add(name)
            elif name not in COLUMN_SCHEMA:
                dropped_columns.add(name)
        frames.append(raw)

    # One INFO line per parse so schema drift is visible in cron output
    # (Requirement 10.5).
    if dropped_columns:
        logger.info(
            "Dropped %d unknown column(s) not in COLUMN_SCHEMA or the "
            "per-model family: %s",
            len(dropped_columns), ", ".join(sorted(dropped_columns)),
        )

    if not frames:
        msg = f"No valid User_Report CSV files found under {reports_dir}"
        warnings.append(msg)
        logger.warning("%s", msg)
        return ParseResult(
            df=_empty_user_dataframe(),
            files_parsed=files_parsed,
            files_skipped=files_skipped,
            total_rows=0,
            warnings=warnings,
            per_model_columns=[],
        )

    combined = pd.concat(frames, ignore_index=True)
    normalized = _normalize_schema(combined, sorted(observed_family))

    # Drop rows whose Date could not be parsed (Requirement 2.5).
    bad_date_mask = normalized["Date"].isna()
    dropped = int(bad_date_mask.sum())
    if dropped:
        msg = f"Dropped {dropped} row(s) with unparseable Date value"
        warnings.append(msg)
        logger.warning("%s", msg)
    normalized = normalized[~bad_date_mask].copy()

    # Deduplicate on (Date, User_Email, Client_Type), keeping the last one.
    deduped = normalized.drop_duplicates(subset=_DEDUP_KEY, keep="last")

    with_derived = _compute_derived_columns(deduped)
    sorted_df = with_derived.sort_values(_DEDUP_KEY).reset_index(drop=True)

    # DataFrame column order, restricted to the names actually observed.
    per_model_columns = [
        col for col in sorted_df.columns if col in observed_family
    ]

    total_rows = len(sorted_df)
    summary = (
        f"Parsed {files_parsed} file(s), skipped {files_skipped}, "
        f"{total_rows} row(s) in consolidated DataFrame, "
        f"{len(per_model_columns)} per-model column(s)"
    )
    logger.info("%s", summary)

    return ParseResult(
        df=sorted_df,
        files_parsed=files_parsed,
        files_skipped=files_skipped,
        total_rows=total_rows,
        warnings=warnings,
        per_model_columns=per_model_columns,
    )
