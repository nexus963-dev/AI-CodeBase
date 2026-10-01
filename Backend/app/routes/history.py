from typing import Optional

from fastapi import APIRouter, HTTPException

from app.services.commit_history_service import (
    CommitHistoryError,
    get_commit_history,
)
from app.services.file_advisor import UnknownRepositoryError


router = APIRouter()


# ==========================================================
# GET /repository/commits
#
# Phase 4a: the full commit flow of a repository, taken from
# GitHub (the local clones are shallow). Optional `path`
# returns only the commits that touched that file — the
# building block for per-file history in Phase 4b.
# ==========================================================

@router.get("/repository/commits")
def list_commits(
    repository_name: str,
    path: Optional[str] = None,
    limit: int = 30,
):
    try:
        return get_commit_history(
            repository_name,
            path=path,
            limit=limit,
        )
    except UnknownRepositoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CommitHistoryError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 502),
            detail=str(exc),
        )
