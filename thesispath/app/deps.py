from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import decode_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> models.User:
    user_id = decode_token(token)
    user = db.get(models.User, user_id) if user_id else None
    if not user:
        raise HTTPException(401, "Недействительный токен")
    return user


def require_roles(*roles: str):
    def checker(user: models.User = Depends(current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(403, "Недостаточно прав для этого действия")
        return user

    return checker


def get_thesis(db: Session, thesis_id: int) -> models.Thesis:
    thesis = db.get(models.Thesis, thesis_id)
    if not thesis:
        raise HTTPException(404, "Диплом не найден")
    return thesis


def check_access(thesis: models.Thesis, user: models.User) -> None:
    if user.role == "admin" or user.id in (thesis.student_id, thesis.supervisor_id):
        return
    raise HTTPException(403, "Нет доступа к этому диплому")


def is_reviewer(thesis: models.Thesis, user: models.User) -> bool:
    return user.role == "admin" or user.id == thesis.supervisor_id


def require_reviewer(thesis: models.Thesis, user: models.User) -> None:
    if not is_reviewer(thesis, user):
        raise HTTPException(403, "Только руководитель этого диплома может это сделать")
