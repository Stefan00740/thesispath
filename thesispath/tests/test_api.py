from .conftest import make_user


def test_register_and_login(client):
    r = client.post("/auth/register", json={"email": "a@x", "password": "secret1", "full_name": "Anna"})
    assert r.status_code == 201
    r = client.post("/auth/login", data={"username": "a@x", "password": "secret1"})
    assert r.status_code == 200 and "access_token" in r.json()


def test_duplicate_email_and_bad_password(client):
    body = {"email": "a@x", "password": "secret1", "full_name": "Anna"}
    client.post("/auth/register", json=body)
    assert client.post("/auth/register", json=body).status_code == 409
    assert client.post("/auth/login", data={"username": "a@x", "password": "wrong"}).status_code == 401


def test_no_token_is_401(client):
    assert client.get("/topics").status_code == 401


def test_student_cannot_create_topic(client):
    student = make_user(client, "s@x", "student")
    assert client.post("/topics", json={"title": "Тема"}, headers=student).status_code == 403


def test_select_then_approve_builds_roadmap(client, world):
    r = client.patch(f"/theses/{world['thesis_id']}/approve", headers=world["teacher"])
    assert r.status_code == 200
    data = r.json()
    assert len(data["milestones"]) == 8 and len(data["checklist"]) == 5
    assert data["next_step"]["title"] == "Тема и план"


def test_taken_topic_cannot_be_selected(client, world):
    other = make_user(client, "s2@x", "student")
    r = client.post(f"/topics/{world['topic']['id']}/select", headers=other)
    assert r.status_code == 409


def test_student_cannot_see_foreign_thesis(client, world):
    other = make_user(client, "s2@x", "student")
    assert client.get(f"/theses/{world['thesis_id']}", headers=other).status_code == 403


def test_upload_versions_increment_and_move_to_review(client, active):
    mid = active["milestones"][0]["id"]
    files = {"file": ("plan.docx", b"v1")}
    r1 = client.post(f"/milestones/{mid}/versions", files=files, headers=active["student"])
    assert r1.status_code == 201 and r1.json()["version_no"] == 1
    assert r1.json()["milestone_status"] == "review"
    r2 = client.post(f"/milestones/{mid}/versions", files={"file": ("plan.docx", b"v2")},
                     headers=active["student"])
    assert r2.json()["version_no"] == 2


def test_supervisor_accepts_and_readiness_grows(client, active):
    mid = active["milestones"][0]["id"]
    v = client.post(f"/milestones/{mid}/versions", files={"file": ("a.docx", b"x")},
                    headers=active["student"]).json()
    before = client.get(f"/theses/{active['thesis_id']}/readiness", headers=active["student"]).json()["index"]
    r = client.post(f"/versions/{v['id']}/comments", json={"text": "Отлично", "verdict": "accepted"},
                    headers=active["teacher"])
    assert r.json()["milestone_status"] == "accepted"
    after = client.get(f"/theses/{active['thesis_id']}/readiness", headers=active["student"]).json()["index"]
    assert after > before


def test_student_cannot_give_verdict(client, active):
    mid = active["milestones"][0]["id"]
    v = client.post(f"/milestones/{mid}/versions", files={"file": ("a.docx", b"x")},
                    headers=active["student"]).json()
    r = client.post(f"/versions/{v['id']}/comments", json={"text": "ok", "verdict": "accepted"},
                    headers=active["student"])
    assert r.status_code == 403


def test_needs_fix_moves_to_revision(client, active):
    mid = active["milestones"][0]["id"]
    v = client.post(f"/milestones/{mid}/versions", files={"file": ("a.docx", b"x")},
                    headers=active["student"]).json()
    r = client.post(f"/versions/{v['id']}/comments", json={"text": "Поправьте", "verdict": "needs_fix"},
                    headers=active["teacher"])
    assert r.json()["milestone_status"] == "revision"


def test_invalid_status_transition_is_409(client, active):
    mid = active["milestones"][0]["id"]
    r = client.patch(f"/milestones/{mid}/status", json={"status": "review"}, headers=active["student"])
    assert r.status_code == 409


def test_supervisor_sees_only_own_students(client, active):
    other_teacher = make_user(client, "t2@x", "supervisor")
    assert client.get("/theses", headers=other_teacher).json() == []
    assert len(client.get("/theses", headers=active["teacher"]).json()) == 1


def test_defense_ready_requires_threshold(client, active):
    r = client.patch(f"/theses/{active['thesis_id']}/defense-ready", headers=active["teacher"])
    assert r.status_code == 409


def test_topic_filters(client, world):
    teacher = world["teacher"]
    client.post("/topics", json={"title": "Другая тема", "direction": "ML"}, headers=teacher)
    r = client.get("/topics", params={"direction": "ML"}, headers=teacher)
    assert [t["direction"] for t in r.json()] == ["ML"]
    assert len(client.get("/topics", params={"status": "free"}, headers=teacher).json()) == 1


def test_detail_has_forecast_and_badges(client, active):
    r = client.get("/theses/me", headers=active["student"]).json()
    assert "forecast" in r and r["badges"] == []


def test_seed_demo_creates_lagging_student(client):
    from app.seed import seed_demo
    seed_demo()
    token = client.post("/auth/login", data={"username": "teacher@demo", "password": "demo1234"}).json()
    h = {"Authorization": f"Bearer {token['access_token']}"}
    theses = client.get("/theses", headers=h).json()
    assert token["user"]["full_name"] == "Руководитель"
    assert len(theses) == 1 and theses[0]["light"] == "red"
    detail = client.get(f"/theses/{theses[0]['id']}", headers=h).json()
    assert detail["forecast"]["on_track"] is False
