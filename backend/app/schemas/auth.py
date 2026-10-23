from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserRegister(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: Optional[str] = "consultant"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool
    role: str = "consultant"
    custom_instructions_about_user: Optional[str] = None
    custom_instructions_how_to_respond: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CustomInstructionsUpdate(BaseModel):
    about_user: Optional[str] = Field(None, max_length=2000)
    how_to_respond: Optional[str] = Field(None, max_length=2000)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
