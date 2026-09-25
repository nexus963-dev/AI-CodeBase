from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel): # validates incoming client data
    username: str
    email: EmailStr
    github_id: str
    password: str

class UserResponse(BaseModel): # controls what data is sent back to the client
    id: int
    username: str
    email: EmailStr
    github_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    email: EmailStr
    password: str