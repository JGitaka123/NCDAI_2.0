from datetime import date, datetime, timezone, timedelta
from typing import Literal, Annotated
import re
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator
from .dosing_schemas import DosingContext, DosingRequest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=256)


class UserCreate(StrictModel):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    display_name: str = Field(min_length=1, max_length=160)
    role: Literal["clinician", "supervisor", "admin"]
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=14, max_length=256)


Pregnancy = Literal["yes", "no", "unknown", "not_applicable"]
Known = Literal["yes", "no", "unknown"]
Urgency = Literal["routine", "soon", "urgent", "emergency"]


class PatientCreate(StrictModel):
    external_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    given_name: str = Field(min_length=1, max_length=100)
    family_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    sex: Literal["female", "male", "other", "unknown"]
    female_pregnancy_status: Pregnancy | None = None
    phone: str | None = Field(default=None, max_length=40)
    synthetic: Literal[True]

    @field_validator("synthetic", mode="before")
    @classmethod
    def explicitly_synthetic(cls, value):
        if value is not True:
            raise ValueError("An explicit synthetic=true marker is required")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def adult_dob(cls, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18 or age > 120 or value > today:
            raise ValueError("Only adults aged 18 through 120 are supported")
        return value


class Medication(StrictModel):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=160)
    dose: float | None = Field(default=None, gt=0, le=100000, strict=True)
    unit: str | None = Field(default=None, max_length=40)
    frequency: str | None = Field(default=None, max_length=80)


Symptoms = Literal["chest_pain", "breathlessness", "neurological_deficit", "confusion", "seizure", "severe_headache", "visual_disturbance", "vomiting", "dehydration", "foot_ulcer", "hypoglycemia_symptoms", "wheeze", "hemoptysis", "unexplained_weight_loss", "persistent_cough", "breast_lump", "abnormal_bleeding"]


class ClinicalData(StrictModel):
    systolic_bp: float | None = Field(default=None, ge=40, le=300)
    diastolic_bp: float | None = Field(default=None, ge=20, le=200)
    repeat_systolic_bp: float | None = Field(default=None, ge=40, le=300)
    repeat_diastolic_bp: float | None = Field(default=None, ge=20, le=200)
    pulse: float | None = Field(default=None, ge=20, le=250)
    oxygen_saturation: float | None = Field(default=None, ge=30, le=100)
    respiratory_rate: float | None = Field(default=None, ge=4, le=80)
    hba1c: float | None = Field(default=None, ge=2, le=25)
    glucose: float | None = Field(default=None, gt=0, le=1500)
    glucose_unit: Literal["mmol/L", "mg/dL"] = "mmol/L"
    egfr: float | None = Field(default=None, ge=0, le=200)
    potassium: float | None = Field(default=None, ge=1, le=10)
    pregnancy_status: Pregnancy = "unknown"
    known_hypertension: Known = "unknown"
    known_diabetes: Known = "unknown"
    known_asthma: Known = "unknown"
    known_copd: Known = "unknown"
    known_ckd: Known = "unknown"
    known_cancer: Known = "unknown"
    tobacco_use: Literal["unknown", "current", "former", "never"] = "unknown"
    medications: list[Medication] = Field(default_factory=list, max_length=50)
    medications_reviewed: StrictBool = False
    allergies: list[str] = Field(default_factory=list, max_length=50)
    allergies_reviewed: StrictBool = False
    symptoms: list[Symptoms] = Field(default_factory=list, max_length=18)
    symptoms_reviewed: StrictBool = False
    adherence: Literal["taking", "missed", "unknown"] = "unknown"
    notes: str = Field(default="", max_length=10000)
    observed_at: datetime | None = None
    medicine_availability: Literal["available", "limited", "unknown"] = "unknown"
    dosing_requests: list[DosingRequest] = Field(default_factory=list, max_length=5)
    dosing_context: DosingContext = Field(default_factory=DosingContext)

    @field_validator("systolic_bp", "diastolic_bp", "repeat_systolic_bp", "repeat_diastolic_bp", "pulse", "oxygen_saturation", "respiratory_rate", "hba1c", "glucose", "egfr", "potassium", mode="before")
    @classmethod
    def numeric_measurement(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError("Measurement must be a JSON number or null")
        return value

    @field_validator("allergies")
    @classmethod
    def bounded_allergies(cls, values):
        if any(not v.strip() or len(v) > 160 for v in values):
            raise ValueError("Allergy entries must contain 1 to 160 characters")
        return [v.strip() for v in values]

    @field_validator("observed_at")
    @classmethod
    def observed_time(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Observation time must include a timezone")
            if value > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("Observation time cannot be in the future")
        return value

    @model_validator(mode="after")
    def plausible_pairs(self):
        medicine_ids = [r.medicine_id for r in self.dosing_requests]
        if len(medicine_ids) != len(set(medicine_ids)):
            raise ValueError("Select each dosing medicine once")
        for s, d in [(self.systolic_bp, self.diastolic_bp), (self.repeat_systolic_bp, self.repeat_diastolic_bp)]:
            if s is not None and d is not None and s <= d:
                raise ValueError("Systolic pressure must exceed diastolic pressure")
        if self.glucose is not None and self.glucose_unit == "mmol/L" and self.glucose > 83.3:
            raise ValueError("Glucose is outside the supported mmol/L measurement range; check units")
        if len(self.symptoms) != len(set(self.symptoms)):
            raise ValueError("Symptoms must not be duplicated")
        return self


class EncounterCreate(StrictModel):
    patient_id: str
    data: ClinicalData


class EncounterPatch(StrictModel):
    expected_version: int = Field(ge=1)
    data: ClinicalData


class Decision(StrictModel):
    recommendation_id: str = Field(min_length=1, max_length=100)
    action: Literal["accept", "modify", "defer", "reject"]
    reason: str | None = Field(default=None, max_length=2000)
    modified_text: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def accountable_decision(self):
        if self.action != "accept" and not self.reason:
            raise ValueError("A reason is required for modify, defer and reject")
        if self.action == "modify" and not self.modified_text:
            raise ValueError("Modified recommendation text is required")
        return self


class ReviewCreate(StrictModel):
    assessment_id: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)
    decisions: list[Decision] = Field(max_length=100)
    note: str | None = Field(default=None, max_length=4000)


class AIBriefingRequest(StrictModel):
    assessment_id: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)


class ReferralCreate(StrictModel):
    reason: str = Field(min_length=3, max_length=4000)
    destination: str = Field(min_length=2, max_length=200)
    urgency: Urgency


class ReferralPatch(StrictModel):
    status: Literal["accepted", "completed", "cancelled"]
    outcome: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def completion_outcome(self):
        if self.status == "completed" and not self.outcome:
            raise ValueError("Completed referrals require an outcome")
        return self
