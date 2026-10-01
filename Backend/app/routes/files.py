from fastapi import APIRouter, HTTPException

from app.schemas.repository import FileRequest
from app.services.file_advisor import (
    UnknownFileError,
    UnknownRepositoryError,
    build_explanation_prompt,
    build_suggestion_prompt,
    read_file_content,
    resolve_file,
    resolve_repository,
)
from app.services.llm_service import generate_repository_answer


router = APIRouter()


# ==========================================================
# GET /files
# List every analyzed file (from the manifest) so the
# frontend FilePanel can show the repository tree.
# ==========================================================

@router.get("/files")
def list_files(repository_name: str):
    try:
        _, manifest = resolve_repository(repository_name)
    except UnknownRepositoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    files = [
        entry
        for entry in manifest.get("files", [])
        if entry.get("path") != ".repix-manifest.json"
    ]

    return {
        "repository_name": repository_name,
        "file_count": len(files),
        "files": files,
    }


# ==========================================================
# POST /files/explain
# Plain-language explanation of one file.
# ==========================================================

@router.post("/files/explain")
def explain_file(request: FileRequest):
    try:
        target, manifest, entry = resolve_file(
            request.repository_name,
            request.file_path,
        )
    except (UnknownRepositoryError, UnknownFileError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    prompt = build_explanation_prompt(
        repository_name=request.repository_name,
        file_path=entry["path"],
        file_content=read_file_content(target),
        manifest=manifest,
    )

    try:
        explanation = generate_repository_answer(prompt)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate explanation: {str(exc)}",
        )

    return {
        "file_path": entry["path"],
        "explanation": explanation,
    }


# ==========================================================
# POST /files/suggest
# Prioritized improvement suggestions for one file.
# ==========================================================

@router.post("/files/suggest")
def suggest_file_improvements(request: FileRequest):
    try:
        target, manifest, entry = resolve_file(
            request.repository_name,
            request.file_path,
        )
    except (UnknownRepositoryError, UnknownFileError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    prompt = build_suggestion_prompt(
        repository_name=request.repository_name,
        file_path=entry["path"],
        file_content=read_file_content(target),
        manifest=manifest,
    )

    try:
        suggestions = generate_repository_answer(prompt)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate suggestions: {str(exc)}",
        )

    return {
        "file_path": entry["path"],
        "suggestions": suggestions,
    }
