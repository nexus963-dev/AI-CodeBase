from pydantic import BaseModel


class RepositoryRequest(BaseModel):
    repo_url: str


class FileRequest(BaseModel):
    repository_name: str
    file_path: str