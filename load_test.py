import argparse
import asyncio
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import yaml

from db_inspector import (
    discover_candidate_tables,
    pick_query_columns,
    sample_primary_key_values,
)
from grafana_exporter import start_prometheus_exporter
from metrics import MetricsCollector
from reporter import Reporter
from scenarios import ramp_up, spike, stress, sustained


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class QueryRunner:
    def __init__(
        self,
        database_url: str,
        metrics: MetricsCollector,
        table: str,
        id_column: Optional[str],
        created_column: Optional[str],
        id_samples: List[int],
        simple_weight: float,
        complex_weight: float,
        statement_timeout_ms: int,
    ) -> None:
        self.database_url = database_url
        self.metrics = metrics
        self.table = table
        self.id_column = id_column
        self.created_column = created_column
        self.id_samples = id_samples
        self.simple_weight = simple_weight
        self.complex_weight = complex_weight
        self.statement_timeout_ms = statement_timeout_ms

    async def __call__(self, _idx: int) -> None:
        conn: Optional[asyncpg.Connection] = None
        t0 = time.perf_counter()
        try:
            conn = await asyncpg.connect(self.database_url, statement_cache_size=0)
            t1 = time.perf_counter()
            self.metrics.record_connect(t1 - t0, ok=True)
            await conn.execute(f"SET statement_timeout = {self.statement_timeout_ms}")
        except Exception:
            t1 = time.perf_counter()
            self.metrics.record_connect(t1 - t0, ok=False)
            if conn:
                await conn.close()
            return

        try:
            # Loop a handful of operations to simulate ongoing work per connection
            for _ in range(20):
                await self._execute_random_query(conn)
        finally:
            if conn:
                await conn.close()

    async def _execute_random_query(self, conn: asyncpg.Connection) -> None:
        is_simple = random.random() < self.simple_weight
        t0 = time.perf_counter()
        ok = True
        kind = "simple" if is_simple else "complex"
        try:
            if is_simple:
                await self._run_simple(conn)
            else:
                await self._run_complex(conn)
        except Exception:
            ok = False
        finally:
            t1 = time.perf_counter()
            self.metrics.record_query(t1 - t0, ok=ok, kind=kind)

    async def _run_simple(self, conn: asyncpg.Connection) -> None:
        if self.id_column and self.id_samples:
            value = random.choice(self.id_samples)
            await conn.fetch(
                f"SELECT * FROM {self.table} WHERE {self.id_column} = $1 LIMIT 1",
                value,
            )
        elif self.created_column:
            await conn.fetch(
                f"SELECT * FROM {self.table} ORDER BY {self.created_column} DESC LIMIT 1",
            )
        else:
            await conn.fetch(f"SELECT * FROM {self.table} LIMIT 1")

    async def _run_complex(self, conn: asyncpg.Connection) -> None:
        # Aggregation and filtered scan with offset/limit
        await conn.fetchrow(f"SELECT COUNT(*) AS c FROM {self.table}")
        offset = random.randint(0, 1000)
        await conn.fetch(
            f"SELECT * FROM {self.table} OFFSET {offset} LIMIT 50"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL DB load tester")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--scenario", choices=["ramp-up", "sustained", "spike", "stress"], default=None)
    parser.add_argument("--prometheus-port", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    db_cfg = cfg.get("database", {})
    workload = cfg.get("workload", {})
    queries_cfg = cfg.get("queries", {})
    metrics_cfg = cfg.get("metrics", {})

    database_url = os.getenv("DATABASE_URL", db_cfg.get("url"))
    if not database_url:
        raise SystemExit("DATABASE_URL or database.url must be provided")

    if metrics_cfg.get("enable_prometheus", True):
        port = args.prometheus_port or metrics_cfg.get("prometheus_port", 9090)
        start_prometheus_exporter(int(port))

    metrics = MetricsCollector()
    reporter = Reporter(
        update_interval_sec=int(metrics_cfg.get("update_interval_sec", 2)),
        json_path=metrics_cfg.get("report_json"),
        csv_path=metrics_cfg.get("report_csv"),
    )

    # Inspect DB and choose a table to target
    candidate_tables = await discover_candidate_tables(database_url)
    if not candidate_tables:
        raise SystemExit("No tables discovered in the database.")
    target_table = candidate_tables[0]
    id_col, created_col = await pick_query_columns(database_url, target_table)
    id_samples = await sample_primary_key_values(database_url, target_table, limit=1000)

    runner = QueryRunner(
        database_url=database_url,
        metrics=metrics,
        table=target_table,
        id_column=id_col,
        created_column=created_col,
        id_samples=id_samples,
        simple_weight=float(queries_cfg.get("simple_weight", 0.7)),
        complex_weight=float(queries_cfg.get("complex_weight", 0.3)),
        statement_timeout_ms=int(db_cfg.get("statement_timeout_ms", 15000)),
    )

    # Orchestrate scenario
    reporter.start()

    async def periodic_report() -> None:
        try:
            while True:
                reporter.update(metrics.snapshot())
                await asyncio.sleep(int(metrics_cfg.get("update_interval_sec", 2)))
        except asyncio.CancelledError:
            pass

    reporter_task = asyncio.create_task(periodic_report())

    scenario = args.scenario or workload.get("default_scenario", "ramp-up")
    try:
        if scenario == "ramp-up":
            await ramp_up(
                start_connections=int(workload["ramp_up"]["start_connections"]),
                end_connections=int(workload["ramp_up"]["end_connections"]),
                duration_sec=int(workload["ramp_up"]["duration_sec"]),
                worker=runner,
            )
        elif scenario == "sustained":
            await sustained(
                connections=int(workload["sustained"]["connections"]),
                duration_sec=int(workload["sustained"]["duration_sec"]),
                worker=runner,
            )
        elif scenario == "spike":
            await spike(
                base_connections=int(workload["spike"]["base_connections"]),
                spike_connections=int(workload["spike"]["spike_connections"]),
                spike_duration_sec=int(workload["spike"]["spike_duration_sec"]),
                cycles=int(workload["spike"]["cycles"]),
                worker=runner,
            )
        elif scenario == "stress":
            await stress(
                start_connections=int(workload["stress"]["start_connections"]),
                step=int(workload["stress"]["step"]),
                max_connections=int(workload["stress"]["max_connections"]),
                step_duration_sec=int(workload["stress"]["step_duration_sec"]),
                worker=runner,
            )
        else:
            raise SystemExit(f"Unknown scenario: {scenario}")
    finally:
        reporter_task.cancel()
        with contextlib.suppress(Exception):
            await reporter_task
        reporter.stop()
        reporter.write_final(metrics.snapshot())


if __name__ == "__main__":
    import contextlib

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


