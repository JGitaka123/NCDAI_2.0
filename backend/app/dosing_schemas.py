"""Explicit medicine-selection contract; missing clinical context stays unknown."""
from datetime import datetime, timezone, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class DoseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class DosingRequest(DoseModel):
    medicine_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    indication: Literal["hypertension", "type_2_diabetes"]
    proposed_dose_mg: float | None = Field(default=None, gt=0, le=100000, strict=True)
    frequency_per_day: int | None = Field(default=None, ge=1, le=24, strict=True)

    @model_validator(mode="after")
    def complete_schedule(self):
        if (self.proposed_dose_mg is None) != (self.frequency_per_day is None):
            raise ValueError("Provide both dose in mg and daily frequency, or neither")
        return self


class DosingContext(DoseModel):
    hepatic_impairment: Literal["yes", "no", "unknown"] = "unknown"
    breastfeeding: Literal["yes", "no", "unknown", "not_applicable"] = "unknown"
    acute_illness: Literal["yes", "no", "unknown"] = "unknown"
    dialysis: Literal["yes", "no", "unknown"] = "unknown"
    frailty: Literal["yes", "no", "unknown"] = "unknown"
    contraindications_reviewed: StrictBool = False
    interactions_reviewed: StrictBool = False
    renal_observed_at: datetime | None = None
    potassium_observed_at: datetime | None = None

    @field_validator("renal_observed_at", "potassium_observed_at")
    @classmethod
    def dated_laboratory_result(cls, value):
        if value is not None and (value.tzinfo is None or value > datetime.now(timezone.utc) + timedelta(minutes=5)):
            raise ValueError("Renal result time must include a timezone and cannot be in the future")
        return value


class DosingInput(DoseModel):
    dosing_requests: list[DosingRequest] = Field(default_factory=list, max_length=5)
    dosing_context: DosingContext = Field(default_factory=DosingContext)

    @model_validator(mode="after")
    def unique_medicines(self):
        ids = [r.medicine_id for r in self.dosing_requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Select each medicine once; duplicate dose requests are not supported")
        return self
