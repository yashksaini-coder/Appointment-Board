import logging
import os
import re
import time as _time
from contextlib import asynccontextmanager
from datetime import date, time, timedelta
from time import perf_counter
from uuid import uuid4

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status as http
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .logging_setup import HEALTH_PATH, configure_logging, fields, request_id
from .models import BLOCKING_STATUSES, CANCELLED, COMPLETED, SCHEDULED, STATUSES, Appointment
from .schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate

configure_logging()
log = logging.getLogger("app")


def _wait_for_db(attempts: int = 30, delay: float = 1.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect():
                if attempt > 1:
                    log.info("db.ready", extra=fields(attempts=attempt))
                return
        except OperationalError:
            log.warning("db.not_ready", extra=fields(attempt=attempt, attempts=attempts))
            _time.sleep(delay)
    # The single line that means "the API is dead and someone must look at it".
    log.error("db.unavailable", extra=fields(attempts=attempts, waited_seconds=attempts * delay))
    raise RuntimeError("Database did not become available in time")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _wait_for_db()
    Base.metadata.create_all(engine)
    seed_if_empty()
    log.info("startup.complete")
    yield


app = FastAPI(title="Appointment Board API", version="1.0.0", lifespan=lifespan)

# --------------------------------------------------------------- access log

# A request id from the client is untrusted input that ends up in the log
# stream and in a reflected response header. Keep it to an opaque token.
_RID_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _client_is_gone(exc: BaseException) -> bool:
    """The peer vanished mid-request. Not a service failure; pages nobody."""
    if isinstance(exc, ClientDisconnect):
        return True
    # Starlette raises this bare RuntimeError when the receive channel closed
    # before the app produced anything.
    return isinstance(exc, RuntimeError) and str(exc) == "No response returned."


@app.middleware("http")
async def access_log(request: Request, call_next):
    rid = _RID_UNSAFE.sub("", request.headers.get("X-Request-Id", ""))[:64] or uuid4().hex[:12]
    token = request_id.set(rid)
    started = perf_counter()
    where = {"method": request.method, "path": request.url.path}
    try:
        try:
            response = await call_next(request)
        except anyio.get_cancelled_exc_class():
            # Cancellation must keep propagating or the surrounding task group
            # is left in an inconsistent state. Note it and re-raise.
            log.info("request.cancelled", extra=fields(**where))
            raise
        except BaseException as exc:
            if _client_is_gone(exc):
                log.info("request.disconnected", extra=fields(**where))
                response = Response(status_code=499)
            else:
                # Handled here rather than re-raised: Starlette's outer error
                # middleware would return a response we cannot attach the
                # request id to, and that id is the point on a failing request.
                log.exception("request.failed", extra=fields(**where))
                response = JSONResponse(
                    status_code=http.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Internal server error.", "request_id": rid},
                )

        response.headers["X-Request-Id"] = rid
        status_code = response.status_code
        if status_code >= 500:
            level = logging.ERROR
        elif status_code == 499:
            level = logging.INFO       # the client left; nothing went wrong here
        elif status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO
        # Health checks are the loudest thing in the log and say nothing until
        # they fail, so only keep the failures.
        if request.url.path != HEALTH_PATH or status_code >= 400:
            log.log(
                level,
                "request",
                extra=fields(
                    **where,
                    query=request.url.query,
                    status=status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 1),
                ),
            )
        return response
    finally:
        request_id.reset(token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


# ---------------------------------------------------------------- error shape

@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Collapse Pydantic's nested error list into one sentence the UI can show."""
    messages = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"] if p not in ("body", "query"))
        msg = err["msg"].removeprefix("Value error, ")
        messages.append(f"{field}: {msg}" if field else msg)
    detail = "; ".join(messages)
    # The message only -- never err["input"], which is the user's own content.
    log.warning("request.validation_failed", extra=fields(detail=detail))
    return JSONResponse(status_code=http.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": detail})


CONSTRAINT_MESSAGES = {
    "no_overlapping_appointments": "That time slot is already taken.",
    "end_time_after_start_time": "End time must be after start time.",
    "title_not_blank": "Title is required.",
}


def _constraint_name(exc: IntegrityError) -> str:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) or ""


# ------------------------------------------------------------------- helpers

def _slot(appointment: Appointment) -> dict:
    """Identity fields, read while the object is still usable.

    Must be called BEFORE commit: after a rollback the instance is expired, and
    touching an attribute would emit a fresh SELECT from inside the error path.
    """
    return {
        "date": str(appointment.appointment_date),
        "start": appointment.start_time.strftime("%H:%M"),
        "end": appointment.end_time.strftime("%H:%M"),
    }


def _get_or_404(db: Session, appointment_id: int) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, f"Appointment {appointment_id} was not found.")
    return appointment


