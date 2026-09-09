from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

SCHEDULED = "scheduled"
COMPLETED = "completed"
CANCELLED = "cancelled"
STATUSES = (SCHEDULED, COMPLETED, CANCELLED)

# A cancelled slot is free again; a completed one still happened, so it stays booked.
BLOCKING_STATUSES = (SCHEDULED, COMPLETED)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    appointment_date: Mapped["Date"] = mapped_column(Date, nullable=False)
    start_time: Mapped["Time"] = mapped_column(Time, nullable=False)
    end_time: Mapped["Time"] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SCHEDULED)
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="end_time_after_start_time"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled')", name="status_is_valid"
        ),
        Index("ix_appointments_date_status", "appointment_date", "status"),
        # The real double-booking guard. A pre-insert SELECT can be beaten by a
        # concurrent request; this constraint cannot. Half-open '[)' so 10-11 and
        # 11-12 are neighbours, not a conflict.
        ExcludeConstraint(
            (
                literal_column(
                    "tsrange(appointment_date + start_time,"
                    " appointment_date + end_time, '[)')"
                ),
                "&&",
            ),
            name="no_overlapping_appointments",
            using="gist",
            where=text("status <> 'cancelled'"),
        ),
    )
