import os
import asyncio
from typing import Dict, List, Optional, Tuple

import asyncpg


async def _fetch_all(conn: asyncpg.Connection, query: str, *args) -> List[asyncpg.Record]:
    return await conn.fetch(query, *args)


async def discover_candidate_tables(
    database_url: str,
    preferred_keywords: Optional[List[str]] = None,
) -> List[str]:
    if preferred_keywords is None:
        preferred_keywords = ["event", "product"]

    conn: Optional[asyncpg.Connection] = None
    try:
        conn = await asyncpg.connect(database_url, statement_cache_size=0)
        rows = await _fetch_all(
            conn,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
        )
        all_tables = [r["table_name"] for r in rows]

        # Prefer tables whose names contain preferred keywords
        lowered = [t.lower() for t in all_tables]
        preferred = [t for t in all_tables if any(k in t.lower() for k in preferred_keywords)]
        if preferred:
            return preferred
        return all_tables
    finally:
        if conn:
            await conn.close()


async def describe_table(
    database_url: str, table_name: str
) -> Dict[str, Dict[str, Optional[str]]]:
    conn: Optional[asyncpg.Connection] = None
    try:
        conn = await asyncpg.connect(database_url, statement_cache_size=0)
        rows = await _fetch_all(
            conn,
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
            """,
            table_name,
        )
        return {r["column_name"]: {"data_type": r["data_type"]} for r in rows}
    finally:
        if conn:
            await conn.close()


async def sample_primary_key_values(
    database_url: str, table_name: str, limit: int = 1000
) -> List[int]:
    conn: Optional[asyncpg.Connection] = None
    try:
        conn = await asyncpg.connect(database_url, statement_cache_size=0)

        # Attempt to detect primary key column
        pk_rows = await _fetch_all(
            conn,
            """
            SELECT a.attname AS column_name
            FROM   pg_index i
            JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE  i.indrelid = $1::regclass AND i.indisprimary
            """,
            table_name,
        )
        pk_column = pk_rows[0]["column_name"] if pk_rows else "id"

        rows = await _fetch_all(
            conn,
            f"SELECT {pk_column} FROM {table_name} ORDER BY {pk_column} DESC LIMIT $1",
            limit,
        )
        values = []
        for r in rows:
            v = r[pk_column]
            if isinstance(v, int):
                values.append(v)
        return values
    finally:
        if conn:
            await conn.close()


async def pick_query_columns(
    database_url: str, table_name: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns a tuple of (id_like_column, created_at_like_column) if found.
    """
    columns = await describe_table(database_url, table_name)
    id_col = None
    created_col = None
    for c in columns:
        lc = c.lower()
        if id_col is None and (lc == "id" or lc.endswith("_id")):
            id_col = c
        if created_col is None and (lc == "created_at" or lc == "createdon" or lc.endswith("_created_at")):
            created_col = c
    return id_col, created_col


__all__ = [
    "discover_candidate_tables",
    "describe_table",
    "sample_primary_key_values",
    "pick_query_columns",
]