def _find_conflict(db: Session, appt: Appointment, exclude_id: int | None) -> Appointment | None:
    """Overlap test for half-open intervals: a.start < b.end AND a.end > b.start."""
    stmt = select(Appointment).where(
        Appointment.appointment_date == appt.appointment_date,
        Appointment.status.in_(BLOCKING_STATUSES),
        Appointment.start_time < appt.end_time,
        Appointment.end_time > appt.start_time,
    )
    if exclude_id is not None:
        stmt = stmt.where(Appointment.id != exclude_id)
    return db.scalars(stmt.order_by(Appointment.start_time)).first()


def _reject_if_conflicting(db: Session, appt: Appointment, exclude_id: int | None = None) -> None:
    # The earliest clash of possibly several -- enough to name one, not a census.
    clash = _find_conflict(db, appt, exclude_id)
    if clash is not None:
        log.warning(
            "appointment.slot_conflict",
            extra=fields(
                appointment_id=exclude_id,
                conflict_id=clash.id,
                conflict_status=clash.status,
                **_slot(appt),
            ),
        )
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            f'Time slot unavailable: "{clash.title}" is already booked on '
            f'{clash.appointment_date} from {clash.start_time:%H:%M} to {clash.end_time:%H:%M}.',
        )


def _require_scheduled(appointment: Appointment, action: str) -> None:
    if appointment.status != SCHEDULED:
        log.warning(
            "appointment.invalid_transition",
            extra=fields(appointment_id=appointment.id, action=action, status=appointment.status),
        )
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            f"Cannot {action} an appointment that is already {appointment.status}.",
        )


def _commit(db: Session, appointment: Appointment, event: str, **extra) -> Appointment:
    # Read identity before committing: on the create path the row has no id yet
    # and a rollback expunges the instance, which is exactly the concurrent-race
    # case this log line exists to explain.
    slot = _slot(appointment)
    known_id = appointment.id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = _constraint_name(exc)
        # Reaching here means the pre-flight SELECT lost a race with another
        # writer and the database caught what the application missed.
        log.warning(
            "appointment.rejected_by_database",
            extra=fields(appointment_id=known_id, constraint=constraint, **slot),
        )
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            CONSTRAINT_MESSAGES.get(constraint, "That change conflicts with an existing appointment."),
        ) from exc
    db.refresh(appointment)
    log.info(event, extra=fields(appointment_id=appointment.id, **_slot(appointment), **extra))
    return appointment


# -------------------------------------------------------------------- routes

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.get("/api/appointments", response_model=list[AppointmentOut])
def list_appointments(
    db: Session = Depends(get_db),
    date_: date | None = Query(default=None, alias="date"),
    status_: str | None = Query(default=None, alias="status"),
):
    if status_ and status_ not in STATUSES:
        log.warning("appointment.bad_filter", extra=fields(status=status_))
        raise HTTPException(
            http.HTTP_400_BAD_REQUEST,
            f"Unknown status '{status_}'. Expected one of: {', '.join(STATUSES)}.",
        )
    stmt = select(Appointment)
    if date_:
        stmt = stmt.where(Appointment.appointment_date == date_)
    if status_:
        stmt = stmt.where(Appointment.status == status_)
    stmt = stmt.order_by(Appointment.appointment_date, Appointment.start_time, Appointment.id)
    rows = db.scalars(stmt).all()
    # "The board looks empty" is unanswerable from an access line alone.
    log.info(
        "appointment.listed",
        extra=fields(date=str(date_) if date_ else None, status=status_, count=len(rows)),
    )
    return rows


