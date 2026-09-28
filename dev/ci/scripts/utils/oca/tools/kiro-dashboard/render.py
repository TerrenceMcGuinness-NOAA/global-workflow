"""Dashboard Renderer for Kiro Dashboard.

Accepts parsed pandas DataFrames (user metrics + event metadata) and produces
a single self-contained HTML file with embedded Plotly charts, summary tables,
and an executive summary panel.

Chart builders return Plotly figures serialised as JSON strings (``fig.to_json``)
so the Jinja2 template can embed them directly into ``Plotly.newPlot()`` calls.
Builders that depend on absent data return ``None`` and the template omits the
corresponding section.
"""

from __future__ import annotations

import calendar
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.offline import get_plotlyjs

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent / "output" / "dashboard.html"
)
_TEMPLATE_NAME = "dashboard.html.j2"

# Capacity color classification thresholds (design Property 7).
_CAP_GREEN = "cap-green"
_CAP_YELLOW = "cap-yellow"
_CAP_RED = "cap-red"

_CAP_COLORS = {
    _CAP_GREEN: "#2ca02c",
    _CAP_YELLOW: "#ffb000",
    _CAP_RED: "#d62728",
}
_UNCAPPED_COLOR = "#7f7f7f"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RenderConfig:
    """Configuration for dashboard rendering."""

    # Anchored to this file, not the cwd, so the default output lands in the
    # gitignored output/ dir regardless of where the CLI is invoked from.
    output_path: Path = _DEFAULT_OUTPUT_PATH
    title: str = "Kiro IDE Usage Dashboard"
    plotly_cdn: bool = False  # Always False for self-contained output


@dataclass
class ExecutiveSummary:
    """Computed executive summary metrics."""

    total_users: int
    total_messages: int
    total_credits: float
    date_range_start: str      # YYYY-MM-DD ("" if no data)
    date_range_end: str        # YYYY-MM-DD ("" if no data)
    active_days: int
    projected_monthly_credits: float
    limited_data: bool         # True if < 2 days of data
    overage_cap: float
    total_overage_used: float
    # Kiro-billed messages split per Client_Type value, count descending then
    # label ascending. Sums to total_messages (Requirement 11.5).
    messages_by_client_type: list[tuple[str, int]] = field(default_factory=list)
    # BYOK figures; all zero when byok_df is empty (Requirement 8.10).
    byok_users: int = 0
    byok_successful_calls: int = 0
    byok_input_tokens: int = 0
    byok_output_tokens: int = 0


@dataclass
class UserSummaryRow:
    """Aggregated per-user summary for the table."""

    email: str
    tier: str
    days_active: int
    total_conversations: int
    total_messages: int
    total_credits: float
    capacity_pct: float
    avg_credits_per_message: float
    last_active: str           # YYYY-MM-DD
    # Distinct Client_Type values seen for this user, sorted and comma-joined;
    # an absent/empty value renders as the sentinel (Requirement 11.4).
    client_types: str = ""
    # Max Usage_Limit among the user's rows on the most recent report date
    # (Requirement 11.3). 0.0 means uncapped.
    usage_limit: float = 0.0


@dataclass
class ByokSummary:
    """Aggregate BYOK figures for the BYOK section header and executive panel."""

    users: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    input_tokens: int = 0            # tokens_available rows only
    output_tokens: int = 0           # tokens_available rows only
    calls_without_tokens: int = 0
    error_breakdown: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class ByokUserRow:
    """One row of the BYOK-versus-Kiro-billed side-by-side table."""

    email: str                       # normalized (lower, strip)
    kiro_messages: int = 0
    kiro_credits: float = 0.0
    byok_successful_calls: int = 0
    byok_failed_calls: int = 0
    byok_input_tokens: int = 0
    byok_output_tokens: int = 0
    byok_models: str = ""
    byok_client_families: str = ""
    byok_last_seen: str = ""         # "YYYY-MM-DD HH:MM" UTC or ""


# ---------------------------------------------------------------------------
# Classification helper
# ---------------------------------------------------------------------------


