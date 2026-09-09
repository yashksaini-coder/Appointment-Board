# Appointment Board

A shared appointment board for a small team. See the schedule as a kanban board,
add, edit, complete and cancel appointments, and filter by date or status —
with double-booking prevented at the database level.

![stack](https://img.shields.io/badge/React-18-informational) ![stack](https://img.shields.io/badge/FastAPI-0.115-informational) ![stack](https://img.shields.io/badge/PostgreSQL-16-informational) ![stack](https://img.shields.io/badge/Docker-Compose-informational)

---

## Quick start

```bash
git clone https://github.com/yashksaini-coder/Appointment-Board && cd Appointment-Board
docker compose up --build
```

Open **http://localhost:8080**. The database is created and seeded with seven
sample appointments on first boot, so there is nothing else to set up.

| What            | Where                        |
|-----------------|------------------------------|
| Board           | http://localhost:8080        |
| API docs        | http://localhost:8000/docs   |
| PostgreSQL      | `localhost:5432`             |

Default credentials are `appointments` / `appointments` / `appointments`.
Copy `.env.example` to `.env` to change ports, credentials or log settings.

---

## Features

- **Kanban board** — three status columns, with the calendar running down the
  page as full-width day bands so chronology survives the status grouping.
- **Duration you can see** — every card draws the appointment on the same fixed
  06:00–22:00 scale, so bar length is directly comparable across cards.
- **No double bookings** — enforced by a PostgreSQL exclusion constraint, not
  just an application check, so it holds under concurrent writes.
- **Clash prevented, not explained** — the add/edit form shows the chosen day's
  existing bookings and turns your slot red before you can submit it.
- **Drag and drop** — drag a scheduled card onto Completed or Cancelled.
  Cancelling always asks first. Every drag has a button equivalent.
- **Filter** by date, by status, or both.
- **Cancelled stays visible**, struck through and clearly marked. Nothing is
  ever deleted.
- **Light / dark / system theme**, remembered between visits.
- **Responsive** from desktop to phone, keyboard accessible, WCAG AA contrast.
- **Structured logging** with a request id on every line.

---

## Stack

### Backend
| Library | Why |
|---|---|
| **FastAPI** `0.115` | Routing, dependency injection, automatic OpenAPI docs |
| **Pydantic** `2.10` | Request/response validation and serialisation |
| **SQLAlchemy** `2.0` | ORM and query building, modern `Mapped[]` style |
| **psycopg** `3.2` | PostgreSQL driver |
| **uvicorn** `0.34` | ASGI server |
| **pytest** + **httpx** | Tests, run against a real PostgreSQL |

### Frontend
| Library | Why |
|---|---|
| **React** `18.3` | UI |
| **Vite** `6` | Dev server and build |

No CSS framework, no component library, no state library and no HTTP client —
plain CSS, React hooks and `fetch`. Drag and drop uses the native HTML5 API.

### Infrastructure
PostgreSQL 16 · nginx (serves the built SPA and proxies `/api`) · Docker Compose.

---

## Commands

```bash
# Run everything
docker compose up --build
docker compose up -d                  # background
docker compose down                   # stop
docker compose down -v                # stop and wipe the database

# Logs
docker compose logs -f backend
LOG_FORMAT=json docker compose up -d backend   # machine-readable logs

# Tests
docker compose exec backend python -m pytest -q
docker compose exec backend python -m pytest -q -k overlap

# Database shell
docker compose exec db psql -U appointments -d appointments
```

### Backend Makefile

`backend/Makefile` wraps the common tasks. Run `make` on its own to list them.

```bash
cd backend
make setup      # create .venv with uv and install dependencies
make db-up      # start just PostgreSQL
make dev        # run the API with autoreload on :8000
make test       # run the test suite
```

| Target | Does |
|---|---|
| `make setup` | Creates `.venv` with [uv](https://docs.astral.sh/uv/) and installs dependencies |
| `make dev` | API with autoreload on `:8000` |
| `make serve` | API the way production runs it — 4 workers, JSON logs |
| `make test` | Test suite (needs PostgreSQL; `make db-up` first) |
| `make lint` | Byte-compiles every module to catch syntax errors |
| `make db-up` | Starts only the database container |
| `make up` / `make down` | Whole stack up or down |
| `make logs` | Follows the backend logs |
| `make psql` | psql shell on the database |
| `make reset` | Wipes the database volume and starts fresh |
| `make clean` | Removes `.venv` and Python caches |

### Without Docker

```bash
# Backend — needs a PostgreSQL reachable at DATABASE_URL
cd backend
make setup && make dev

# Frontend — proxies /api to localhost:8000
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # production build into dist/
```

---

## Using the board

1. **Open the board.** Appointments are grouped by day, and split across the
   Scheduled, Completed and Cancelled columns.
2. **Filter** with the date picker or the status menu. Choosing one status shows
   only that column.
3. **Add appointment.** Enter a title, an optional description, a date and a
   start and end time. The strip under the time fields shows what that day
   already holds and warns you before you submit a clashing slot.
4. **Edit, complete or cancel** from the buttons on any scheduled card, or drag
   the card into another column.
5. **Cancelling asks for confirmation.** The appointment stays on the board,
   marked as cancelled, and its time slot becomes bookable again.

### Rules the app enforces

- A title, a date, a start time and an end time are required.
- The end time must be after the start time.
- Two appointments cannot overlap on the same day. Back-to-back is fine —
  10:00–11:00 and 11:00–12:00 do not clash.
- Cancelled and completed are **final**: those appointments cannot be edited,
  completed or cancelled again. Cards only move left to right.
- Cancelling frees the time slot. Completing does not — it still happened.

---

## API

Base URL `http://localhost:8000`. Interactive docs at `/docs`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/appointments` | List all, sorted by date then start time |
| `GET` | `/api/appointments?date=YYYY-MM-DD` | Filter by date |
| `GET` | `/api/appointments?status=scheduled` | Filter by status |
| `GET` | `/api/appointments/{id}` | Fetch one |
| `POST` | `/api/appointments` | Create |
| `PATCH` | `/api/appointments/{id}` | Edit (partial, scheduled only) |
| `POST` | `/api/appointments/{id}/complete` | Mark completed |
| `POST` | `/api/appointments/{id}/cancel` | Cancel |
| `GET` | `/api/health` | Liveness and database check |

### Appointment

```json
{
  "id": 1,
  "title": "Team standup",
  "description": "Daily sync on blockers and priorities.",
  "appointment_date": "2026-09-10",
  "start_time": "09:00",
  "end_time": "09:30",
  "status": "scheduled",
  "created_at": "2026-09-10T08:00:00Z",
  "updated_at": "2026-09-10T08:00:00Z"
}
```

`status` is one of `scheduled`, `completed`, `cancelled`.

### Create one

```bash
curl -X POST http://localhost:8000/api/appointments \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Design review",
    "description": "Walk through the new mockups.",
    "appointment_date": "2026-09-11",
    "start_time": "14:00",
    "end_time": "15:00"
  }'
```

### Errors

Every error has the same shape, so a client can always show `detail` directly:

```json
{ "detail": "Time slot unavailable: \"Team standup\" is already booked on 2026-09-10 from 09:00 to 09:30." }
```

| Code | Meaning |
|---|---|
| `400` | Unknown filter value |
| `404` | No appointment with that id |
| `409` | Time slot taken, or the appointment is already completed/cancelled |
| `422` | Missing or invalid fields (e.g. end time not after start time) |
| `500` | Server error — the body includes a `request_id` to quote |

Every response carries an `X-Request-Id` header. Send your own to trace a
request through the logs.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `appointments` | Database credentials |
| `DATABASE_URL` | built from the above | Full SQLAlchemy connection URL |
| `CORS_ORIGINS` | `localhost:5173,localhost:8080` | Comma-separated allowed origins |
| `DB_PORT` / `API_PORT` / `WEB_PORT` | `5432` / `8000` / `8080` | Host ports |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | `console` | `console` for humans, `json` for log aggregation |

---

## Project layout

```
backend/
  app/
    main.py            routes, middleware, error handling, sample data
    models.py          the appointments table and all its constraints
    schemas.py         request/response validation
    db.py              engine and session
    logging_setup.py   structured logging
  tests/               API tests, run against a real PostgreSQL
  Makefile             setup, run and test shortcuts
frontend/
  src/
    App.jsx            board, columns, day bands, cards, drag and drop
    AppointmentForm.jsx  add/edit dialog with the availability strip
    lane.js            shared 06:00–22:00 lane geometry
    api.js             fetch wrapper
    styles.css         the design system
  nginx.conf           serves the SPA, proxies /api
docker-compose.yml
docs/
  DEPLOYMENT.md      taking this to production
```

---

## Deploying

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for production setup — managed
PostgreSQL, migrations, and step-by-step guides for Vercel, AWS, DigitalOcean
and plain Docker.
