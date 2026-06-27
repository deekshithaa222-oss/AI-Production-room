from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentState(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"


class InvestigationState(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"


class InvestigationRequest(BaseModel):
    description: str = Field(..., min_length=3)


class AgentResult(BaseModel):
    name: str
    status: AgentState = AgentState.pending
    summary: str = ""
    findings: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class RootCauseScore(BaseModel):
    hypothesis: str
    score: int
    reasons: List[str]


class IncidentReport(BaseModel):
    summary: str
    root_cause: str
    evidence: List[str]
    immediate_actions: List[str]
    long_term_recommendations: List[str]
    human_approval_required: bool = True


class Investigation(BaseModel):
    id: str
    description: str
    status: InvestigationState
    progress: int
    agents: List[AgentResult]
    evidence: Dict[str, Any] = Field(default_factory=dict)
    scores: List[RootCauseScore] = Field(default_factory=list)
    report: Optional[IncidentReport] = None