def capacity_class(capacity_pct: float) -> str:
    """Classify a capacity utilization percentage into a CSS class.

    ``< 50`` -> ``cap-green``; ``50 <= x < 80`` -> ``cap-yellow``;
    ``>= 80`` -> ``cap-red``. Exhaustive and mutually exclusive over all
    non-negative floats.
    """
    if capacity_pct < 50:
        return _CAP_GREEN
    if capacity_pct < 80:
        return _CAP_YELLOW
    return _CAP_RED


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def _fmt_date(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


# Shared sentinel for an absent/empty categorical value. Parentheses rather
# than angle brackets so neither Plotly nor the HTML template ever reads it as
# a tag (matches event_parser.MODEL_ID_UNKNOWN).
UNKNOWN_LABEL = "(unknown)"


def _text_or_unknown(value) -> str:
    """Normalize a cell to a display label, mapping empty/NA to the sentinel."""
    if value is None:
        return UNKNOWN_LABEL
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return UNKNOWN_LABEL
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    return text if text else UNKNOWN_LABEL


def normalize_email(value) -> str:
    """Lower-case and strip an email for the BYOK join (Requirement 7.10)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
    return str(value).strip().lower()


def _client_types_label(group: pd.DataFrame) -> str:
    """Sorted, comma-joined distinct Client_Type values for one user."""
    if "Client_Type" not in group.columns:
        return UNKNOWN_LABEL
    seen = {_text_or_unknown(value) for value in group["Client_Type"].tolist()}
    return ", ".join(sorted(seen))


def _latest_usage_limits(group: pd.DataFrame) -> list[float]:
    """Distinct Usage_Limit values on the group's most recent Date, sorted.

    With two Client_Type rows on that date there can legitimately be two
    values; the caller uses the maximum and warns when they disagree
    (Requirement 11.3).
    """
    if "Usage_Limit" not in group.columns or group.empty:
        return []
    latest = group["Date"].max()
    rows = group[group["Date"] == latest]
    limits = pd.to_numeric(rows["Usage_Limit"], errors="coerce").dropna()
    return sorted({float(value) for value in limits.tolist()})


def _messages_by_client_type(user_df: pd.DataFrame) -> list[tuple[str, int]]:
    """Kiro-billed message totals per Client_Type, count desc then label asc."""
    if user_df is None or user_df.empty:
        return []
    messages = pd.to_numeric(
        user_df["Total_Messages"], errors="coerce").fillna(0)
    if "Client_Type" in user_df.columns:
        labels = user_df["Client_Type"].map(_text_or_unknown)
    else:
        labels = pd.Series([UNKNOWN_LABEL] * len(user_df), index=user_df.index)
    grouped = messages.groupby(labels.to_numpy()).sum()
    pairs = [(str(label), int(total)) for label, total in grouped.items()]
    pairs.sort(key=lambda pair: (-pair[1], pair[0]))
    return pairs


def compute_executive_summary(user_df: pd.DataFrame) -> ExecutiveSummary:
    """Compute high-level metrics for the executive summary panel."""
    if user_df is None or user_df.empty:
        return ExecutiveSummary(
            total_users=0,
            total_messages=0,
            total_credits=0.0,
            date_range_start="",
            date_range_end="",
            active_days=0,
            projected_monthly_credits=0.0,
            limited_data=True,
            overage_cap=0.0,
            total_overage_used=0.0,
            messages_by_client_type=[],
        )

    total_users = int(user_df["User_Email"].nunique())
    total_messages = int(pd.to_numeric(user_df["Total_Messages"],
                                       errors="coerce").fillna(0).sum())
    total_credits = float(pd.to_numeric(user_df["Credits_Used"],
                                        errors="coerce").fillna(0.0).sum())
    active_days = int(user_df["Date"].nunique())
    start = _fmt_date(user_df["Date"].min())
    end = _fmt_date(user_df["Date"].max())

    projected = (total_credits / active_days * 30) if active_days > 0 else 0.0
    limited_data = active_days < 2

    most_recent_date = user_df["Date"].max()
    recent_rows = user_df[user_df["Date"] == most_recent_date]
    overage_cap = float(pd.to_numeric(recent_rows["Overage_Cap"],
                                      errors="coerce").fillna(0.0).max())
    total_overage_used = float(pd.to_numeric(user_df["Overage_Credits_Used"],
                                             errors="coerce").fillna(0.0).sum())

    return ExecutiveSummary(
        total_users=total_users,
        total_messages=total_messages,
        total_credits=total_credits,
        date_range_start=start,
        date_range_end=end,
        active_days=active_days,
        projected_monthly_credits=projected,
        limited_data=limited_data,
        overage_cap=overage_cap,
        total_overage_used=total_overage_used,
        messages_by_client_type=_messages_by_client_type(user_df),
    )


def compute_user_summary_table(user_df: pd.DataFrame) -> list[UserSummaryRow]:
    """Aggregate per-user metrics; sorted by total_credits descending.

    Messages, credits, and conversations are summed across every row for the
    user, so a user with both a ``KIRO_IDE`` and a ``KIRO_CLI`` row on the same
    day is counted once with both contributions (Requirement 11.2).

    Capacity utilization uses the maximum ``Usage_Limit`` among the user's rows
    on their most recent report date (Requirement 11.3); disagreeing values are
    logged once per user.
    """
    if user_df is None or user_df.empty:
        return []

    rows: list[UserSummaryRow] = []
    for email, group in user_df.groupby("User_Email", sort=False):
        ordered = group.sort_values("Date")
        recent = ordered.iloc[-1]

        days_active = int(ordered["Date"].nunique())
        total_conversations = int(pd.to_numeric(
            ordered["Chat_Conversations"], errors="coerce").fillna(0).sum())
        total_messages = int(pd.to_numeric(
            ordered["Total_Messages"], errors="coerce").fillna(0).sum())
        total_credits = float(pd.to_numeric(
            ordered["Credits_Used"], errors="coerce").fillna(0.0).sum())

        limits = _latest_usage_limits(ordered)
        if len(limits) > 1:
            logger.warning(
                "User %s has disagreeing Usage_Limit values on %s (%s); "
                "using the maximum %s",
                email, _fmt_date(ordered["Date"].max()),
                ", ".join(f"{value:g}" for value in limits), f"{max(limits):g}",
            )
        recent_limit = max(limits) if limits else 0.0
        capacity_pct = (total_messages / recent_limit * 100.0
                        if recent_limit > 0 else 0.0)
        avg_cpm = (total_credits / total_messages
                   if total_messages > 0 else 0.0)

        tier = recent["Subscription_Tier"]
        tier = "" if tier is None or pd.isna(tier) else str(tier)

        rows.append(UserSummaryRow(
            email=str(email),
            tier=tier,
            days_active=days_active,
            total_conversations=total_conversations,
            total_messages=total_messages,
            total_credits=total_credits,
            capacity_pct=capacity_pct,
            avg_credits_per_message=avg_cpm,
            last_active=_fmt_date(recent["Date"]),
            client_types=_client_types_label(ordered),
            usage_limit=recent_limit,
        ))

    rows.sort(key=lambda r: r.total_credits, reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Chart builders — each returns a Plotly figure JSON string, or None.
# ---------------------------------------------------------------------------


def _synced_date_range(user_df: pd.DataFrame) -> pd.DatetimeIndex:
    """Continuous daily DatetimeIndex spanning the data's min..max Date."""
    start = pd.Timestamp(user_df["Date"].min()).normalize()
    end = pd.Timestamp(user_df["Date"].max()).normalize()
    return pd.date_range(start, end, freq="D")


def _user_daily_series(group: pd.DataFrame, column: str,
                       date_index: pd.DatetimeIndex) -> pd.Series:
    """Per-day values for one user's column, zero-filled over the full range."""
    daily = (group.assign(_d=group["Date"].dt.normalize())
             .groupby("_d")[column]
             .sum())
    daily = pd.to_numeric(daily, errors="coerce")
    return daily.reindex(date_index, fill_value=0).fillna(0)


def build_daily_credits_chart(user_df: pd.DataFrame) -> str | None:
    """Stacked area chart: daily credits per user (zero-filled days)."""
    if user_df.empty:
        return None
    date_index = _synced_date_range(user_df)
    fig = go.Figure()
    for email, group in user_df.groupby("User_Email", sort=False):
        series = _user_daily_series(group, "Credits_Used", date_index)
        fig.add_trace(go.Scatter(
            x=list(date_index), y=series.to_numpy(),
            mode="lines", name=str(email),
            stackgroup="one",
        ))
    fig.update_layout(title="Daily Credits by User",
                      xaxis_title="Date", yaxis_title="Credits",
                      template="plotly_dark")
    return fig.to_json()


def build_daily_messages_chart(user_df: pd.DataFrame) -> str | None:
    """Grouped bar chart: daily message count per user (zero-filled days)."""
    if user_df.empty:
        return None
    date_index = _synced_date_range(user_df)
    fig = go.Figure()
    for email, group in user_df.groupby("User_Email", sort=False):
        series = _user_daily_series(group, "Total_Messages", date_index)
        fig.add_trace(go.Bar(
            x=list(date_index), y=series.to_numpy(), name=str(email),
        ))
    fig.update_layout(title="Daily Messages by User", barmode="group",
                      xaxis_title="Date", yaxis_title="Messages",
                      template="plotly_dark")
    return fig.to_json()


def build_capacity_chart(user_df: pd.DataFrame) -> str | None:
    """Horizontal bar chart: per-user capacity utilization, color-coded."""
    if user_df.empty:
        return None
    rows = compute_user_summary_table(user_df)
    # Uncapped users are the ones whose max Usage_Limit on their latest date is
    # zero; the value is already on the row, so no second lookup (and no second
    # disagreement WARN) is needed.
    emails, values, colors, labels = [], [], [], []
    for row in rows:
        uncapped = row.usage_limit <= 0
        emails.append(row.email)
        if uncapped:
            values.append(0.0)
            colors.append(_UNCAPPED_COLOR)
            labels.append("uncapped")
        else:
            values.append(row.capacity_pct)
            colors.append(_CAP_COLORS[capacity_class(row.capacity_pct)])
            labels.append(f"{row.capacity_pct:.1f}%")
    fig = go.Figure(go.Bar(
        x=values, y=emails, orientation="h",
        marker_color=colors, text=labels, textposition="auto",
    ))
    fig.update_layout(title="Capacity Utilization by User",
                      xaxis_title="Capacity %", yaxis_title="User",
                      template="plotly_dark")
    return fig.to_json()


def build_tier_distribution_chart(user_df: pd.DataFrame) -> str | None:
    """Pie chart: user count per subscription tier (most recent tier/user)."""
    if user_df.empty:
        return None
    recent_tiers = {}
    for email, group in user_df.groupby("User_Email", sort=False):
        recent = group.sort_values("Date").iloc[-1]
        tier = recent["Subscription_Tier"]
        recent_tiers[email] = "" if tier is None or pd.isna(tier) else str(tier)
    counts = pd.Series(list(recent_tiers.values())).value_counts()
    fig = go.Figure(go.Pie(labels=list(counts.index),
                           values=[int(v) for v in counts.to_numpy()]))
    fig.update_layout(title="Subscription Tier Distribution",
                      template="plotly_dark")
    return fig.to_json()


def build_cost_efficiency_chart(user_df: pd.DataFrame) -> str | None:
    """Line chart: credits per message over time, per user (zero-filled)."""
    if user_df.empty:
        return None
    date_index = _synced_date_range(user_df)
    fig = go.Figure()
    for email, group in user_df.groupby("User_Email", sort=False):
        credits = _user_daily_series(group, "Credits_Used", date_index)
        messages = _user_daily_series(group, "Total_Messages", date_index)
        msgs = messages.to_numpy(dtype="float64")
        crd = credits.to_numpy(dtype="float64")
        cpm = np.zeros_like(crd)
        mask = msgs > 0
        cpm[mask] = crd[mask] / msgs[mask]
        fig.add_trace(go.Scatter(
            x=list(date_index), y=cpm, mode="lines+markers", name=str(email),
        ))
    fig.update_layout(title="Cost Efficiency (Credits per Message)",
                      xaxis_title="Date", yaxis_title="Credits / Message",
                      template="plotly_dark")
    return fig.to_json()


def build_monthly_projection_chart(user_df: pd.DataFrame) -> str | None:
    """Bar chart: actual MTD vs projected monthly credits vs overage cap.

    Returns None if fewer than 2 distinct days of data are available.
    """
    if user_df.empty:
        return None
    active_days = int(user_df["Date"].nunique())
    if active_days < 2:
        return None

    total_credits = float(pd.to_numeric(user_df["Credits_Used"],
                                        errors="coerce").fillna(0.0).sum())
    most_recent = pd.Timestamp(user_df["Date"].max())
    days_in_month = calendar.monthrange(most_recent.year, most_recent.month)[1]
    projected = total_credits / active_days * days_in_month
    recent_rows = user_df[user_df["Date"] == user_df["Date"].max()]
    overage_cap = float(pd.to_numeric(recent_rows["Overage_Cap"],
                                      errors="coerce").fillna(0.0).max())

    fig = go.Figure(go.Bar(
        x=["Actual (MTD)", "Projected (Month)", "Overage Cap"],
        y=[total_credits, projected, overage_cap],
        marker_color=["#1f77b4", "#ff7f0e", "#d62728"],
    ))
    fig.update_layout(title="Monthly Credit Projection",
                      yaxis_title="Credits", template="plotly_dark")
    return fig.to_json()


def build_weekend_weekday_chart(user_df: pd.DataFrame) -> str | None:
    """Bar chart: weekday vs weekend average daily messages and credits.

    Returns None if the date range has zero weekend or zero weekday days.
    """
    if user_df.empty:
        return None
    # Team daily totals (sum across users per calendar day).
    daily = (user_df.assign(_d=user_df["Date"].dt.normalize())
             .groupby("_d")
             .agg(messages=("Total_Messages", "sum"),
                  credits=("Credits_Used", "sum")))
    daily.index = pd.to_datetime(daily.index)
    is_weekend = daily.index.weekday >= 5
    weekend = daily[is_weekend]
    weekday = daily[~is_weekend]
    if weekend.empty or weekday.empty:
        return None

    categories = ["Weekday", "Weekend"]
    avg_messages = [float(pd.to_numeric(weekday["messages"]).mean()),
                    float(pd.to_numeric(weekend["messages"]).mean())]
    avg_credits = [float(pd.to_numeric(weekday["credits"]).mean()),
                   float(pd.to_numeric(weekend["credits"]).mean())]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=categories, y=avg_messages, name="Avg Messages/Day"))
    fig.add_trace(go.Bar(x=categories, y=avg_credits, name="Avg Credits/Day"))
    fig.update_layout(title="Weekend vs Weekday Usage", barmode="group",
                      template="plotly_dark")
    return fig.to_json()


