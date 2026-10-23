from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import current_user
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])


def user_out(u: models.User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role}


@router.post("/register", status_code=201)
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(models.User).where(models.User.email == body.email)):
        raise HTTPException(409, "Пользователь с таким email уже существует")
    user = models.User(email=body.email, full_name=body.full_name, role=body.role,
                       password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user_out(user)


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == form.username))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Неверный email или пароль")
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": user_out(user)}


@router.get("/me")
def me(user: models.User = Depends(current_user)):
    return user_out(user)


@router.patch("/me")
def update_me(body: schemas.ProfileIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    user.full_name = body.full_name.strip()
    db.commit()
    return user_out(user)


@router.post("/change-password")
def change_password(body: schemas.PasswordIn, db: Session = Depends(get_db),
                    user: models.User = Depends(current_user)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "Текущий пароль указан неверно")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"changed": True}


@router.get("/supervisors")
def supervisors(db: Session = Depends(get_db), _: models.User = Depends(current_user)):
    rows = db.scalars(select(models.User).where(models.User.role == "supervisor").order_by(models.User.full_name))
    return [{"id": u.id, "full_name": u.full_name} for u in rows]
