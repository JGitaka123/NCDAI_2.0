from typing import Literal
from uuid import UUID
from pydantic import Field, StrictBool
from .schemas import StrictModel


class ConsultationCreate(StrictModel):
    idempotency_key: UUID
    expected_version: int = Field(ge=1)
    assessment_id: str = Field(min_length=1,max_length=100)
    recommendation_ids: list[str] = Field(min_length=1,max_length=30)
    reason_category: Literal['disagreement','uncertainty','dose_question','outside_scope','other']
    question: str = Field(min_length=10,max_length=4000)
    immediate_action: str = Field(min_length=10,max_length=4000)


class OpinionCreate(StrictModel):
    snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    agreement: Literal['agree','partly_agree','disagree','insufficient_information']
    assessment: str = Field(min_length=10,max_length=6000)
    recommended_action: str = Field(min_length=10,max_length=6000)
    rationale: str = Field(min_length=10,max_length=6000)
    urgency: Literal['routine','soon','urgent','emergency']
    source_references: str = Field(min_length=3,max_length=4000)


class DispositionCreate(StrictModel):
    opinion_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_encounter_version: int = Field(ge=1)
    action: Literal['accepted','modified','not_followed']
    action_taken: str = Field(min_length=10,max_length=6000)
    stale_snapshot_acknowledged: StrictBool = False
