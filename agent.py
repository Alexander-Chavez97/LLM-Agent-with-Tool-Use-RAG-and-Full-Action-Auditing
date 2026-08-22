"""
Core agent loop -- Gemini version, now with action logging.

The only new thing versus the previous version: the tool-dispatch block
is wrapped with timing + a call to log_action(). This is the ONE place
in the whole codebase that calls log_action -- every tool, current and
future, is covered automatically because of that.
"""

import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

from tools import TOOL_SCHEMAS, dispatch
from logging_utils import log_action

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.5-flash"
MAX_TOOL_ITERATIONS = 8


def _to_gemini_schema(json_schema: dict) -> dict:
    """
    Our tool SCHEMA dicts use standard JSON Schema, e.g.
    {"type": "object", ...}. Gemini expects the same shape but with
    uppercase type names, e.g. {"type": "OBJECT", ...}.
    """
    if not isinstance(json_schema, dict):
        return json_schema
    converted = {}
    for key, value in json_schema.items():
        if key == "type" and isinstance(value, str):
            converted[key] = value.upper()
        elif isinstance(value, dict):
            converted[key] = _to_gemini_schema(value)
        elif isinstance(value, list):
            converted[key] = [_to_gemini_schema(v) for v in value]
        else:
            converted[key] = value
    return converted


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name=schema["name"],
        description=schema["description"],
        parameters=_to_gemini_schema(schema["input_schema"]),
    )
    for schema in TOOL_SCHEMAS
]
_TOOLS = [types.Tool(function_declarations=_FUNCTION_DECLARATIONS)]


def _dispatch_and_log(session_id: str, tool_name: str, tool_input: dict) -> dict:
    """
    Run one tool call, time it, and log exactly one action_log row
    regardless of outcome. Returns the result dict to send back to the
    model either way.
    """
    start = time.perf_counter()
    try:
        result = dispatch(tool_name, tool_input)
        latency_ms = int((time.perf_counter() - start) * 1000)

        # A tool can return {"error": ...} without raising -- e.g. bad
        # SQL, division by zero. That's a failure for audit purposes
        # even though dispatch() itself didn't throw.
        tool_reported_error = isinstance(result, dict) and "error" in result
        log_action(
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=result,
            success=not tool_reported_error,
            error_message=result.get("error") if tool_reported_error else None,
            latency_ms=latency_ms,
        )
        return result

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log_action(
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=None,
            success=False,
            error_message=str(e),
            latency_ms=latency_ms,
        )
        return {"error": str(e)}


def run_turn(history: list, session_id: str) -> list:
    """
    Same contract as before, plus session_id so every tool call this
    turn can be attributed to a session in action_log.
    """
    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.models.generate_content(
            model=MODEL,
            contents=history,
            config=types.GenerateContentConfig(tools=_TOOLS),
        )

        candidate = response.candidates[0]
        history.append(candidate.content)

        function_calls = [
            part.function_call
            for part in candidate.content.parts
            if part.function_call is not None
        ]

        if not function_calls:
            return history

        response_parts = []
        for fc in function_calls:
            result = _dispatch_and_log(session_id, fc.name, dict(fc.args))
            response_parts.append(
                types.Part.from_function_response(name=fc.name, response=result)
            )

        history.append(types.Content(role="user", parts=response_parts))

    history.append(
        types.Content(
            role="model",
            parts=[types.Part.from_text(text="(Stopped: too many tool calls in a row.)")],
        )
    )
    return history