# 🧭 ThesisPath

Карта пути к защите диплома: темы, этапы с дедлайнами, версии файлов, комментарии руководителя
и автоматический **индекс готовности к защите (0–100%)**.
Стек: Python, FastAPI, PostgreSQL, SQLAlchemy, pytest, Docker, GitHub Actions.

## Запуск (3 команды)
```bash
git clone <repo> && cd thesispath
docker compose up --build
# открыть http://localhost:8000  (дашборд)  и  http://localhost:8000/docs  (Swagger)
```
Демо-аккаунты (пароль `demo1234`): `student@demo` (студент), `teacher@demo` (руководитель), `student2@demo` (студент с отставанием), `admin@demo` (координатор).

## Демо-сценарий
1. Студент выбирает тему → заявка уходит руководителю.
2. Руководитель подтверждает → создаётся карта из 8 этапов и чек-лист.
3. Студент загружает версию → этап «на проверке».
4. Руководитель комментирует и принимает/возвращает → растёт индекс готовности.

## Возможности сверх минимума
- **Студент:** выбор темы или собственная тема на рассмотрение, отзыв заявки, заметки «что сделано» к этапам, ближайшие дедлайны, уведомления, профиль и смена пароля.
- **Руководитель:** подтверждение или отказ с причиной, свои темы (создать/изменить/удалить), заявки и просрочки сверху списка.
- **Уведомления** 🔔 для всех ролей: заявка, подтверждение/отказ, новая версия, вердикт, новый этап.
- Лента событий по каждому диплому (кто и что сделал).
- Статистика для руководителя/админа: средняя готовность, просрочки, очередь на проверку.
- Прогноз завершения по текущему темпу и бейджи.
- Отчёт для печати / PDF (`GET /theses/{id}/report`).
- Поиск и фильтры по темам.
- Миграции Alembic (в Docker применяются автоматически).

## Индекс готовности
40% принятые этапы + 20% последняя версия одобрена + 20% чек-лист + 20% дисциплина (−10% за просрочку).
«Готов к защите»: индекс ≥ 90% и подтверждение руководителя.

## Роли и доступ
Студент видит только свой диплом, руководитель только своих студентов, админ всё.

## Тесты и качество
```bash
pip install -r requirements-dev.txt
ruff check .
pytest -v --cov=app   # по умолчанию SQLite in-memory; в CI: PostgreSQL (DATABASE_URL)
alembic upgrade head  # миграции (DATABASE_URL задаёт БД)
```

## API (основное)
| Метод | Путь | Кто |
|---|---|---|
| POST | /auth/register, /auth/login | все |
| GET/POST | /topics | все / руководитель |
| POST | /topics/{id}/select | студент |
| GET | /theses, /theses/me, /theses/{id} | по роли |
| PATCH | /theses/{id}/approve, /defense-ready | руководитель |
| GET/POST | /theses/{id}/milestones | по роли / руководитель |
| PATCH | /milestones/{id}/status | студент / руководитель |
| GET/POST | /milestones/{id}/versions | по роли / студент |
| POST | /versions/{id}/comments | по роли (вердикт: руководитель) |
| GET | /theses/{id}/readiness | по роли |
| PATCH | /checklist/{id} | руководитель |
| GET | /theses/{id}/events, /theses/{id}/report | по роли |
| GET | /stats | руководитель / админ |
| POST | /topics/propose | студент (своя тема) |
| PATCH/DELETE | /topics/{id} | владелец-руководитель / админ |
| PATCH | /theses/{id}/reject | руководитель |
| DELETE | /theses/me/request | студент (отзыв заявки) |
| PATCH | /milestones/{id}/note | студент |
| GET | /deadlines | по роли |
| GET, POST | /notifications, /notifications/read-all | все |
| PATCH, POST, GET | /auth/me, /auth/change-password, /auth/supervisors | все |

Postman: `postman/ThesisPath.postman_collection.json`. Диаграммы: `docs/diagrams.md`.

## Ограничения и развитие
Файлы лежат на диске контейнера (volume), без облачного хранилища.
Дальше: уведомления в Telegram, антиплагиат, аналитика по кафедре.
