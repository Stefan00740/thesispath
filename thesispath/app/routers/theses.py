import html
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db
from ..deps import check_access, current_user, get_thesis, require_reviewer, require_roles

router = APIRouter(tags=["Дипломы"])


def milestone_out(m: models.Milestone, today: date | None = None) -> dict:
    return {"id": m.id, "title": m.title, "position": m.position, "deadline": m.deadline.isoformat(),
            "status": m.status, "light": services.traffic_light(m.status, m.deadline, today),
            "versions_count": len(m.versions), "note": m.note or ""}


def summary(t: models.Thesis) -> dict:
    r = services.thesis_readiness(t)
    return {"id": t.id, "student": t.student.full_name, "student_id": t.student_id,
            "topic": t.topic.title, "supervisor": t.supervisor.full_name, "status": t.status,
            "readiness": r["index"], "ready_for_defense": r["ready_for_defense"],
            "light": services.thesis_light(t),
            "waiting_review": sum(m.status == "review" for m in t.milestones)}


def detail(t: models.Thesis) -> dict:
    data = summary(t)
    r = services.thesis_readiness(t)
    nxt = next((m for m in t.milestones if m.status != "accepted"), None)
    data.update(services.thesis_insights(t))
    data.update({
        "readiness_breakdown": r["breakdown"],
        "next_step": milestone_out(nxt) if nxt else None,
        "milestones": [milestone_out(m) for m in t.milestones],
        "checklist": [{"id": c.id, "item": c.item, "done": c.done} for c in t.checklist],
    })
    return data