@app.get("/api/appointments/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, appointment_id)


@app.post("/api/appointments", response_model=AppointmentOut, status_code=http.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    appointment = Appointment(**payload.model_dump(), status=SCHEDULED)
    _reject_if_conflicting(db, appointment)
    db.add(appointment)
    return _commit(db, appointment, "appointment.created")


@app.patch("/api/appointments/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int, payload: AppointmentUpdate, db: Session = Depends(get_db)
):
    appointment = _get_or_404(db, appointment_id)
    _require_scheduled(appointment, "edit")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "No changes were supplied.")
    for field, value in changes.items():
        setattr(appointment, field, value)

    if appointment.end_time <= appointment.start_time:
        # Raised by hand, so it bypasses the RequestValidationError handler --
        # log it here or the identical rejection is silent on the edit path.
        log.warning(
            "request.validation_failed",
            extra=fields(detail="End time must be after start time.", appointment_id=appointment_id),
        )
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "End time must be after start time.")
    _reject_if_conflicting(db, appointment, exclude_id=appointment.id)
    return _commit(db, appointment, "appointment.updated", changed=sorted(changes))


@app.post("/api/appointments/{appointment_id}/complete", response_model=AppointmentOut)
def complete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = _get_or_404(db, appointment_id)
    _require_scheduled(appointment, "complete")
    appointment.status = COMPLETED
    return _commit(db, appointment, "appointment.completed")


@app.post("/api/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = _get_or_404(db, appointment_id)
    _require_scheduled(appointment, "cancel")
    appointment.status = CANCELLED
    # The slot logged here is the one that just became bookable again.
    return _commit(db, appointment, "appointment.cancelled", slot_released=True)


# ---------------------------------------------------------------------- seed

SAMPLE = [
    ("Team standup", "Daily sync on blockers and priorities.", 0, "09:00", "09:30", SCHEDULED),
    ("Design review", "Walk through the new booking flow mockups.", 0, "11:00", "12:00", SCHEDULED),
    ("Client call - Nordic Ltd", "Quarterly check-in and renewal talk.", 0, "15:00", "16:00", SCHEDULED),
    ("Sprint retrospective", "What went well, what to change next sprint.", 1, "10:00", "11:00", SCHEDULED),
    ("Dentist appointment", "Routine check-up, clinic on 5th street.", 1, "17:00", "17:45", CANCELLED),
    ("Onboarding: new intern", "Laptop setup, repo access, first ticket.", -1, "10:00", "11:30", COMPLETED),
    ("Budget planning", "Finalise Q4 numbers with finance.", -1, "14:00", "15:00", CANCELLED),
]


def seed_if_empty() -> None:
    """Sample data so the board is reviewable the moment it boots.

    Guarded by an env var: an empty production database is not an invitation to
    write seven fake appointments into it. Set SEED_SAMPLE_DATA=false anywhere
    that is not a demo or a local checkout.
    """
    if os.getenv("SEED_SAMPLE_DATA", "true").strip().lower() not in ("1", "true", "yes"):
        log.info("db.seed_skipped")
        return
    with Session(engine) as db:
        if db.scalar(select(Appointment.id).limit(1)) is not None:
            return
        today = date.today()
        db.add_all(
            Appointment(
                title=t, description=d, appointment_date=today + timedelta(days=off),
                start_time=time.fromisoformat(s), end_time=time.fromisoformat(e), status=st,
            )
            for t, d, off, s, e, st in SAMPLE
        )
        db.commit()
        # WARNING, not INFO: seeing this in a running deployment means the
        # database came up empty, which is an incident, not a milestone.
        log.warning("db.seeded", extra=fields(count=len(SAMPLE)))
