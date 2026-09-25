from pydantic import BaseModel


class RepositoryRequest(BaseModel):
    repo_url: str