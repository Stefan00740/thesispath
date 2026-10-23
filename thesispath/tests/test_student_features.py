from .conftest import make_user


def uid(client, headers):
    return client.get("/auth/me", headers=headers).json()["id"]


def notes(client, headers):
    return client.get("/notifications", headers=headers).json()


def test_propose_own_topic_and_approve(client):
    teacher = make_user(client, "t@x", "supervisor", "Teacher")
    student = make_user(client, "s@x", "student", "Student")
    body = {"title": "Моя собственная тема", "direction": "AI", "supervisor_id": uid(client, teacher)}
    r = client.post("/topics/propose", json=body, headers=student)
    assert r.status_code == 201
    pending = client.get("/theses", headers=teacher).json()
    assert len(pending) == 1 and pending[0]["status"] == "pending"
    assert client.patch(f"/theses/{r.json()['thesis_id']}/approve", headers=teacher).status_code == 200
    assert client.get("/theses/me", headers=student).json()["topic"] == "Моя собственная тема"


def test_propose_requires_real_supervisor_and_single_thesis(client, world):
    student2 = make_user(client, "s2@x", "student")
    bad = client.post("/topics/propose", json={"title": "Тема тема", "supervisor_id": 9999}, headers=student2)
    assert bad.status_code == 400
    again = client.post("/topics/propose", headers=world["student"],
                        json={"title": "Ещё тема", "supervisor_id": uid(client, world["teacher"])})
    assert again.status_code == 409


def test_reject_proposed_topic_notifies_student_and_removes_topic(client):
    teacher = make_user(client, "t@x", "supervisor")
    student = make_user(client, "s@x", "student")
    r = client.post("/topics/propose", headers=student,
                    json={"title": "Слишком широкая тема", "supervisor_id": uid(client, teacher)})
    res = client.patch(f"/theses/{r.json()['thesis_id']}/reject", json={"reason": "Сузьте тему"}, headers=teacher)
    assert res.status_code == 200
    assert client.get("/theses/me", headers=student).status_code == 404
    assert "Сузьте тему" in notes(client, student)["items"][0]["text"]
    assert client.get("/topics", headers=student).json() == []


def test_reject_regular_topic_frees_it(client, world):
    client.patch(f"/theses/{world['thesis_id']}/reject", json={"reason": "Нет мест"}, headers=world["teacher"])
    topics = client.get("/topics", headers=world["student"]).json()
    assert topics[0]["status"] == "free"
    other = make_user(client, "s2@x", "student")
    assert client.post(f"/topics/{topics[0]['id']}/select", headers=other).status_code == 201


def test_reject_active_thesis_is_409_and_student_cannot_reject(client, active):
    assert client.patch(f"/theses/{active['thesis_id']}/reject", json={"reason": "поздно"},
                        headers=active["teacher"]).status_code == 409
    assert client.patch(f"/theses/{active['thesis_id']}/reject", json={"reason": "хочу"},
                        headers=active["student"]).status_code == 403


def test_withdraw_pending_request_only(client, world):
    assert client.delete("/theses/me/request", headers=world["student"]).status_code == 200
    assert client.get("/theses/me", headers=world["student"]).status_code == 404
    # тема снова свободна, можно выбрать заново
    assert client.post(f"/topics/{world['topic']['id']}/select", headers=world["student"]).status_code == 201
    client.patch(f"/theses/{client.get('/theses/me', headers=world['student']).json()['id']}/approve",
                 headers=world["teacher"])
    assert client.delete("/theses/me/request", headers=world["student"]).status_code == 409


def test_notifications_flow(client, world):
    assert notes(client, world["teacher"])["unread"] == 1  # заявка студента
    client.post("/notifications/read-all", headers=world["teacher"])
    assert notes(client, world["teacher"])["unread"] == 0
    client.patch(f"/theses/{world['thesis_id']}/approve", headers=world["teacher"])
    assert "подтвердил" in notes(client, world["student"])["items"][0]["text"]


def test_verdict_notifies_student_and_upload_notifies_supervisor(client, active):
    mid = active["milestones"][0]["id"]
    client.post("/notifications/read-all", headers=active["teacher"])
    v = client.post(f"/milestones/{mid}/versions", files={"file": ("a.docx", b"x")}, headers=active["student"]).json()
    assert notes(client, active["teacher"])["unread"] == 1
    client.post(f"/versions/{v['id']}/comments", json={"text": "ok", "verdict": "accepted"}, headers=active["teacher"])
    assert "принял" in notes(client, active["student"])["items"][0]["text"]


def test_milestone_note_only_for_owner(client, active):
    mid = active["milestones"][0]["id"]
    ok = client.patch(f"/milestones/{mid}/note", json={"note": "Собрал источники"}, headers=active["student"])
    assert ok.status_code == 200
    assert client.patch(f"/milestones/{mid}/note", json={"note": "x"}, headers=active["teacher"]).status_code == 403
    seen = client.get("/theses/me", headers=active["student"]).json()["milestones"][0]["note"]
    assert seen == "Собрал источники"


def test_deadlines_sorted_and_scoped(client, active):
    items = client.get("/deadlines", params={"limit": 3}, headers=active["student"]).json()
    assert len(items) == 3
    assert [i["deadline"] for i in items] == sorted(i["deadline"] for i in items)
    stranger = make_user(client, "x@x", "student")
    assert client.get("/deadlines", headers=stranger).json() == []


def test_topic_edit_and_delete_rules(client, world):
    teacher, student = world["teacher"], world["student"]
    free = client.post("/topics", json={"title": "Свободная тема"}, headers=teacher).json()
    upd = client.patch(f"/topics/{free['id']}", json={"title": "Новое название"}, headers=teacher)
    assert upd.json()["title"] == "Новое название"
    assert client.delete(f"/topics/{free['id']}", headers=student).status_code == 403
    assert client.delete(f"/topics/{world['topic']['id']}", headers=teacher).status_code == 409
    assert client.delete(f"/topics/{free['id']}", headers=teacher).status_code == 200
    other = make_user(client, "t2@x", "supervisor")
    assert client.patch(f"/topics/{world['topic']['id']}", json={"title": "Чужая тема"}, headers=other).status_code == 403


def test_profile_update_and_password_change(client):
    h = make_user(client, "u@x", "student", "Old Name")
    assert client.patch("/auth/me", json={"full_name": "New Name"}, headers=h).json()["full_name"] == "New Name"
    assert client.post("/auth/change-password", json={"old_password": "bad", "new_password": "newsecret"},
                       headers=h).status_code == 400
    assert client.post("/auth/change-password", json={"old_password": "secret1", "new_password": "newsecret"},
                       headers=h).status_code == 200
    assert client.post("/auth/login", data={"username": "u@x", "password": "newsecret"}).status_code == 200
    assert client.post("/auth/login", data={"username": "u@x", "password": "secret1"}).status_code == 401


def test_supervisor_list(client, world):
    names = [s["full_name"] for s in client.get("/auth/supervisors", headers=world["student"]).json()]
    assert names == ["Teacher"]
