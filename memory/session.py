"""
Persistent per-session memory.

Reads/writes the `messages` table so a conversation survives past a
single run of `python main.py` -- not just within one process's
lifetime. Two translation problems solved here:

1. Gemini's `Content`/`Part` objects aren't JSON-serializable, and a
   Part can represent three different things (text, a function call, a
   function response) -- we define an explicit, lossless dict format
   for each and convert both directions.
2. The `messages.role` CHECK constraint only allows 'user'/'assistant'
   (written before we picked a provider), but Gemini uses
   'user'/'model'. Rather than loosen the schema to match one
   provider's vocabulary, we translate at this boundary -- the
   database stays provider-agnostic, and only this file needs to know
   Gemini's specific naming.
"""

import json
from google.genai import types
from psycopg.types.json import Jsonb

from db.connection import get_connection

_ROLE_TO_DB = {"user": "user", "model": "assistant"}
_ROLE_FROM_DB = {"user": "user", "assistant": "model"}


def _serialize_part(part: types.Part) -> dict:
    if part.text is not None:
        return {"kind": "text", "text": part.text}
    if part.function_call is not None:
        return {
            "kind": "function_call",
            "name": part.function_call.name,
            "args": dict(part.function_call.args) if part.function_call.args else {},
        }
    if part.function_response is not None:
        return {
            "kind": "function_response",
            "name": part.function_response.name,
            "response": part.function_response.response,
        }
    raise ValueError(f"Unsupported Part shape, nothing set: {part}")


def _deserialize_part(data: dict) -> types.Part:
    kind = data["kind"]
    if kind == "text":
        return types.Part(text=data["text"])
    if kind == "function_call":
        return types.Part(function_call=types.FunctionCall(name=data["name"], args=data["args"]))
    if kind == "function_response":
        return types.Part(
            function_response=types.FunctionResponse(name=data["name"], response=data["response"])
        )
    raise ValueError(f"Unknown part kind in stored message: {kind}")


def save_message(session_id: str, content: types.Content) -> None:
    """
    Persist one Content object (Gemini's unit of "one turn's worth of
    parts") as one row in `messages`.
    """
    db_role = _ROLE_TO_DB[content.role]
    parts_json = [_serialize_part(p) for p in content.parts]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
                # Jsonb(...) tells psycopg to adapt this Python list as a
                # JSONB value -- without it, psycopg has no default rule
                # for turning a raw Python list into the jsonb column type.
                (session_id, db_role, Jsonb(parts_json)),
            )
        conn.commit()


def load_history(session_id: str) -> list[types.Content]:
    """
    Reconstruct the Gemini-format history list for an existing session,
    in the order the conversation actually happened.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM messages WHERE session_id = %s ORDER BY created_at ASC",
                (session_id,),
            )
            rows = cur.fetchall()

    history = []
    for db_role, content_json in rows:
        # psycopg auto-parses jsonb columns back into Python objects,
        # so content_json is already a list of dicts here, not a string.
        parts = [_deserialize_part(p) for p in content_json]
        history.append(types.Content(role=_ROLE_FROM_DB[db_role], parts=parts))
    return history