def build_hourly_heatmap(event_df: pd.DataFrame) -> str | None:
    """Heatmap: hour-of-day (Y) x date (X), colored by event count.

    Returns None if event_df is empty.
    """
    if event_df is None or event_df.empty:
        return None
    df = event_df.copy()
    df["_date"] = df["timestamp"].dt.strftime("%Y-%m-%d")
    df["_hour"] = df["timestamp"].dt.hour
    pivot = (df.pivot_table(index="_hour", columns="_date",
                            values="requestId", aggfunc="count", fill_value=0)
             .reindex(range(24), fill_value=0))
    fig = go.Figure(go.Heatmap(
        z=pivot.to_numpy(),
        x=list(pivot.columns),
        y=[f"{h:02d}" for h in pivot.index],
        colorscale="Viridis",
    ))
    fig.update_layout(title="Hourly Activity Heatmap (UTC)",
                      xaxis_title="Date", yaxis_title="Hour of Day (UTC)",
                      template="plotly_dark")
    return fig.to_json()


def build_model_distribution_chart(event_df: pd.DataFrame) -> str | None:
    """Bar chart: event count per modelId. Returns None if event_df is empty.

    A record whose ``modelId`` was null is bucketed under the Model_Sentinel by
    the event parser, so it appears here as its own ``(unknown)`` category
    rather than vanishing (Requirement 12.5).
    """
    if event_df is None or event_df.empty:
        return None
    counts = event_df["modelId"].value_counts()
    fig = go.Figure(go.Bar(
        x=list(counts.index),
        y=[int(v) for v in counts.to_numpy()],
        marker_color="#17becf",
    ))
    fig.update_layout(title="Events by Model", xaxis_title="Model ID",
                      yaxis_title="Event Count", template="plotly_dark")
    return fig.to_json()


