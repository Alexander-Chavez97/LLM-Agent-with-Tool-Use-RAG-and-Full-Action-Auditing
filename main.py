"""
CLI entry point -- Gemini version.

Same shape as before: in-memory history list, replaced by real
persistence in step 7. `types.Content`/`types.Part` are Gemini's
equivalent of Anthropic's plain dicts -- more structured, less
hand-rolled JSON.
"""

from google.genai import types
from agent import run_turn


def main():
    print("Agent CLI. Type 'quit' to exit.\n")
    history = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_input)]))
        history = run_turn(history)

        last = history[-1]
        if last.role == "model":
            for part in last.parts:
                if part.text:
                    print(f"Agent: {part.text}\n")


if __name__ == "__main__":
    main()