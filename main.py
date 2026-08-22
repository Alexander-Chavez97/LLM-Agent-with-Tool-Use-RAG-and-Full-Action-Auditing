"""
CLI entry point.

Creates one `sessions` row per run of this script. This is needed now
(not just for step 7's memory) because action_log.session_id is a
foreign key -- if we pass a non-null session_id, a matching row must
already exist in `sessions`.
"""

from google.genai import types
from agent import run_turn
from db.connection import get_connection


def _create_session() -> str:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO sessions DEFAULT VALUES RETURNING id")
            session_id = cur.fetchone()[0]
    return str(session_id)


def main():
    print("Agent CLI. Type 'quit' to exit.\n")
    session_id = _create_session()
    print(f"(session: {session_id})\n")

    history = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_input)]))
        history = run_turn(history, session_id)

        last = history[-1]
        if last.role == "model":
            for part in last.parts:
                if part.text:
                    print(f"Agent: {part.text}\n")


if __name__ == "__main__":
    main()