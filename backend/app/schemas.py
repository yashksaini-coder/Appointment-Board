from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class AppointmentBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    appointment_date: date
    start_time: time
    end_time: time

    @field_validator("title", "description")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("Title is required")
        return v

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    """Partial edit. Cross-field checks happen in the route against stored values."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    appointment_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None

    @field_validator("title", "description")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("Title is required")
        return v


class AppointmentOut(AppointmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime
    updated_at: datetime

    # The <input type="time"> control speaks "HH:MM", so hand it exactly that.
    @field_serializer("start_time", "end_time")
    def fmt_time(self, v: time) -> str:
        return v.strftime("%H:%M")
