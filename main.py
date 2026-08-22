"""
CLI entry point.

Supports resuming a previous conversation by session id, loading its
full history back from Postgres via memory/session.py. After every
turn, any NEW messages (user input, tool calls, tool results, final
answer) are saved -- one save point, same "wrap it in exactly one
place" pattern used for logging in agent.py.
"""

import uuid as uuid_lib
from google.genai import types
from agent import run_turn
from db.connection import get_connection
from memory.session import save_message, load_history


def _create_session() -> str:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO sessions DEFAULT VALUES RETURNING id")
            session_id = cur.fetchone()[0]
        conn.commit()
    return str(session_id)


def _session_exists(session_id: str) -> bool:
    # Validate the SHAPE of the input before it ever touches SQL --
    # sending "What's the CAP theorem tradeoff?" straight into a query
    # that expects a UUID crashes with a raw Postgres error instead of
    # a clean "not found." Free-text input should never be trusted to
    # already match what the database expects.
    try:
        uuid_lib.UUID(session_id)
    except ValueError:
        return False

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM sessions WHERE id = %s", (session_id,))
            return cur.fetchone() is not None


def main():
    print("Agent CLI. Type 'quit' to exit.\n")

    resume_id = input("Session id to resume (or press Enter for a new session): ").strip()

    if resume_id:
        if not _session_exists(resume_id):
            print(f"No session found with id {resume_id}. Starting a new session instead.\n")
            session_id = _create_session()
            history = []
        else:
            session_id = resume_id
            history = load_history(session_id)
            print(f"Resumed session {session_id} -- {len(history)} prior message(s) loaded.\n")
    else:
        session_id = _create_session()
        history = []

    print(f"(session: {session_id})\n")

    last_saved_index = len(history)  # anything loaded from DB is already saved

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_input)]))
        history = run_turn(history, session_id)

        # Persist every message added since the last save point -- this
        # covers the user's message, any tool_use/tool_result exchanges,
        # and the final text answer, in one place.
        for content in history[last_saved_index:]:
            save_message(session_id, content)
        last_saved_index = len(history)

        last = history[-1]
        if last.role == "model":
            for part in last.parts:
                if part.text:
                    print(f"Agent: {part.text}\n")


if __name__ == "__main__":
    main()