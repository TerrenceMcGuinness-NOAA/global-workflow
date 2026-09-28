"""Kiro IDE Usage Dashboard.

A standalone CLI tool that syncs Kiro IDE telemetry from S3, parses daily
user CSV reports and event-level JSON logs into pandas DataFrames, and
renders a self-contained static HTML dashboard with interactive Plotly
charts.

Pipeline: sync -> parse -> render.

See README.md for usage.
"""

__version__ = "1.0.0"
