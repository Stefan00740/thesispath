import os
import tempfile

os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return TestClient(app)


def make_user(client, email, role, name=None):
    client.post("/auth/register", json={"email": email, "password": "secret1", "full_name": name or email,
                                        "role": role})
    r = client.post("/auth/login", data={"username": email, "password": "secret1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def world(client):
    """Руководитель с темой и студент, выбравший её (ещё не подтверждено)."""
    teacher = make_user(client, "t@x", "supervisor", "Teacher")
    student = make_user(client, "s@x", "student", "Student")
    topic = client.post("/topics", json={"title": "Тема диплома", "direction": "IS"}, headers=teacher).json()
    sel = client.post(f"/topics/{topic['id']}/select", headers=student).json()
    return {"teacher": teacher, "student": student, "topic": topic, "thesis_id": sel["thesis_id"]}


@pytest.fixture()
def active(client, world):
    r = client.patch(f"/theses/{world['thesis_id']}/approve", headers=world["teacher"])
    world["milestones"] = r.json()["milestones"]
    return world
