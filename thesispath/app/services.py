"""Бизнес-логика: чистые функции (легко тестируются) и работа с ORM-объектами."""
from datetime import date, timedelta

from sqlalchemy import delete

from . import models

DEFAULT_MILESTONES = [
    "Тема и план", "Введение", "Глава 1", "Глава 2",
    "Глава 3", "Оформление по ГОСТ", "Предзащита", "Защита",
]
DEFAULT_CHECKLIST = [
    "Антиплагиат пройден", "Оформление по ГОСТ", "Отзыв руководителя",
    "Презентация готова", "Допуск к защите",
]
STEP_DAYS = 14

TRANSITIONS = {
    "not_started": {"in_progress"},
    "in_progress": {"review"},
    "review": {"revision", "accepted"},
    "revision": {"review"},
    "accepted": set(),
}
STUDENT_TARGETS = {"in_progress", "review"}
REVIEWER_TARGETS = {"revision", "accepted"}
READY_THRESHOLD = 90


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def traffic_light(status: str, deadline: date, today: date | None = None) -> str:
    today = today or date.today()
    if status == "accepted":
        return "green"
    days_left = (deadline - today).days
    if days_left < 0:
        return "red"
    if days_left <= 3:
        return "yellow"
    return "green"


def compute_readiness(accepted: int, total: int, latest_approved: bool,
                      checklist_done: int, checklist_total: int, overdue: int) -> dict:
    milestones_pts = 40 * accepted / total if total else 0
    approved_pts = 20 if latest_approved else 0
    checklist_pts = 20 * checklist_done / checklist_total if checklist_total else 0
    discipline_pts = max(0, 20 - 10 * overdue) if total else 0
    index = round(milestones_pts + approved_pts + checklist_pts + discipline_pts)
    return {
        "index": index,
        "breakdown": {
            "milestones": round(milestones_pts),
            "latest_version_approved": approved_pts,
            "checklist": round(checklist_pts),
            "discipline": discipline_pts,
        },
    }


def thesis_readiness(thesis: models.Thesis, today: date | None = None) -> dict:
    today = today or date.today()
    ms = thesis.milestones
    accepted = sum(m.status == "accepted" for m in ms)
    overdue = sum(m.status != "accepted" and m.deadline < today for m in ms)
    versions = [v for m in ms for v in m.versions]
    latest_ok = False
    if versions:
        last = max(versions, key=lambda v: v.id)
        decisions = [c for c in last.comments if c.verdict != "comment"]
        latest_ok = bool(decisions) and decisions[-1].verdict == "accepted"
    done = sum(i.done for i in thesis.checklist)
    result = compute_readiness(accepted, len(ms), latest_ok, done, len(thesis.checklist), overdue)
    result["ready_for_defense"] = result["index"] >= READY_THRESHOLD and thesis.supervisor_confirmed
    return result


def thesis_light(thesis: models.Thesis, today: date | None = None) -> str:
    if thesis.status != "active":
        return "gray"
    lights = {traffic_light(m.status, m.deadline, today) for m in thesis.milestones}
    return "red" if "red" in lights else "yellow" if "yellow" in lights else "green"


def build_roadmap(db, thesis: models.Thesis, start: date | None = None) -> None:
    start = start or date.today()
    for i, title in enumerate(DEFAULT_MILESTONES, start=1):
        db.add(models.Milestone(thesis_id=thesis.id, title=title, position=i,
                                deadline=start + timedelta(days=STEP_DAYS * i), status="not_started"))
    for item in DEFAULT_CHECKLIST:
        db.add(models.ChecklistItem(thesis_id=thesis.id, item=item, done=False))


def forecast(accepted: int, total: int, elapsed_days: int, planned_days_left: int) -> dict | None:
    """Прогноз по текущему темпу: сколько дней нужно на остаток и успеваем ли к последнему дедлайну."""
    if accepted == 0 or total == 0 or accepted >= total:
        return None
    pace = max(elapsed_days, 1) / accepted
    needed = round(pace * (total - accepted))
    return {"days_needed": needed, "days_planned": planned_days_left,
            "delta": planned_days_left - needed, "on_track": needed <= planned_days_left}


def badges(accepted_titles: set, accepted: int, total: int, overdue: int, ready: bool) -> list:
    out = []
    if "Глава 1" in accepted_titles:
        out.append({"code": "first_chapter", "emoji": "📘", "title": "Первая глава принята"})
    if accepted >= 2 and overdue == 0:
        out.append({"code": "on_time", "emoji": "⏱", "title": "Все дедлайны в срок"})
    if total and accepted * 2 >= total:
        out.append({"code": "halfway", "emoji": "🚀", "title": "Половина пути пройдена"})
    if ready:
        out.append({"code": "ready", "emoji": "🎓", "title": "Готов к защите"})
    return out


def thesis_insights(thesis: models.Thesis, today: date | None = None) -> dict:
    today = today or date.today()
    ms = thesis.milestones
    accepted = [m for m in ms if m.status == "accepted"]
    overdue = sum(m.status != "accepted" and m.deadline < today for m in ms)
    fc = None
    if ms and thesis.status == "active":
        created = thesis.created_at.date() if thesis.created_at else today
        planned_left = (max(m.deadline for m in ms) - today).days
        fc = forecast(len(accepted), len(ms), (today - created).days, planned_left)
    ready = thesis_readiness(thesis, today)["ready_for_defense"]
    return {"forecast": fc,
            "badges": badges({m.title for m in accepted}, len(accepted), len(ms), overdue, ready)}


STATUS_LABELS = {"not_started": "не начат", "in_progress": "в работе", "review": "на проверке",
                 "revision": "доработка", "accepted": "принят"}


def log_event(db, thesis_id: int, actor_id: int, kind: str, text: str) -> None:
    db.add(models.Event(thesis_id=thesis_id, actor_id=actor_id, kind=kind, text=text[:500]))


def notify(db, user_id: int, text: str, thesis_id: int | None = None) -> None:
    db.add(models.Notification(user_id=user_id, text=text[:500], thesis_id=thesis_id))


def release_request(db, thesis: models.Thesis) -> None:
    """Снять заявку (отзыв студентом или отказ руководителя): тема освобождается,
    а тема, предложенная самим студентом, удаляется."""
    topic = thesis.topic
    db.execute(delete(models.Event).where(models.Event.thesis_id == thesis.id))
    db.delete(thesis)
    db.flush()
    if topic.proposed_by_id:
        db.delete(topic)
    else:
        topic.status = "free"
