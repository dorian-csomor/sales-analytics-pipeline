"""
Data quality log: every cleansing rule records what it found and what it did.
The log is written to the etl.data_quality_log table and to a Markdown report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class DataQualityLog:
    run_id: str
    entries: list[dict] = field(default_factory=list)

    def record(self, check_id: str, table: str, issue: str, rows: int | pd.Series, action: str) -> None:
        n = int(rows.sum()) if isinstance(rows, pd.Series) else int(rows)
        self.entries.append(dict(run_id=self.run_id, check_id=check_id, source_table=table,
                                 issue=issue, rows_affected=n, action_taken=action))
        level = logging.WARNING if n else logging.INFO
        log.log(level, "[%s] %-12s %-60s %6d rows -> %s", check_id, table, issue, n, action)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries, columns=["run_id", "check_id", "source_table", "issue",
                                                   "rows_affected", "action_taken"])

    def write_report(self, path: Path, summary: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df = self.to_frame()
        lines = [
            "# Data quality report",
            "",
            f"Run `{self.run_id}`",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
        lines += [f"| {k} | {v} |" for k, v in summary.items()]
        lines += [
            "",
            "## Checks",
            "",
            "| # | Table | Issue | Rows | Action |",
            "|---|---|---|---:|---|",
        ]
        for r in df.itertuples():
            lines.append(f"| {r.check_id} | `{r.source_table}` | {r.issue} | {r.rows_affected:,} | {r.action_taken} |")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("Data quality report written to %s", path)
