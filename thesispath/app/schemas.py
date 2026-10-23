from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

EMAIL = r"^[^@\s]+@[^@\s]+$"


class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL, examples=["student@demo"])
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=2)
    role: Literal["student", "supervisor"] = "student"


class TopicIn(BaseModel):
    title: str = Field(min_length=3)
    description: str = ""
    direction: str = ""
    supervisor_id: int | None = None  # только для admin


class MilestoneIn(BaseModel):
    title: str = Field(min_length=2)
    deadline: date


class StatusIn(BaseModel):
    status: Literal["in_progress", "review", "revision", "accepted"]


class CommentIn(BaseModel):
    text: str = Field(min_length=1)
    verdict: Literal["comment", "needs_fix", "accepted"] = "comment"


class ChecklistIn(BaseModel):
    done: bool


class ProposeIn(BaseModel):
    title: str = Field(min_length=3)
    description: str = ""
    direction: str = ""
    supervisor_id: int


class TopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3)
    description: str | None = None
    direction: str | None = None


class RejectIn(BaseModel):
    reason: str = Field(min_length=3)


class NoteIn(BaseModel):
    note: str = Field(max_length=2000)


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=2)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)
