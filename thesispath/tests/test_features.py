import os
import subprocess
import sys
from pathlib import Path

from .conftest import make_user


def test_event_feed_records_actions(client, active):
    mid = active["milestones"][0]["id"]
    client.post(f"/milestones/{mid}/versions", files={"file": ("a.docx", b"x")}, headers=active["student"])
    r = client.get(f"/theses/{active['thesis_id']}/events", headers=active["student"])
    kinds = [e["kind"] for e in r.json()]
    assert r.status_code == 200
    assert kinds[0] == "version" and "approved" in kinds and "topic_selected" in kinds  # новые сверху


def test_event_feed_is_private(client, world):
    stranger = make_user(client, "x@x", "student")
    assert client.get(f"/theses/{world['thesis_id']}/events", headers=stranger).status_code == 403


def test_stats_for_supervisor_and_forbidden_for_student(client, active):
    s = client.get("/stats", headers=active["teacher"]).json()
    assert s["theses_total"] == 1 and s["active"] == 1 and s["topics"]["taken"] == 1
    assert client.get("/stats", headers=active["student"]).status_code == 403


def test_stats_counts_waiting_review(client, active):
    mid = active["milestones"][0]["id"]
    client.post(f"/milestones/{mid}/versions", files={"file": ("a.docx", b"x")}, headers=active["student"])
    assert client.get("/stats", headers=active["teacher"]).json()["waiting_review"] == 1


def test_report_is_html_and_private(client, active):
    r = client.get(f"/theses/{active['thesis_id']}/report", headers=active["student"])
    assert r.status_code == 200 and "Тема диплома" in r.text and "Этап" in r.text
    stranger = make_user(client, "x@x", "student")
    assert client.get(f"/theses/{active['thesis_id']}/report", headers=stranger).status_code == 403


def test_topic_text_search(client, world):
    t = world["teacher"]
    client.post("/topics", json={"title": "Нейросети в медицине", "direction": "ML"}, headers=t)
    found = client.get("/topics", params={"q": "медиц"}, headers=t).json()
    assert [x["title"] for x in found] == ["Нейросети в медицине"]


def test_checklist_toggle_and_defense_flow(client, active):
    detail = client.get("/theses/me", headers=active["student"]).json()
    item = detail["checklist"][0]["id"]
    assert client.patch(f"/checklist/{item}", json={"done": True}, headers=active["student"]).status_code == 403
    assert client.patch(f"/checklist/{item}", json={"done": True}, headers=active["teacher"]).json()["done"]


def test_add_milestone_by_supervisor_only(client, active):
    body = {"title": "Доп. задание", "deadline": "2030-01-01"}
    url = f"/theses/{active['thesis_id']}/milestones"
    assert client.post(url, json=body, headers=active["student"]).status_code == 403
    assert client.post(url, json=body, headers=active["teacher"]).status_code == 201
    assert len(client.get(url, headers=active["student"]).json()) == 9


def test_migrations_create_schema(tmp_path):
    root = Path(__file__).resolve().parent.parent
    db = tmp_path / "m.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}"}
    res = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    import sqlite3
    tables = {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master")}
    assert {"users", "theses", "milestones", "events", "alembic_version"} <= tables
