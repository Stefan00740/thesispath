from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db
from ..deps import current_user, require_roles

router = APIRouter(prefix="/topics", tags=["Темы"])


def topic_out(t: models.Topic) -> dict:
    return {"id": t.id, "title": t.title, "description": t.description, "direction": t.direction,
            "status": t.status, "supervisor_id": t.supervisor_id, "supervisor": t.supervisor.full_name,
            "proposed_by_student": t.proposed_by_id is not None}


def _no_thesis_yet(db: Session, user: models.User) -> None:
    if db.scalar(select(models.Thesis).where(models.Thesis.student_id == user.id)):
        raise HTTPException(409, "У вас уже есть выбранная тема")


def _new_request(db: Session, user: models.User, topic: models.Topic, how: str) -> models.Thesis:
    thesis = models.Thesis(student_id=user.id, topic_id=topic.id, supervisor_id=topic.supervisor_id)
    db.add(thesis)
    db.flush()
    services.log_event(db, thesis.id, user.id, "topic_selected", f"{user.full_name} {how} «{topic.title}»")
    services.notify(db, topic.supervisor_id,
                    f"{user.full_name} {how} «{topic.title}»: подтвердите или отклоните заявку", thesis.id)
    return thesis


@router.get("")
def list_topics(direction: str | None = None, status: str | None = None,
                supervisor_id: int | None = None, q: str | None = None, db: Session = Depends(get_db),
                _: models.User = Depends(current_user)):
    query = select(models.Topic).order_by(models.Topic.id)
    if direction:
        query = query.where(models.Topic.direction == direction)
    if status:
        query = query.where(models.Topic.status == status)
    if supervisor_id:
        query = query.where(models.Topic.supervisor_id == supervisor_id)
    if q:
        query = query.where(models.Topic.title.ilike(f"%{q}%") | models.Topic.description.ilike(f"%{q}%"))
    return [topic_out(t) for t in db.scalars(query)]


@router.post("", status_code=201)
def create_topic(body: schemas.TopicIn, db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles("supervisor", "admin"))):
    supervisor_id = user.id if user.role == "supervisor" else body.supervisor_id
    supervisor = db.get(models.User, supervisor_id) if supervisor_id else None
    if not supervisor or supervisor.role != "supervisor":
        raise HTTPException(400, "Нужно указать существующего руководителя (supervisor_id)")
    topic = models.Topic(title=body.title, description=body.description,
                         direction=body.direction, supervisor_id=supervisor.id)
    db.add(topic)
    db.commit()
    return topic_out(topic)


@router.post("/propose", status_code=201)
def propose_topic(body: schemas.ProposeIn, db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles("student"))):
    """Студент предлагает собственную тему выбранному руководителю."""
    supervisor = db.get(models.User, body.supervisor_id)
    if not supervisor or supervisor.role != "supervisor":
        raise HTTPException(400, "Выберите руководителя из списка")
    _no_thesis_yet(db, user)
    topic = models.Topic(title=body.title, description=body.description, direction=body.direction,
                         supervisor_id=supervisor.id, status="taken", proposed_by_id=user.id)
    db.add(topic)
    db.flush()
    thesis = _new_request(db, user, topic, "предложил(а) свою тему")
    db.commit()
    return {"thesis_id": thesis.id, "status": thesis.status,
            "message": "Тема отправлена руководителю на рассмотрение"}


def _own_topic(db: Session, topic_id: int, user: models.User) -> models.Topic:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Тема не найдена")
    if user.role != "admin" and topic.supervisor_id != user.id:
        raise HTTPException(403, "Это не ваша тема")
    return topic


@router.patch("/{topic_id}")
def update_topic(topic_id: int, body: schemas.TopicUpdate, db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles("supervisor", "admin"))):
    topic = _own_topic(db, topic_id, user)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(topic, field, value)
    db.commit()
    return topic_out(topic)


@router.delete("/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles("supervisor", "admin"))):
    topic = _own_topic(db, topic_id, user)
    if topic.status != "free":
        raise HTTPException(409, "Нельзя удалить тему, которую уже выбрал студент")
    db.delete(topic)
    db.commit()
    return {"deleted": True}


@router.post("/{topic_id}/select", status_code=201)
def select_topic(topic_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles("student"))):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Тема не найдена")
    if topic.status != "free":
        raise HTTPException(409, "Тема уже занята")
    _no_thesis_yet(db, user)
    topic.status = "taken"
    thesis = _new_request(db, user, topic, "выбрал(а) тему")
    db.commit()
    return {"thesis_id": thesis.id, "status": thesis.status,
            "message": "Заявка отправлена руководителю на подтверждение"}
