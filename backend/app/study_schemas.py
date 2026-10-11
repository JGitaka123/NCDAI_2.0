from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

def today():
    return datetime.now(ZoneInfo('Africa/Nairobi')).date()

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Enrolment(StrictModel):
    kind: Literal['enrolment']
    index_date: date
    status: Literal['enrolled','declined','not_eligible','pending','withdrawn']
    participation_documented: StrictBool = False
    @model_validator(mode='after')
    def valid(self):
        if self.index_date > today(): raise ValueError('Index date cannot be in the future')
        if self.status == 'enrolled' and not self.participation_documented: raise ValueError('Document participation under the approved protocol before marking enrolled')
        return self

class Visit(StrictModel):
    kind: Literal['visit']
    consultation_minutes: float | None = Field(default=None, gt=0, le=480, allow_inf_nan=False)
    timing_method: Literal['observed','estimated','not_recorded'] = 'not_recorded'
    decision_changed: Literal['yes','no','unknown'] = 'unknown'
    safety_screening: Literal['not_assessed','no_event_reported','event_reported'] = 'not_assessed'
    workflow_issue: Literal['none','duplicate_entry','slow','connectivity','missing_data','other','not_recorded'] = 'not_recorded'
    language: Literal['English','Kiswahili','other','not_recorded'] = 'not_recorded'
    helpfulness: int | None = Field(default=None, ge=1, le=5, strict=True)
    @model_validator(mode='after')
    def valid(self):
        if (self.consultation_minutes is None) != (self.timing_method == 'not_recorded'): raise ValueError('Provide both consultation time and its measurement method')
        return self

class Followup(StrictModel):
    kind: Literal['followup']
    contact_date: date
    status: Literal['completed','missed','unreachable','declined','died']
    systolic_bp: float | None = Field(default=None, ge=50, le=300, allow_inf_nan=False)
    diastolic_bp: float | None = Field(default=None, ge=30, le=200, allow_inf_nan=False)
    hba1c: float | None = Field(default=None, ge=3, le=25, allow_inf_nan=False)
    hospitalisation: Literal['yes','no','unknown'] = 'unknown'
    @model_validator(mode='after')
    def valid(self):
        if self.contact_date > today(): raise ValueError('Contact date cannot be in the future')
        if (self.systolic_bp is None) != (self.diastolic_bp is None): raise ValueError('Record both blood pressure values')
        if self.systolic_bp is not None and self.systolic_bp <= self.diastolic_bp: raise ValueError('Check systolic and diastolic values')
        if self.status != 'completed' and any(x is not None for x in [self.systolic_bp,self.diastolic_bp,self.hba1c]): raise ValueError('Measurements require a completed follow-up')
        return self

class Safety(StrictModel):
    kind: Literal['safety']
    incident_id: UUID
    occurred_on: date
    severity: Literal['near_miss','no_harm','mild','moderate','severe','death']
    category: Literal['unsafe_recommendation','missed_urgent_action','medication','delay','privacy','other']
    suspected_app_related: Literal['yes','no','unknown'] = 'unknown'
    description: str = Field(min_length=10, max_length=2000)
    immediate_action: str = Field(min_length=10, max_length=2000)
    status: Literal['open','resolved'] = 'open'
    @model_validator(mode='after')
    def valid(self):
        if self.occurred_on > today(): raise ValueError('Incident date cannot be in the future')
        return self

class DailyTally(StrictModel):
    kind: Literal['daily_tally']
    clinic_date: date
    eligible_visits: int = Field(ge=0,le=10000,strict=True)
    app_used_visits: int = Field(ge=0,le=10000,strict=True)
    non_use_connectivity: int = Field(default=0,ge=0,le=10000,strict=True)
    non_use_workload: int = Field(default=0,ge=0,le=10000,strict=True)
    non_use_declined: int = Field(default=0,ge=0,le=10000,strict=True)
    non_use_other: int = Field(default=0,ge=0,le=10000,strict=True)
    @model_validator(mode='after')
    def valid(self):
        if self.clinic_date > today(): raise ValueError('Clinic date cannot be in the future')
        total=self.app_used_visits+self.non_use_connectivity+self.non_use_workload+self.non_use_declined+self.non_use_other
        if total != self.eligible_visits: raise ValueError('App use plus reasons for non-use must equal all eligible visits')
        return self

Payload = Annotated[Enrolment | Visit | Followup | Safety | DailyTally, Field(discriminator='kind')]

class StudyRecordCreate(StrictModel):
    idempotency_key: UUID
    previous_id: UUID | None = None
    patient_id: UUID | None = None
    encounter_id: UUID | None = None
    synthetic: StrictBool
    payload: Payload
