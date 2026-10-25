from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .locations import UFS, validate_city_state


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CityInput(Input):
    id: str = Field(pattern=r"^[0-9]{7}$")
    name: str = Field(min_length=2, max_length=100)
    uf: str

    @field_validator("uf")
    @classmethod
    def uf_valid(cls, value: str) -> str:
        value = value.upper()
        if value not in UFS:
            raise ValueError("UF inválida")
        return value

    @model_validator(mode="after")
    def city_state_valid(self):
        validate_city_state(self.id, self.uf)
        return self


class RunInput(Input):
    city_id: str = Field(pattern=r"^[0-9]{7}$")
    start_date: date
    end_date: date
    max_pages_per_job: int = Field(default=500, ge=1, le=100000)
    max_purchases: int = Field(default=0, ge=0)
    max_units: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def dates_valid(self):
        if self.start_date > self.end_date:
            raise ValueError("data inicial deve ser anterior ou igual à final")
        return self


class ScheduleInput(Input):
    city_id: str = Field(pattern=r"^[0-9]{7}$")
    name: str = Field(min_length=2, max_length=100)
    frequency: Literal["once", "daily", "weekly"]
    local_time: str = "02:00"
    timezone: str = "America/Sao_Paulo"
    weekday: int | None = Field(default=None, ge=0, le=6)
    window_days: int = Field(default=90, ge=1, le=3650)
    due_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def schedule_valid(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("fuso horário inválido") from None
        clock = time.fromisoformat(self.local_time)
        if clock.tzinfo is not None or clock.second or clock.microsecond:
            raise ValueError("horário deve usar HH:MM")
        self.local_time = clock.strftime("%H:%M")
        if self.frequency == "weekly" and self.weekday is None:
            raise ValueError("selecione o dia da semana")
        if self.frequency == "once" and (self.due_at is None or self.due_at.tzinfo is None):
            raise ValueError("agendamento pontual requer data e fuso horário")
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError("informe ambas as datas ou use janela móvel")
        if self.start_date and self.start_date > self.end_date:
            raise ValueError("período inválido")
        return self


class EnabledInput(Input):
    enabled: bool
