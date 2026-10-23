from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, services
from ..database import get_db
from ..deps import current_user, require_roles

router = APIRouter(tags=["Статистика"])


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: models.User = Depends(require_roles("supervisor", "admin"))):
    """Сводка: руководитель видит своих студентов, админ — всех."""
    tq = select(models.Thesis)
    topq = select(models.Topic.status, func.count()).group_by(models.Topic.status)
    if user.role == "supervisor":
        tq = tq.where(models.Thesis.supervisor_id == user.id)
        topq = topq.where(models.Topic.supervisor_id == user.id)
    theses = list(db.scalars(tq))
    active = [t for t in theses if t.status == "active"]
    today = date.today()
    lights = {"green": 0, "yellow": 0, "red": 0}
    readiness = []
    for t in active:
        lights[services.thesis_light(t, today)] += 1
        readiness.append(services.thesis_readiness(t, today))
    topics = dict(db.execute(topq).all())
    return {
        "theses_total": len(theses),
        "pending": len(theses) - len(active),
        "active": len(active),
        "lights": lights,
        "avg_readiness": round(sum(r["index"] for r in readiness) / len(readiness)) if readiness else 0,
        "ready_for_defense": sum(r["ready_for_defense"] for r in readiness),
        "waiting_review": sum(m.status == "review" for t in active for m in t.milestones),
        "overdue_milestones": sum(m.status != "accepted" and m.deadline < today
                                  for t in active for m in t.milestones),
        "topics": {"free": topics.get("free", 0), "taken": topics.get("taken", 0)},
    }


@router.get("/deadlines")
def deadlines(limit: int = 8, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    """Ближайшие непринятые этапы: у студента свои, у руководителя по всем его студентам."""
    q = select(models.Thesis).where(models.Thesis.status == "active")
    if user.role == "student":
        q = q.where(models.Thesis.student_id == user.id)
    elif user.role == "supervisor":
        q = q.where(models.Thesis.supervisor_id == user.id)
    today = date.today()
    items = [{"thesis_id": t.id, "student": t.student.full_name, "title": m.title,
              "deadline": m.deadline.isoformat(), "days_left": (m.deadline - today).days,
              "status": m.status, "light": services.traffic_light(m.status, m.deadline, today)}
             for t in db.scalars(q) for m in t.milestones if m.status != "accepted"]
    items.sort(key=lambda i: i["deadline"])
    return items[:min(max(limit, 1), 50)]
