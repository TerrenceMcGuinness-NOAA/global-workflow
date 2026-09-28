#!/usr/bin/env python3
"""CLI Entry Point for Kiro Dashboard.

Orchestrates S3 sync, the CloudTrail BYOK fetch, parsing, and rendering into a
single command. All diagnostic output goes to stderr; only the final output path
goes to stdout, so the tool composes in pipelines (e.g.
``kiro-dashboard.sh | xargs open``).

Usage
-----
    tools/kiro-dashboard/kiro-dashboard.sh [--sync] [--cloudtrail]
                                          [--since YYYY-MM-DD]
                                          [--output PATH] [--open]

The launcher resolves the interpreter; ``<interpreter> cli.py [flags]`` also
works directly with any Python 3.10+ that has the five runtime libraries.

Exit codes
----------
    0  success (dashboard rendered)
    1  no data available to render
    2  invalid arguments
    3  environment error (interpreter too old / runtime library missing)
"""

from __future__ import annotations

import sys

EXIT_OK = 0
EXIT_NO_DATA = 1
EXIT_BAD_ARGS = 2
EXIT_ENV_ERROR = 3

# Minimum interpreter version and the runtime third-party libraries the tool
# imports. Both are checked by _preflight() before any of them is imported.
_MIN_PY = (3, 10)
_RUNTIME_MODULES = ("pandas", "numpy", "plotly", "jinja2", "boto3")
_REQUIREMENTS_PATH = "tools/kiro-dashboard/requirements.txt"


def _preflight() -> None:
    """Fail fast with one actionable ``[ERROR]`` line and exit code 3.

    Runs before any third-party import and before argument parsing, so a wrong
    interpreter produces a diagnosis instead of a ``ModuleNotFoundError``
    traceback. Adds no output when the environment is healthy.

    Uses ``importlib.util.find_spec`` rather than ``import`` so a broken
    install yields a clean "missing" message instead of a partial traceback.
    """
    import importlib.util
    from datetime import datetime as _datetime

    stamp = _datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    version = "%d.%d.%d" % sys.version_info[:3]

    if sys.version_info < _MIN_PY:
        print(
            f"{stamp} [ERROR] {sys.executable} is Python {version}; the Kiro "
            f"dashboard needs Python "
            f"{_MIN_PY[0]}.{_MIN_PY[1]} or newer. Remedies: run through "
            f"tools/kiro-dashboard/kiro-dashboard.sh, or set "
            f"KIRO_DASHBOARD_PYTHON to an interpreter of version "
            f"{_MIN_PY[0]}.{_MIN_PY[1]} or newer.",
            file=sys.stderr,
        )
        sys.exit(EXIT_ENV_ERROR)

    missing = []
    for name in _RUNTIME_MODULES:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)

    if missing:
        print(
            f"{stamp} [ERROR] {sys.executable} (Python {version}) is missing "
            f"required module(s): {', '.join(missing)}. Install with: "
            f"{sys.executable} -m pip install --user -r {_REQUIREMENTS_PATH}",
            file=sys.stderr,
        )
        sys.exit(EXIT_ENV_ERROR)


_preflight()

# Third-party-bearing imports come only after the preflight, so an unsupported
# interpreter never reaches them (pycodestyle E402 is expected here).
import argparse           # noqa: E402
import logging            # noqa: E402
import webbrowser         # noqa: E402
from datetime import date, datetime   # noqa: E402
from pathlib import Path              # noqa: E402

import analytics_parser   # noqa: E402
import cloudtrail_parser  # noqa: E402
import cloudtrail_sync    # noqa: E402
import event_parser       # noqa: E402
import parser as csv_parser           # noqa: E402
import render             # noqa: E402
import sync               # noqa: E402

logger = logging.getLogger("kiro_dashboard.cli")


