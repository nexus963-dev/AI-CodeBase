import ast
import json
import os
import re
from pathlib import Path

MANIFEST_FILENAME = ".repix-manifest.json"
IGNORED_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "env", "dist", "build"}
SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".php", ".rb", ".cs"}


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _python_symbols(content: str) -> list[dict]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({
                "name": node.name,
                "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            })
    return sorted(symbols, key=lambda item: item["line"])


def _javascript_symbols(content: str) -> list[dict]:
    patterns = [
        (r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"\b(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", "class"),
        (r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", "function"),
    ]
    symbols = []
    for pattern, kind in patterns:
        for match in re.finditer(pattern, content):
            line = _line_number(content, match.start())
            symbols.append({"name": match.group(1), "kind": kind, "line": line, "end_line": line})
    return sorted(symbols, key=lambda item: (item["line"], item["name"]))


def build_repository_manifest(repository_path: Path) -> dict:
    files = []
    for root, dirs, filenames in os.walk(repository_path):
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRS]
        for filename in sorted(filenames):
            path = Path(root) / filename
            relative_path = path.relative_to(repository_path).as_posix()
            entry = {"path": relative_path, "type": path.suffix.lower() or "file"}
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if path.suffix.lower() == ".py":
                        entry["symbols"] = _python_symbols(content)
                    elif path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}:
                        entry["symbols"] = _javascript_symbols(content)
                    else:
                        entry["symbols"] = []
                except OSError:
                    entry["symbols"] = []
            files.append(entry)

    manifest = {"repository": repository_path.name, "file_count": len(files), "files": files}
    (repository_path / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_repository_manifest(repository_path: Path) -> dict:
    manifest_path = repository_path / MANIFEST_FILENAME
    if not manifest_path.exists():
        return build_repository_manifest(repository_path)
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return build_repository_manifest(repository_path)
