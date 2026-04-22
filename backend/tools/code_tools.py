"""Code validation and formatting tools."""

import ast
import re


def strip_markdown_fences(text: str) -> str:
    """
    Extract content from markdown code fences.

    Falls back to returning the raw text if no fences are found.

    Args:
        text: Raw string potentially containing ```language ... ``` fences.

    Returns:
        The extracted content, stripped of whitespace.
    """
    match = re.search(r"```(?:\w+)?\n?(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def validate_python_code(code: str) -> dict:
    """
    Three-layer Python code validator.

    Layer 1 — AST syntax check.
    Layer 2 — Structure analysis (function count, type hints).
    Layer 3 — Quality warnings (missing docstrings, bare excepts).

    Args:
        code: Python source code string to validate.

    Returns:
        Dict with keys: is_valid, syntax_error, warnings,
        function_count, has_type_hints.
    """
    result = {
        "is_valid": True,
        "syntax_error": None,
        "warnings": [],
        "function_count": 0,
        "has_type_hints": False,
    }

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        result["is_valid"] = False
        result["syntax_error"] = str(exc)
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["function_count"] += 1
            if node.returns or any(a.annotation for a in node.args.args):
                result["has_type_hints"] = True

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (ast.get_docstring(node)):
                result["warnings"].append(f"Function '{node.name}' has no docstring")
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            result["warnings"].append("Bare 'except:' clause found — catch specific exceptions")

    for node in tree.body:
        if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
            result["warnings"].append("Unguarded top-level expression found")

    return result