def validate_since(value: str) -> date:
    """Parse a ``--since`` value as a ``YYYY-MM-DD`` date.

    Raises ``argparse.ArgumentTypeError`` on an invalid format so argparse
    exits with code 2 before any S3 calls are made.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid date '{value}': expected format YYYY-MM-DD"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="kiro-dashboard",
        description="Sync Kiro IDE telemetry from S3, optionally fetch BYOK "
                    "Bedrock events from CloudTrail, and render a static "
                    "HTML usage dashboard.",
        epilog="Exit codes: 0 success, 1 no data available to render, "
               "2 invalid arguments, 3 environment error (interpreter older "
               "than 3.10, or a runtime library missing).",
    )
    parser.add_argument(
        "--sync", action="store_true",
        help="Download the latest telemetry from S3 before rendering.",
    )
    parser.add_argument(
        "--cloudtrail", action="store_true",
        help="Fetch BYOK Bedrock events from CloudTrail LookupEvents into the "
             "local cache before rendering. Requires cloudtrail:LookupEvents. "
             "Without this flag no CloudTrail API call is made and the BYOK "
             "section renders from whatever is already cached.",
    )
    parser.add_argument(
        "--since", type=validate_since, metavar="YYYY-MM-DD", default=None,
        help="Restrict --sync and --cloudtrail to data on or after this date. "
             "The CloudTrail window is clamped to the 90-day retention limit. "
             "No effect when neither --sync nor --cloudtrail is given.",
    )
    parser.add_argument(
        "--output", type=str, default=None, metavar="PATH",
        help="HTML output path "
             "(default: tools/kiro-dashboard/output/dashboard.html).",
    )
    parser.add_argument(
        "--open", action="store_true",
        help="Open the rendered HTML in the default browser.",
    )
    return parser


def setup_logging() -> None:
    """Configure stderr logging in ``YYYY-MM-DDTHH:MM:SS [LEVEL] message`` form.

    The WARNING level is displayed as ``WARN`` per the CLI logging contract.
    """
    logging.addLevelName(logging.WARNING, "WARN")
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _cache_has_files(cache_dir: Path) -> bool:
    """True if the cache holds any User_Report, Event_Log, or CloudTrail data.

    ``by_user_analytic/`` is deliberately excluded: analytics data alone must
    never cause a Dashboard to be rendered (Requirement 13.7).
    """
    reports = cache_dir / "user_reports"
    events = cache_dir / "events"
    cloudtrail = cache_dir / "cloudtrail"
    if reports.exists() and any(reports.glob("**/*.csv")):
        return True
    if events.exists() and any(events.glob("**/*.json.gz")):
        return True
    if cloudtrail.exists() and any(
            cloudtrail.glob("**/bedrock-events.jsonl")):
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    """Main entry point. Returns the process exit code."""
    arg_parser = build_parser()
    args = arg_parser.parse_args(argv)
    setup_logging()

    since = args.since
    if since is not None and not args.sync and not args.cloudtrail:
        logger.warning("--since has no effect without --sync or --cloudtrail; "
                       "ignoring --since")
        since = None

    cache_dir = sync.DEFAULT_CACHE_DIR

    # The two fetch stages are independent: either may fail without preventing
    # the other or the render, and neither changes the exit code.
    if args.sync:
        sync.sync_all(cache_dir, since=since)

    fetch_failure: str | None = None
    if args.cloudtrail:
        fetch_result = cloudtrail_sync.fetch_bedrock_events(
            cache_dir, since=since)
        fetch_failure = fetch_result.failure_class

    if not args.sync and not args.cloudtrail \
            and not _cache_has_files(cache_dir):
        print(
            "No cached telemetry found. Run with --sync to download data "
            "from S3, and/or --cloudtrail to fetch BYOK Bedrock events, "
            "before rendering.",
            file=sys.stderr,
        )
        return 1

    user_result = csv_parser.parse_user_reports(cache_dir)
    event_result = event_parser.parse_events(cache_dir)
    byok_result = cloudtrail_parser.parse_cloudtrail(cache_dir)
    # Parsed on every render so the frame is available to the renderer, but it
    # never rescues an otherwise-empty run (Requirement 13.7).
    analytics_result = analytics_parser.parse_analytics(cache_dir)

    if (user_result.df.empty and event_result.df.empty
            and byok_result.df.empty):
        print(
            "No data available to render: zero User_Report CSVs, zero "
            "Event_Logs, and zero CloudTrail partitions were successfully "
            "parsed.",
            file=sys.stderr,
        )
        return 1

    if args.output:
        config = render.RenderConfig(output_path=Path(args.output))
    else:
        config = render.RenderConfig()

    byok_meta = cloudtrail_sync.load_partition_meta(cache_dir)
    byok_meta["fetch_failure"] = fetch_failure

    output_path = render.render_dashboard(
        user_result.df, event_result.df, config,
        byok_df=byok_result.df,
        byok_meta=byok_meta,
        per_model_columns=user_result.per_model_columns,
        analytics_df=analytics_result.df,
    )

    if args.open:
        try:
            webbrowser.open(Path(output_path).resolve().as_uri())
        except Exception as exc:  # browser unavailable / headless
            logger.warning("Could not open browser (%s); dashboard written to %s",
                           exc.__class__.__name__, output_path)

    print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
