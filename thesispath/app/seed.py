from datetime import date, timedelta

from sqlalchemy import select

from . import models, services
from .database import SessionLocal
from .security import hash_password

DEMO_PASSWORD = "demo1234"


def _user(email: str, name: str, role: str) -> models.User:
    return models.User(email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))


def seed_demo() -> None:
    with SessionLocal() as db:
        if db.scalar(select(models.User)):
            return
        admin = _user("admin@demo", "Координатор", "admin")
        teacher = _user("teacher@demo", "Руководитель", "supervisor")
        student = _user("student@demo", "Студент", "student")
        student2 = _user("student2@demo", "Студент 2", "student")
        db.add_all([admin, teacher, student, student2])
        db.flush()

        topics = []
        for title, direction in [
            ("Система управления дипломными работами", "Информационные системы"),
            ("Прогнозирование спроса с помощью ML", "Data Science"),
            ("Чат-бот для поддержки студентов", "NLP"),
            ("Умный мониторинг серверов", "DevOps"),
            ("Рекомендательная система учебных курсов", "Data Science"),
        ]:
            t = models.Topic(title=title, direction=direction, supervisor_id=teacher.id,
                             description="Демо-тема")
            db.add(t)
            topics.append(t)
        db.flush()

        # Второй студент: уже идёт работа, есть отставание (чтобы светофор и прогноз были видны сразу)
        topics[1].status = "taken"
        start = date.today() - timedelta(days=50)
        thesis = models.Thesis(student_id=student2.id, topic_id=topics[1].id, supervisor_id=teacher.id,
                               status="active", created_at=models.now() - timedelta(days=50))
        db.add(thesis)
        db.flush()
        services.build_roadmap(db, thesis, start=start)
        db.flush()
        db.refresh(thesis)
        for m in thesis.milestones:
            if m.position in (1, 2):
                m.status = "accepted"
            elif m.position == 3:
                m.status = "revision"  # дедлайн прошёл: красный
        thesis.checklist[0].done = True
        for kind, text in [
            ("topic_selected", f"{student2.full_name} выбрал(а) тему «{topics[1].title}»"),
            ("approved", "Руководитель подтвердил закрепление, создана карта из 8 этапов"),
            ("comment", f"{teacher.full_name} вернул(а) на доработку этап «Глава 1»"),
        ]:
            services.log_event(db, thesis.id, teacher.id if kind != "topic_selected" else student2.id, kind, text)
        services.notify(db, teacher.id, "Студент 2 просит проверить этап «Введение»", thesis.id)
        services.notify(db, student2.id, "Руководитель вернул(а) на доработку этап «Глава 1»", thesis.id)
        db.commit()
