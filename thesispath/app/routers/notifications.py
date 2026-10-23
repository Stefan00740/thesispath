from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import current_user

router = APIRouter(prefix="/notifications", tags=["Уведомления"])


@router.get("")
def list_notifications(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    rows = db.scalars(select(models.Notification).where(models.Notification.user_id == user.id)
                      .order_by(models.Notification.id.desc()).limit(30))
    unread = db.scalar(select(func.count()).select_from(models.Notification)
                       .where(models.Notification.user_id == user.id, models.Notification.read.is_(False)))
    return {"unread": unread or 0,
            "items": [{"id": n.id, "text": n.text, "thesis_id": n.thesis_id, "read": n.read,
                       "at": n.created_at.strftime("%d.%m %H:%M")} for n in rows]}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    db.execute(update(models.Notification).where(models.Notification.user_id == user.id).values(read=True))
    db.commit()
    return {"ok": True}