def build_kiro_model_split_chart(
    user_df: pd.DataFrame,
    per_model_columns: "Sequence[str]" = (),
) -> str | None:
    """Bar chart: Kiro-billed messages per model, one bar per family column.

    The bar label is the column name with the ``_messages`` suffix removed.
    Returns ``None`` when no Per_Model_Column_Family column was observed, so
    the template can show the "no per-model message columns" notice
    (Requirements 8.7, 10.6).

    Parameters
    ----------
    user_df : pd.DataFrame
        Consolidated user report frame.
    per_model_columns : Sequence[str]
        Family column names from ``ParseResult.per_model_columns``.

    Returns
    -------
    str | None
        Plotly figure JSON, or None when there is nothing to plot.
    """
    if user_df is None or user_df.empty:
        return None
    present = [col for col in per_model_columns if col in user_df.columns]
    if not present:
        return None
    labels: list[str] = []
    totals: list[int] = []
    for col in present:
        labels.append(col[: -len("_messages")] if col.endswith("_messages")
                      else col)
        totals.append(int(pd.to_numeric(user_df[col], errors="coerce")
                          .fillna(0).sum()))
    fig = go.Figure(go.Bar(x=labels, y=totals, marker_color="#9467bd"))
    fig.update_layout(title="Kiro-billed Messages by Model",
                      xaxis_title="Model", yaxis_title="Messages",
                      template="plotly_dark")
    return fig.to_json()


