"""
db_query tool.

Lets the model write actual SQL SELECT statements against the `products`
table. Three independent layers of defense, in order of how much they'd
matter if the layer above them failed:

1. Connects using the `agent_readonly` Postgres role (see db/roles.sql),
   which only has SELECT granted -- not the app's main superuser role.
   Even if the validation in this file has a bug, the database itself
   cannot execute a write. This is the layer that actually matters.
2. App-level validation rejects anything that isn't a single SELECT
   statement (blocks stacked queries via ';', blocks DROP/DELETE/etc).
3. Every query is wrapped in a subquery with a hard row LIMIT, so even
   a valid but too-broad SELECT can't flood the model with output or
   blow up the token budget of the response.
"""

import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

_READONLY_URL = os.environ["DATABASE_READONLY_URL"]
_ROW_LIMIT = 50


def _validate_select_only(query: str) -> str:
    q = query.strip().rstrip(";").strip()
    if ";" in q:
        raise ValueError("Multiple statements are not allowed.")
    if not q.lower().startswith("select"):
        raise ValueError("Only SELECT queries are permitted.")
    return q


def run(query: str) -> dict:
    """
    Args:
        query: a single SQL SELECT statement written by the model.

    Returns:
        {"rows": [...], "row_count": N} on success, or {"error": ...}.
        Errors are returned as data, not raised, for the same reason as
        the calculator tool: the caller needs something to send back as
        a tool_result regardless of outcome.
    """
    try:
        safe_query = _validate_select_only(query)
    except ValueError as e:
        return {"error": str(e)}

    wrapped = f"SELECT * FROM ({safe_query}) AS subquery LIMIT {_ROW_LIMIT}"

    try:
        with psycopg.connect(_READONLY_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '3000ms'")
                cur.execute(wrapped)
                rows = cur.fetchall()
                # Decimal/date/etc aren't JSON-serializable by default --
                # stringify anything that isn't a plain JSON-safe type.
                clean_rows = [
                    {
                        k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                        for k, v in row.items()
                    }
                    for row in rows
                ]
                return {"rows": clean_rows, "row_count": len(clean_rows)}
    except psycopg.Error as e:
        return {"error": f"Database error: {e}"}


SCHEMA = {
    "name": "db_query",
    "description": (
        "Run a read-only SQL SELECT query against the 'products' table to "
        "answer questions about product inventory, pricing, or stock. "
        "Table schema: products(id BIGINT, name TEXT, category TEXT, "
        "price_usd NUMERIC, in_stock BOOLEAN). Only SELECT statements are "
        "permitted -- no INSERT/UPDATE/DELETE/DROP. Results are capped at "
        f"{_ROW_LIMIT} rows."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "A single SQL SELECT statement, e.g. "
                    "\"SELECT name, price_usd FROM products "
                    "WHERE category = 'Electronics' ORDER BY price_usd DESC\""
                ),
            }
        },
        "required": ["query"],
    },
}