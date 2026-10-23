import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db
from ..deps import check_access, current_user, is_reviewer, require_reviewer

router = APIRouter(tags=["Этапы, файлы, комментарии"])
MAX_FILE_BYTES = 20 * 1024 * 1024


def _milestone(db: Session, milestone_id: int) -> models.Milestone:
    m = db.get(models.Milestone, milestone_id)
    if not m:
        raise HTTPException(404, "Этап не найден")
    return m


def _thesis_of(db: Session, m: models.Milestone) -> models.Thesis:
    return db.get(models.Thesis, m.thesis_id)


def version_out(v: models.FileVersion) -> dict:
    return {"id": v.id, "version_no": v.version_no, "filename": v.filename,
            "uploaded_at": v.uploaded_at.isoformat(),
            "comments": [{"id": c.id, "author": c.author.full_name, "text": c.text,
                          "verdict": c.verdict, "created_at": c.created_at.isoformat()}
                         for c in v.comments]}


@router.patch("/milestones/{milestone_id}/status")
def change_status(milestone_id: int, body: schemas.StatusIn, db: Session = Depends(get_db),
                  user: models.User = Depends(current_user)):
    m = _milestone(db, milestone_id)
    t = _thesis_of(db, m)
    check_access(t, user)
    if body.status in services.REVIEWER_TARGETS:
        require_reviewer(t, user)
    elif user.id != t.student_id and user.role != "admin":
        raise HTTPException(403, "Этот статус может поставить только студент")
    if not services.can_transition(m.status, body.status):
        raise HTTPException(409, f"Переход {m.status} → {body.status} недопустим")
    old = m.status
    m.status = body.status
    services.log_event(db, t.id, user.id, "status",
                       f"Этап «{m.title}»: {services.STATUS_LABELS[old]} → {services.STATUS_LABELS[m.status]}")
    db.commit()
    return {"id": m.id, "status": m.status}


@router.post("/milestones/{milestone_id}/versions", status_code=201)
async def upload_version(milestone_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                         user: models.User = Depends(current_user)):
    m = _milestone(db, milestone_id)
    t = _thesis_of(db, m)
    if user.id != t.student_id and user.role != "admin":
        raise HTTPException(403, "Версии загружает студент-владелец диплома")
    if m.status == "accepted":
        raise HTTPException(409, "Этап уже принят: загрузка закрыта")
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Файл больше 20 МБ")
    version_no = len(m.versions) + 1
    safe_name = Path(file.filename or "file").name
    folder = Path(os.getenv("UPLOAD_DIR", "uploads")) / f"thesis_{t.id}" / f"milestone_{m.id}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"v{version_no}_{safe_name}"
    path.write_bytes(content)
    v = models.FileVersion(milestone_id=m.id, version_no=version_no, filename=safe_name, file_path=str(path))
    db.add(v)
    if m.status in ("not_started", "in_progress", "revision"):
        m.status = "review"
    services.log_event(db, t.id, user.id, "version",
                       f"Загружена версия v{version_no} этапа «{m.title}»")
    services.notify(db, t.supervisor_id, f"{user.full_name}: загружена версия v{version_no} этапа «{m.title}»", t.id)
    db.commit()
    return {**version_out(v), "milestone_status": m.status}


@router.get("/milestones/{milestone_id}/versions")
def list_versions(milestone_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    m = _milestone(db, milestone_id)
    check_access(_thesis_of(db, m), user)
    return [version_out(v) for v in m.versions]


@router.get("/versions/{version_id}/download")
def download(version_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    v = db.get(models.FileVersion, version_id)
    if not v:
        raise HTTPException(404, "Версия не найдена")
    check_access(_thesis_of(db, _milestone(db, v.milestone_id)), user)
    return FileResponse(v.file_path, filename=v.filename)


@router.post("/versions/{version_id}/comments", status_code=201)
def add_comment(version_id: int, body: schemas.CommentIn, db: Session = Depends(get_db),
                user: models.User = Depends(current_user)):
    v = db.get(models.FileVersion, version_id)
    if not v:
        raise HTTPException(404, "Версия не найдена")
    m = _milestone(db, v.milestone_id)
    t = _thesis_of(db, m)
    check_access(t, user)
    if body.verdict != "comment":
        if not is_reviewer(t, user):
            raise HTTPException(403, "Вердикты выносит только руководитель")
        if m.status != "review":
            raise HTTPException(409, "Вердикт можно вынести только для этапа «на проверке»")
        m.status = "accepted" if body.verdict == "accepted" else "revision"
    c = models.Comment(file_version_id=v.id, author_id=user.id, text=body.text, verdict=body.verdict)
    db.add(c)
    action = {"accepted": "принял(а) этап", "needs_fix": "вернул(а) на доработку этап",
              "comment": "прокомментировал(а) этап"}[body.verdict]
    services.log_event(db, t.id, user.id, "comment", f"{user.full_name} {action} «{m.title}»")
    target = t.student_id if is_reviewer(t, user) else t.supervisor_id
    services.notify(db, target, f"{user.full_name} {action} «{m.title}»", t.id)
    db.commit()
    return {"id": c.id, "verdict": c.verdict, "milestone_status": m.status}


@router.patch("/checklist/{item_id}")
def toggle_checklist(item_id: int, body: schemas.ChecklistIn, db: Session = Depends(get_db),
                     user: models.User = Depends(current_user)):
    item = db.get(models.ChecklistItem, item_id)
    if not item:
        raise HTTPException(404, "Пункт не найден")
    thesis = db.get(models.Thesis, item.thesis_id)
    require_reviewer(thesis, user)
    item.done = body.done
    services.log_event(db, thesis.id, user.id, "checklist",
                       f"Чек-лист: «{item.item}» — {'выполнено' if body.done else 'снято'}")
    db.commit()
    return {"id": item.id, "item": item.item, "done": item.done}


@router.patch("/milestones/{milestone_id}/note")
def save_note(milestone_id: int, body: schemas.NoteIn, db: Session = Depends(get_db),
              user: models.User = Depends(current_user)):
    m = _milestone(db, milestone_id)
    t = _thesis_of(db, m)
    if user.id != t.student_id and user.role != "admin":
        raise HTTPException(403, "Заметки пишет студент-владелец диплома")
    m.note = body.note
    db.commit()
    return {"id": m.id, "note": m.note}
