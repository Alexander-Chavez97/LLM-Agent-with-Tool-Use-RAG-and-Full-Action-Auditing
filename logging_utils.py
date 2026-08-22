"""
Action logging.
 
log_action() is called from exactly ONE place: the tool-dispatch wrapper
in agent.py. That's the whole design -- every current and future tool
gets logged automatically, with zero extra code per tool, because
logging happens around dispatch() rather than inside each tool.
"""

import json
from db.connection import get_connection

def log_action(session_id, tool_name, tool_input, tool_output, success, error_message, latency_ms):
    """
    Write one row to action_log, unconditionally -- success or failure.
 
    Args:
        session_id: UUID of the current session (may be None).
        tool_name: name of the tool that was called.
        tool_input: dict of arguments passed to the tool.
        tool_output: dict returned by the tool, or None if it raised.
        success: False for BOTH raised exceptions AND tool-returned
            {"error": ...} dicts -- a tool "running without crashing"
            isn't the same as it doing what was asked.
        error_message: human-readable failure reason, or None.
        latency_ms: wall-clock time the dispatch call took.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO action_log
                        (session_id, tool_name, tool_input, tool_output,
                         success, error_message, latency_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        tool_name,
                        json.dumps(tool_input),
                        json.dumps(tool_output) if tool_output is not None else None,
                        success,
                        error_message,
                        latency_ms,
                    ),
                )
    except Exception as e:
        # A broken log write must never crash the conversation -- print
        # loudly instead so it's visible during development, but let
        # the agent loop continue.
        print(f"[WARNING] Failed to write action_log row: {e}")