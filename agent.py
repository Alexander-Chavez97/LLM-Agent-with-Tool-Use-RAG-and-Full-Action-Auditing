"""
Core agent loop 

Gemini calls it function_call / function_response, and uses role="model"
instead of role="assistant". Notice tools/ is untouched -- that's the
payoff of having a provider-agnostic tool registry.
"""

import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

from tools import TOOL_SCHEMAS, dispatch

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.7-flash"
MAX_TOOL_ITERATIONS = 8


def _to_gemini_schema(json_schema: dict) -> dict:
    """
    Our tool SCHEMA dicts (in tools/calculator.py etc.) use standard
    JSON Schema, e.g. {"type": "object", "properties": {...}}. Gemini
    expects the same structure but with uppercase type names, e.g.
    {"type": "OBJECT", ...}. This is the one real adapter problem in
    swapping providers -- everything else lines up conceptually.
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


def run_turn(history: list) -> list:
    """
    history is a list of google.genai.types.Content objects, alternating
    role="user" / role="model".
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
            # Final text answer -- no tool calls requested this round.
            return history

        response_parts = []
        for fc in function_calls:
            try:
                result = dispatch(fc.name, dict(fc.args))
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response=result)
                )
            except Exception as e:
                response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name, response={"error": str(e)}
                    )
                )

        # Function responses go back as role="user", same logic as
        # Anthropic's tool_result: this is the environment/tool layer
        # responding, not a human, but Gemini only has two roles too.
        history.append(types.Content(role="user", parts=response_parts))

    history.append(
        types.Content(
            role="model",
            parts=[types.Part.from_text(text="(Stopped: too many tool calls in a row.)")],
        )
    )
    return history