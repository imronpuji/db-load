import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn


@dataclass
class ReportPaths:
    json_path: Optional[str]
    csv_path: Optional[str]


class Reporter:
    def __init__(self, update_interval_sec: int = 2, json_path: Optional[str] = None, csv_path: Optional[str] = None) -> None:
        self.console = Console()
        self.update_interval_sec = update_interval_sec
        self.paths = ReportPaths(json_path=json_path, csv_path=csv_path)
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None

    def start(self, title: str = "Running load test...") -> None:
        self._progress = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            transient=True,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(title, total=None)

    def update(self, snapshot: Dict[str, float]) -> None:
        if not self._progress or self._task_id is None:
            return
        msg = f"qps={snapshot.get('qps', 0):.2f} ok={int(snapshot.get('success', 0))} err={int(snapshot.get('error', 0))}"
        self._progress.update(self._task_id, description=msg)

    def stop(self) -> None:
        if self._progress:
            self._progress.stop()

    def write_final(self, summary: Dict[str, float]) -> None:
        # JSON report
        if self.paths.json_path:
            os.makedirs(os.path.dirname(self.paths.json_path), exist_ok=True)
            with open(self.paths.json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
        # CSV report
        if self.paths.csv_path:
            os.makedirs(os.path.dirname(self.paths.csv_path), exist_ok=True)
            with open(self.paths.csv_path, "w", encoding="utf-8") as f:
                f.write("metric,value\n")
                for k, v in summary.items():
                    f.write(f"{k},{v}\n")


__all__ = ["Reporter"]


