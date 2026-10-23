from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # student | supervisor | admin


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    direction: Mapped[str] = mapped_column(String(100), default="")
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="free")  # free | taken
    proposed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # тема предложена студентом
    supervisor: Mapped[User] = relationship(foreign_keys=[supervisor_id])


class Thesis(Base):
    __tablename__ = "theses"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), unique=True)
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | active
    supervisor_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    student: Mapped[User] = relationship(foreign_keys=[student_id])
    supervisor: Mapped[User] = relationship(foreign_keys=[supervisor_id])
    topic: Mapped[Topic] = relationship()
    milestones: Mapped[list["Milestone"]] = relationship(
        order_by="Milestone.position", cascade="all, delete-orphan"
    )
    checklist: Mapped[list["ChecklistItem"]] = relationship(
        order_by="ChecklistItem.id", cascade="all, delete-orphan"
    )


class Milestone(Base):
    __tablename__ = "milestones"
    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id"))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column()
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")  # заметка студента: что сделано
    versions: Mapped[list["FileVersion"]] = relationship(
        order_by="FileVersion.id", cascade="all, delete-orphan"
    )


class FileVersion(Base):
    __tablename__ = "file_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    milestone_id: Mapped[int] = mapped_column(ForeignKey("milestones.id"))
    version_no: Mapped[int] = mapped_column()
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    comments: Mapped[list["Comment"]] = relationship(
        order_by="Comment.id", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_version_id: Mapped[int] = mapped_column(ForeignKey("file_versions.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(20), default="comment")  # comment | needs_fix | accepted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    author: Mapped[User] = relationship()


class ChecklistItem(Base):
    __tablename__ = "defense_checklist"
    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id"))
    item: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    thesis_id: Mapped[int | None] = mapped_column(nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
