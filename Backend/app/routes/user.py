from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.security import hash_password,verify_password
from app.auth import create_access_token, get_current_user

from app.schemas.repository import RepositoryRequest
from app.services.github_service import (clone_repository,get_repository_metadata,)
from app.services.repository_reader import read_repository
from app.services.chunking_service import create_chunks
from app.services.embedding_service import generate_embeddings
from app.services.vector_database import get_or_create_repository_collection, store_repository_embeddings
from app.services.repository_manifest import build_repository_manifest

router = APIRouter()

@router.post("/users", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):

    existing_email = db.query(User).filter(User.email == user.email).first()
    existing_github = db.query(User).filter(User.github_id == user.github_id).first()

    errors = []

    if existing_email:
        errors.append("Email already registered.")

    if existing_github:
        errors.append("GitHub ID already registered.")

    if errors:
        raise HTTPException(
            status_code=400,
            detail=errors
        )

    hashed_password = hash_password(user.password)

    db_user = User(
        username=user.username,
        email=user.email,
        github_id=user.github_id,
        hashed_password=hashed_password
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    db_user = db.query(User).filter(
        User.email == form_data.username
    ).first()

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not verify_password(
        form_data.password,
        db_user.hashed_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    access_token = create_access_token(
        data={"sub": db_user.email}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: User = Depends(get_current_user)
):
    return current_user

@router.post("/analyze-repository")
def analyze_repository(repository: RepositoryRequest):

    repo_path = clone_repository(
        repository.repo_url
    )

    repository_data = read_repository(
        repo_path
    )

    build_repository_manifest(repo_path)

    chunk_data = create_chunks(
        repository_data
    )

    embedded_chunks = generate_embeddings(
        chunk_data
    )

    collection = get_or_create_repository_collection(
        repo_path.name
    )

    store_repository_embeddings(
        collection,
        embedded_chunks
    )

    # Get repository metadata
    metadata = get_repository_metadata(
        repo_path
    )
    return {

        "repository_name": repo_path.name,

        "chunk_count": len(chunk_data),

        "language": metadata["language"],

        "branch": metadata["branch"],

        "license": metadata["license"],

    }