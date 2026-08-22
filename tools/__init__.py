"""
Tool registry.

This is the single place that knows "what tools exist." agent.py imports
TOOL_SCHEMAS to tell Claude what's available, and calls dispatch() to
actually run one. Adding a new tool later (web_search, db_query, rag
retrieve) means: write the tool module with a `run()` + `SCHEMA`, then
add two lines here. agent.py itself never needs to change.
"""

from tools import calculator, db_query

_REGISTRY = {
    "calculator": calculator,
    "db_query": db_query,
}

TOOL_SCHEMAS = [module.SCHEMA for module in _REGISTRY.values()]


def dispatch(tool_name: str, tool_input: dict) -> dict:
    """
    Run the named tool with the given input, return its result dict.

    Raises KeyError if tool_name isn't registered -- agent.py is
    responsible for catching that and logging/reporting it, since an
    unregistered tool name would mean Claude hallucinated a tool that
    doesn't exist, which is itself worth logging.
    """
    if tool_name not in _REGISTRY:
        raise KeyError(f"Unknown tool: {tool_name}")
    return _REGISTRY[tool_name].run(**tool_input)