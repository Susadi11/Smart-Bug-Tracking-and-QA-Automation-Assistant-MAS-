"""
Code validation and formatting tools.
"""

import ast
import re
from typing import Optional


def strip_markdown_fences(text: str) -> str:
    """
    Extract content from ```language ... ``` fences.
    Falls back to returning the raw text if no fences are found.
    """
    match = re.search(r"```(?:\w+)?\n?(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def validate_python_code(code: str) -> dict:
    """
    Three-layer Python code validator.
    Returns:
      is_valid       — False if code has a syntax error
      syntax_error   — error message or None
      warnings       — list of quality issues
      function_count — number of top-level functions
      has_type_hints — True if any annotations are found
    """
    result = {
        "is_valid": True,
        "syntax_error": None,
        "warnings": [],
        "function_count": 0,
        "has_type_hints": False,
    }

    # Layer 1 — AST syntax check
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        result["is_valid"] = False
        result["syntax_error"] = str(exc)
        return result

    # Layer 2 — structure check
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["function_count"] += 1
            if node.returns or any(a.annotation for a in node.args.args):
                result["has_type_hints"] = True

    # Layer 3 — quality check
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (ast.get_docstring(node)):
                result["warnings"].append(f"Function '{node.name}' has no docstring")
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            result["warnings"].append("Bare 'except:' clause found — catch specific exceptions")

    # Unguarded top-level code check
    for node in tree.body:
        if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
            result["warnings"].append("Unguarded top-level expression found")

    return result
