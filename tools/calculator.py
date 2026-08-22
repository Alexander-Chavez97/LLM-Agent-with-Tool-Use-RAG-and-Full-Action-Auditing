"""
Calculator tool.
 
Deliberately does NOT use Python's built-in eval() on the raw string --
eval() executes arbitrary Python, so `expression` could contain
`__import__('os').system('rm -rf /')` and Claude (or a prompt-injected
document it read) could trigger it. Instead we parse the expression into
an Abstract Syntax Tree and only allow a small whitelist of node types
(numbers and +, -, *, /, **, parentheses). Anything else -- function
calls, attribute access, names -- raises before any code runs.
"""

import ast
import operator

# Whitelisted operators. Anything not in this dict is rejected.
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg, # unary minus, e.g. -1
    ast.UAdd: operator.pos, # unary plus, e.g. +1
}

def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _ALLOWED_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")

def run(expression: str) -> dict:
    """
    Evaluate a basic arithmetic expression safely.

    Args:
        expression: e.g. "47 * 12", "(3 + 4) / 2", "2 ** 10"

    Returns:
        dict with either {"result": <number>} or {"error": <message>}
        We return errors as data (not raised exceptions) because the
        caller needs to send *something* back to Claude as a tool_result
        even on failure -- Claude can then decide to retry with a fixed
        expression or explain the issue to the user.
    """
    try:
        parsed = ast.parse(expression, mode='eval')
        result = _eval_node(parsed.body)
        return {"result": result}
    except ZeroDivisionError:
        return {"error": "Division by zero"}
    except Exception as e:
        return {"error": f"Could not evaluate expression: {e}"}

# JSON schema Claude uses to know this tool exists and how to call it.
SCHEMA = {
    "name": "calculator",
    "description": (
        "Evaluate a basic arithmetic expression. Supports +, -, *, /, ** "
        "(power), and parentheses. Use this for any numeric computation "
        "rather than doing math yourself -- it's exact, you are not."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A math expression, e.g. '47 * 12' or '(3 + 4) / 2'",
            }
        },
        "required": ["expression"],
    },
}