# ---------------------------------------------------------------------------
# BYOK aggregations (CloudTrail side)
# ---------------------------------------------------------------------------


def _int_sum(series: pd.Series) -> int:
    """Sum a possibly-nullable numeric series as a plain int."""
    return int(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def compute_byok_summary(byok_df: pd.DataFrame | None) -> ByokSummary:
    """Aggregate ``byok_df`` into the BYOK section header figures.

    Token sums cover only rows with ``tokens_available`` True: a failed call
    produces no service event and therefore no token counts, and mixing NA into
    the sums would either hide the failures or corrupt the totals
    (Requirement 8.13).

    Parameters
    ----------
    byok_df : pd.DataFrame | None
        BYOK frame from ``cloudtrail_parser.parse_cloudtrail``.

    Returns
    -------
    ByokSummary
        All-zero when ``byok_df`` is None or empty.
    """
    if byok_df is None or byok_df.empty:
        return ByokSummary()

    success = byok_df["success"].astype("boolean").fillna(False)
    available = byok_df["tokens_available"].astype("boolean").fillna(False)
    with_tokens = byok_df[available.to_numpy()]

    failed_rows = byok_df[(~success).to_numpy()]
    codes = (failed_rows["errorCode"].map(
        lambda value: str(value) if value else UNKNOWN_LABEL)
        if not failed_rows.empty else pd.Series(dtype="object"))
    counts: dict[str, int] = {}
    for code in codes.tolist():
        counts[code] = counts.get(code, 0) + 1
    error_breakdown = sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    return ByokSummary(
        users=int(byok_df["userName"].nunique()),
        successful_calls=int(success.sum()),
        failed_calls=int((~success).sum()),
        input_tokens=_int_sum(with_tokens["inputTokens"]),
        output_tokens=_int_sum(with_tokens["outputTokens"]),
        calls_without_tokens=int((~available).sum()),
        error_breakdown=error_breakdown,
    )


def compute_byok_user_table(
    user_df: pd.DataFrame | None,
    byok_df: pd.DataFrame | None,
) -> list[ByokUserRow]:
    """Build the per-user BYOK-versus-Kiro-billed side-by-side rows.

    The two sources are joined on the normalized email only (lower-cased,
    whitespace-stripped) and never per request: a BYOK call and a Kiro message
    are different units. A user present in one source shows zeros and empty
    strings for the other (Requirement 8.3).

    Sorted by BYOK successful calls descending, then Kiro-billed credits
    descending, then email ascending (Requirement 8.4).
    """
    kiro: dict[str, dict] = {}
    if user_df is not None and not user_df.empty \
            and "User_Email" in user_df.columns:
        emails = user_df["User_Email"].map(normalize_email)
        messages = pd.to_numeric(
            user_df["Total_Messages"], errors="coerce").fillna(0)
        credits = pd.to_numeric(
            user_df["Credits_Used"], errors="coerce").fillna(0.0)
        for email, message_count, credit in zip(
                emails.tolist(), messages.tolist(), credits.tolist()):
            if not email:
                continue
            bucket = kiro.setdefault(email, {"messages": 0, "credits": 0.0})
            bucket["messages"] += int(message_count)
            bucket["credits"] += float(credit)

    byok: dict[str, dict] = {}
    if byok_df is not None and not byok_df.empty:
        success = byok_df["success"].astype("boolean").fillna(False).to_numpy()
        available = (byok_df["tokens_available"].astype("boolean")
                     .fillna(False).to_numpy())
        for position, (_index, row) in enumerate(byok_df.iterrows()):
            name = normalize_email(row["userName"]) or UNKNOWN_LABEL
            bucket = byok.setdefault(name, {
                "success": 0, "failed": 0, "input": 0, "output": 0,
                "models": set(), "families": set(), "last_seen": None,
            })
            if success[position]:
                bucket["success"] += 1
            else:
                bucket["failed"] += 1
            if available[position]:
                bucket["input"] += int(pd.to_numeric(
                    row["inputTokens"], errors="coerce") or 0)
                bucket["output"] += int(pd.to_numeric(
                    row["outputTokens"], errors="coerce") or 0)
            model = str(row["modelId"]) if row["modelId"] else UNKNOWN_LABEL
            bucket["models"].add(model)
            family = (str(row["clientFamily"]) if row["clientFamily"]
                      else UNKNOWN_LABEL)
            bucket["families"].add(family)
            stamp = pd.Timestamp(row["eventTime"])
            if bucket["last_seen"] is None or stamp > bucket["last_seen"]:
                bucket["last_seen"] = stamp

    rows: list[ByokUserRow] = []
    for email in sorted(set(kiro) | set(byok)):
        kiro_bucket = kiro.get(email, {"messages": 0, "credits": 0.0})
        byok_bucket = byok.get(email)
        if byok_bucket is None:
            rows.append(ByokUserRow(
                email=email,
                kiro_messages=int(kiro_bucket["messages"]),
                kiro_credits=float(kiro_bucket["credits"]),
            ))
            continue
        last_seen = byok_bucket["last_seen"]
        rows.append(ByokUserRow(
            email=email,
            kiro_messages=int(kiro_bucket["messages"]),
            kiro_credits=float(kiro_bucket["credits"]),
            byok_successful_calls=byok_bucket["success"],
            byok_failed_calls=byok_bucket["failed"],
            byok_input_tokens=byok_bucket["input"],
            byok_output_tokens=byok_bucket["output"],
            byok_models=", ".join(sorted(byok_bucket["models"])),
            byok_client_families=", ".join(sorted(byok_bucket["families"])),
            byok_last_seen=("" if last_seen is None
                            else last_seen.strftime("%Y-%m-%d %H:%M")),
        ))

    rows.sort(key=lambda row: (-row.byok_successful_calls, -row.kiro_credits,
                               row.email))
    return rows


def _byok_date_index(byok_df: pd.DataFrame,
                     byok_meta: dict | None) -> pd.DatetimeIndex:
    """Daily index spanning the cached partition range (Requirement 8.5).

    Falls back to the frame's own event span when no partition metadata is
    supplied, so the builders remain callable with a single argument.
    """
    meta = byok_meta or {}
    start_text = str(meta.get("window_start") or "")
    end_text = str(meta.get("window_end") or "")
    start = pd.to_datetime(start_text, errors="coerce") if start_text else pd.NaT
    end = pd.to_datetime(end_text, errors="coerce") if end_text else pd.NaT
    stamps = pd.to_datetime(byok_df["eventTime"], utc=True, errors="coerce")
    data_start = stamps.min().tz_convert(None).normalize()
    data_end = stamps.max().tz_convert(None).normalize()
    if pd.isna(start) or start > data_start:
        start = data_start
    if pd.isna(end) or end < data_end:
        end = data_end
    return pd.date_range(pd.Timestamp(start).normalize(),
                         pd.Timestamp(end).normalize(), freq="D")


def _byok_daily_counts(byok_df: pd.DataFrame) -> pd.DataFrame:
    """Add a normalized UTC-day column used by both daily BYOK charts."""
    out = byok_df.copy()
    stamps = pd.to_datetime(out["eventTime"], utc=True, errors="coerce")
    out["_day"] = stamps.dt.tz_convert(None).dt.normalize()
    return out


def build_byok_daily_calls_chart(byok_df: pd.DataFrame | None,
                                 byok_meta: dict | None = None) -> str | None:
    """Grouped bar chart: successful BYOK calls per UTC day, one series/user."""
    if byok_df is None or byok_df.empty:
        return None
    frame = _byok_daily_counts(byok_df)
    frame = frame[frame["success"].astype("boolean").fillna(False).to_numpy()]
    date_index = _byok_date_index(byok_df, byok_meta)
    fig = go.Figure()
    for name, group in frame.groupby("userName", sort=True):
        daily = group.groupby("_day")["eventID"].count()
        series = daily.reindex(date_index, fill_value=0).fillna(0)
        fig.add_trace(go.Bar(x=list(date_index),
                             y=[int(v) for v in series.to_numpy()],
                             name=str(name)))
    fig.update_layout(title="BYOK Bedrock Calls per Day (successful)",
                      barmode="group", xaxis_title="Date (UTC)",
                      yaxis_title="BYOK calls", template="plotly_dark")
    return fig.to_json()


def build_byok_daily_tokens_chart(byok_df: pd.DataFrame | None,
                                  byok_meta: dict | None = None) -> str | None:
    """Stacked bar chart: BYOK input and output tokens per UTC day.

    Two stacks per date (input, output); each stack has one trace per user.
    Only rows with ``tokens_available`` True contribute.
    """
    if byok_df is None or byok_df.empty:
        return None
    frame = _byok_daily_counts(byok_df)
    available = frame["tokens_available"].astype("boolean").fillna(False)
    frame = frame[available.to_numpy()]
    date_index = _byok_date_index(byok_df, byok_meta)
    if frame.empty:
        return None
    fig = go.Figure()
    for column, stack_label in (("inputTokens", "input"),
                                ("outputTokens", "output")):
        for name, group in frame.groupby("userName", sort=True):
            daily = (group.assign(
                _v=pd.to_numeric(group[column], errors="coerce").fillna(0))
                .groupby("_day")["_v"].sum())
            series = daily.reindex(date_index, fill_value=0).fillna(0)
            fig.add_trace(go.Bar(
                x=list(date_index),
                y=[int(v) for v in series.to_numpy()],
                name=f"{name} ({stack_label})",
                offsetgroup=stack_label,
                legendgroup=str(name),
            ))
    fig.update_layout(title="BYOK Tokens per Day (input / output stacks)",
                      barmode="stack", xaxis_title="Date (UTC)",
                      yaxis_title="Tokens", template="plotly_dark")
    return fig.to_json()


def build_byok_model_split_chart(byok_df: pd.DataFrame | None) -> str | None:
    """Bar chart: successful BYOK calls per normalized ``modelId``."""
    if byok_df is None or byok_df.empty:
        return None
    success = byok_df["success"].astype("boolean").fillna(False)
    successful = byok_df[success.to_numpy()]
    if successful.empty:
        return None
    counts = successful["modelId"].value_counts()
    fig = go.Figure(go.Bar(
        x=[str(label) for label in counts.index],
        y=[int(value) for value in counts.to_numpy()],
        marker_color="#4c9aff",
    ))
    fig.update_layout(title="BYOK Successful Calls by Model",
                      xaxis_title="Model", yaxis_title="BYOK calls",
                      template="plotly_dark")
    return fig.to_json()


# ---------------------------------------------------------------------------
# Jinja2 helpers
# ---------------------------------------------------------------------------


def _format_number(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "0"
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def _format_float(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "0.00"
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _build_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["format_number"] = _format_number
    env.filters["format_float"] = _format_float
    env.globals["capacity_class"] = capacity_class
    return env


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def render_dashboard(
    user_df: pd.DataFrame,
    event_df: pd.DataFrame,
    config: RenderConfig | None = None,
    *,
    byok_df: pd.DataFrame | None = None,
    byok_meta: dict | None = None,
    per_model_columns: Sequence[str] = (),
    analytics_df: pd.DataFrame | None = None,
) -> Path:
    """Render the full dashboard HTML from parsed data.

    Steps: compute ExecutiveSummary -> compute per-user rows -> compute the
    BYOK aggregates -> build chart JSON -> render Jinja2 template -> write
    output HTML.

    The keyword-only parameters are additive: a caller that passes only
    ``user_df``, ``event_df``, and ``config`` gets the parent dashboard plus the
    "BYOK not fetched" notice.

    Parameters
    ----------
    user_df : pd.DataFrame
        Consolidated User_Report frame.
    event_df : pd.DataFrame
        Event_Log metadata frame.
    config : RenderConfig | None
        Output path / title configuration.
    byok_df : pd.DataFrame | None
        BYOK frame from ``cloudtrail_parser.parse_cloudtrail``.
    byok_meta : dict | None
        Partition metadata from ``cloudtrail_sync.load_partition_meta``, plus
        this run's ``fetch_failure`` class.
    per_model_columns : Sequence[str]
        Family column names from ``ParseResult.per_model_columns``.
    analytics_df : pd.DataFrame | None
        By_User_Analytic frame. Captured but not rendered in this spec.

    Raises
    ------
    OSError
        If the output file cannot be written; the message includes the output
        path and the OS-level failure reason.
    """
    if config is None:
        config = RenderConfig()

    has_user_data = user_df is not None and not user_df.empty
    has_event_data = event_df is not None and not event_df.empty
    has_byok_data = byok_df is not None and not byok_df.empty
    meta = dict(byok_meta or {})
    meta.setdefault("partition_count", 0)
    meta.setdefault("window_start", "")
    meta.setdefault("window_end", "")
    meta.setdefault("latest_fetched_at", "")
    meta.setdefault("latest_complete_fetched_at", "")
    meta.setdefault("fetch_failure", None)

    summary = compute_executive_summary(user_df)
    user_rows = compute_user_summary_table(user_df)
    byok = compute_byok_summary(byok_df)
    byok_user_rows = compute_byok_user_table(user_df, byok_df)

    summary.byok_users = byok.users
    summary.byok_successful_calls = byok.successful_calls
    summary.byok_input_tokens = byok.input_tokens
    summary.byok_output_tokens = byok.output_tokens

    context = {
        "title": config.title,
        "summary": summary,
        "user_rows": user_rows,
        "has_user_data": has_user_data,
        "has_event_data": has_event_data,
        "has_byok_data": has_byok_data,
        "byok": byok,
        "byok_meta": meta,
        "byok_user_rows": byok_user_rows,
        "plotly_js": get_plotlyjs(),
        "generation_timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"),
        # Chart JSON (None where not applicable).
        "chart_daily_credits": None,
        "chart_daily_messages": None,
        "chart_capacity": None,
        "chart_tier_dist": None,
        "chart_cost_eff": None,
        "chart_monthly_projection": None,
        "chart_weekend_weekday": None,
        "chart_hourly_heatmap": None,
        "chart_model_dist": None,
        "chart_byok_daily_calls": None,
        "chart_byok_daily_tokens": None,
        "chart_byok_model_split": None,
        "chart_kiro_model_split": None,
    }

    if has_user_data:
        context["chart_daily_credits"] = build_daily_credits_chart(user_df)
        context["chart_daily_messages"] = build_daily_messages_chart(user_df)
        context["chart_capacity"] = build_capacity_chart(user_df)
        context["chart_tier_dist"] = build_tier_distribution_chart(user_df)
        context["chart_cost_eff"] = build_cost_efficiency_chart(user_df)
        context["chart_monthly_projection"] = build_monthly_projection_chart(user_df)
        context["chart_weekend_weekday"] = build_weekend_weekday_chart(user_df)
        context["chart_kiro_model_split"] = build_kiro_model_split_chart(
            user_df, per_model_columns)

    if has_event_data:
        context["chart_hourly_heatmap"] = build_hourly_heatmap(event_df)
        context["chart_model_dist"] = build_model_distribution_chart(event_df)

    if has_byok_data:
        context["chart_byok_daily_calls"] = build_byok_daily_calls_chart(
            byok_df, meta)
        context["chart_byok_daily_tokens"] = build_byok_daily_tokens_chart(
            byok_df, meta)
        context["chart_byok_model_split"] = build_byok_model_split_chart(byok_df)

    env = _build_environment()
    template = env.get_template(_TEMPLATE_NAME)
    html = template.render(**context)

    output_path = Path(config.output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        raise OSError(
            f"Failed to write dashboard to {output_path}: {exc.strerror or exc}"
        ) from exc

    logger.info("Wrote dashboard to %s", output_path)
    return output_path
