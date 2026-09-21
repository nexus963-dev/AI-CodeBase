import ast
from typing import List


def create_chunks(repository_data: List[dict]) -> List[dict]:
    """
    Creates searchable chunks from a repository.

    Supports:
    - Markdown/documentation files
    - Python functions
    - Python classes
    - Other text-based files
    """

    repository_chunks = []
    chunk_number = 1

    for file in repository_data:

        file_path = file["file_path"]
        file_name = file["name"]
        content = file["content"]

        # ---------------------------------------------------------
        # Documentation files
        # ---------------------------------------------------------

        if file_name.lower() in {
            "readme.md",
            "readme",
        }:

            chunk = {
                "file_path": file_path,
                "name": file_name,
                "chunk_type": "documentation",
                "chunk": content,
                "chunk_number": chunk_number,
            }

            repository_chunks.append(chunk)
            chunk_number += 1

            continue

        # ---------------------------------------------------------
        # Other Markdown files
        # ---------------------------------------------------------

        if file_name.lower().endswith(".md"):

            chunk = {
                "file_path": file_path,
                "name": file_name,
                "chunk_type": "documentation",
                "chunk": content,
                "chunk_number": chunk_number,
            }

            repository_chunks.append(chunk)
            chunk_number += 1

            continue

        # ---------------------------------------------------------
        # Python files
        # ---------------------------------------------------------

        if file_name.lower().endswith(".py"):

            try:

                tree = ast.parse(content)

                for node in ast.walk(tree):

                    if isinstance(
                        node,
                        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    ):

                        name = node.name

                        source_code = ast.get_source_segment(
                            content,
                            node
                        )

                        if not source_code:
                            continue

                        if isinstance(
                            node,
                            (ast.FunctionDef, ast.AsyncFunctionDef)
                        ):
                            chunk_type = "function"
                        else:
                            chunk_type = "class"

                        chunk = {
                            "file_path": file_path,
                            "name": name,
                            "chunk_type": chunk_type,
                            "chunk": source_code,
                            "chunk_number": chunk_number,
                        }

                        repository_chunks.append(chunk)

                        chunk_number += 1

            except SyntaxError:

                print(
                    f"Skipping Python file due to syntax error: "
                    f"{file_path}"
                )

            continue

        # ---------------------------------------------------------
        # Other supported text files
        # ---------------------------------------------------------

        if file_name.lower().endswith(
            (
                ".json",
                ".yaml",
                ".yml",
                ".txt",
            )
        ):

            if not content.strip():
                continue

            chunk = {
                "file_path": file_path,
                "name": file_name,
                "chunk_type": "text",
                "chunk": content,
                "chunk_number": chunk_number,
            }

            repository_chunks.append(chunk)

            chunk_number += 1

    return repository_chunks