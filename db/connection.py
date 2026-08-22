"""
Shared connection helper for the app's own writable operations --
session creation and action logging. Uses the main `agent` role, NOT
agent_readonly, since these need INSERT privileges that the readonly
role deliberately does not have.
"""

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    return psycopg.connect(_DATABASE_URL)