@router.get("/theses")
def list_theses(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    q = select(models.Thesis).order_by(models.Thesis.id)
    if user.role == "student":
        q = q.where(models.Thesis.student_id == user.id)
    elif user.role == "supervisor":
        q = q.where(models.Thesis.supervisor_id == user.id)
    return [summary(t) for t in db.scalars(q)]


@router.get("/theses/me")
def my_thesis(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    t = db.scalar(select(models.Thesis).where(models.Thesis.student_id == user.id))
    if not t:
        raise HTTPException(404, "У вас пока нет диплома: выберите тему")
    return detail(t)


@router.get("/theses/{thesis_id}")
def thesis_detail(thesis_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    check_access(t, user)
    return detail(t)


@router.patch("/theses/{thesis_id}/approve")
def approve(thesis_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    require_reviewer(t, user)
    if t.status != "pending":
        raise HTTPException(409, "Закрепление уже подтверждено")
    t.status = "active"
    db.flush()
    services.build_roadmap(db, t)
    services.log_event(db, t.id, user.id, "approved",
                       "Руководитель подтвердил закрепление, создана карта из 8 этапов")
    services.notify(db, t.student_id, "Руководитель подтвердил вашу тему. Карта диплома создана: начинайте с первого этапа", t.id)
    db.commit()
    db.refresh(t)
    return detail(t)


@router.patch("/theses/{thesis_id}/defense-ready")
def confirm_defense(thesis_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    require_reviewer(t, user)
    if services.thesis_readiness(t)["index"] < services.READY_THRESHOLD:
        raise HTTPException(409, f"Индекс готовности ниже {services.READY_THRESHOLD}%")
    t.supervisor_confirmed = True
    services.log_event(db, t.id, user.id, "defense_ready", "Студент допущен к защите 🎓")
    services.notify(db, t.student_id, "Вы допущены к защите 🎓", t.id)
    db.commit()
    return summary(t)


@router.get("/theses/{thesis_id}/milestones")
def list_milestones(thesis_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    check_access(t, user)
    return [milestone_out(m) for m in t.milestones]


@router.post("/theses/{thesis_id}/milestones", status_code=201)
def add_milestone(thesis_id: int, body: schemas.MilestoneIn, db: Session = Depends(get_db),
                  user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    require_reviewer(t, user)
    if t.status != "active":
        raise HTTPException(409, "Сначала подтвердите закрепление студента")
    position = max((m.position for m in t.milestones), default=0) + 1
    m = models.Milestone(thesis_id=t.id, title=body.title, deadline=body.deadline, position=position)
    db.add(m)
    services.log_event(db, t.id, user.id, "milestone_added",
                       f"Добавлен этап «{body.title}» (дедлайн {body.deadline})")
    services.notify(db, t.student_id, f"Новый этап «{body.title}», дедлайн {body.deadline}", t.id)
    db.commit()
    return milestone_out(m)


@router.get("/theses/{thesis_id}/readiness")
def readiness(thesis_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    check_access(t, user)
    return {**services.thesis_readiness(t), "light": services.thesis_light(t),
            "threshold": services.READY_THRESHOLD, "supervisor_confirmed": t.supervisor_confirmed}


@router.get("/theses/{thesis_id}/events")
def events(thesis_id: int, limit: int = 30, db: Session = Depends(get_db),
           user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    check_access(t, user)
    q = (select(models.Event).where(models.Event.thesis_id == t.id)
         .order_by(models.Event.id.desc()).limit(min(max(limit, 1), 100)))
    return [{"id": e.id, "kind": e.kind, "text": e.text, "actor": e.actor.full_name,
             "at": e.created_at.strftime("%d.%m %H:%M")} for e in db.scalars(q)]


@router.get("/theses/{thesis_id}/report", response_class=HTMLResponse)
def report(thesis_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    """Страница отчёта для печати / сохранения в PDF."""
    t = get_thesis(db, thesis_id)
    check_access(t, user)
    d = detail(t)
    e = html.escape
    rows = "".join(
        f"<tr><td>{m['position']}</td><td>{e(m['title'])}</td><td>{e(services.STATUS_LABELS[m['status']])}</td>"
        f"<td>{m['deadline']}</td><td>{m['versions_count']}</td></tr>" for m in d["milestones"])
    checks = "".join(f"<li>{'☑' if c['done'] else '☐'} {e(c['item'])}</li>" for c in d["checklist"])
    badges = ", ".join(f"{b['emoji']} {e(b['title'])}" for b in d["badges"]) or "—"
    fc = d["forecast"]
    forecast = "—" if not fc else (f"запас {fc['delta']} дн." if fc["on_track"] else f"отставание {-fc['delta']} дн.")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Отчёт: {e(d['student'])}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:800px;margin:30px auto;padding:0 16px;color:#1d2433}}
table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ccd;padding:6px 8px;text-align:left}}
h1{{margin-bottom:0}}.big{{font-size:40px;font-weight:700}}@media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()">🖨 Печать / сохранить в PDF</button>
<h1>Карта выполнения дипломной работы</h1>
<p><b>Студент:</b> {e(d['student'])}<br><b>Руководитель:</b> {e(d['supervisor'])}<br><b>Тема:</b> {e(d['topic'])}<br>
<b>Дата отчёта:</b> {date.today().isoformat()}</p>
<p class="big">{d['readiness']}% <span style="font-size:16px;font-weight:400">готовности к защите
{'— допущен ✅' if d['ready_for_defense'] else ''}</span></p>
<p>Прогноз по текущему темпу: {forecast}. Достижения: {badges}</p>
<table><tr><th>№</th><th>Этап</th><th>Статус</th><th>Дедлайн</th><th>Версий</th></tr>{rows}</table>
<h3>Чек-лист допуска</h3><ul style="list-style:none;padding:0">{checks}</ul></body></html>"""


@router.patch("/theses/{thesis_id}/reject")
def reject(thesis_id: int, body: schemas.RejectIn, db: Session = Depends(get_db),
           user: models.User = Depends(current_user)):
    t = get_thesis(db, thesis_id)
    require_reviewer(t, user)
    if t.status != "pending":
        raise HTTPException(409, "Отклонить можно только заявку, ожидающую подтверждения")
    title, student_id = t.topic.title, t.student_id
    services.release_request(db, t)
    services.notify(db, student_id, f"Заявка на тему «{title}» отклонена: {body.reason}")
    db.commit()
    return {"rejected": True}


@router.delete("/theses/me/request")
def withdraw(db: Session = Depends(get_db), user: models.User = Depends(require_roles("student"))):
    t = db.scalar(select(models.Thesis).where(models.Thesis.student_id == user.id))
    if not t:
        raise HTTPException(404, "Заявки нет")
    if t.status != "pending":
        raise HTTPException(409, "Заявка уже подтверждена: отозвать её нельзя")
    title, supervisor_id = t.topic.title, t.supervisor_id
    services.release_request(db, t)
    services.notify(db, supervisor_id, f"{user.full_name} отозвал(а) заявку на тему «{title}»")
    db.commit()
    return {"withdrawn": True}
