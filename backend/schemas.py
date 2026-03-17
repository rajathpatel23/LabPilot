from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="New LabPilot Thread")


class MessageCreate(BaseModel):
    content: str
    data_path: str
    model_path: str
    top_k: int = 5
    use_llm: bool = False
    use_tavily: bool = False


class TrainingRunCreate(BaseModel):
    dataset_path: str
    target_column: str
    features: List[str] = Field(default_factory=list)
    output_name: str = "surrogate_api"


class ExperimentRunCreate(BaseModel):
    strategy: str
    dataset_path: str
    model_path: str
    budget: int = 20
    n_init: int = 3
    seed: int = 42
    reward_mode: str = "improvement"
    beta: float = 0.8
    linucb_alpha: float = 1.0
    linucb_lambda: float = 1.0


class RecommendationRequest(BaseModel):
    data_path: str
    model_path: str
    top_k: int = 5
    use_llm: bool = False


class EvidenceSearchRequest(BaseModel):
    query: str
    max_results: int = 5
    search_depth: str = "advanced"
    include_answer: str = "basic"
    focus_journals: List[str] = Field(default_factory=lambda: ["JACS", "Chemical Science"])


class RecommendationWithEvidenceRequest(BaseModel):
    data_path: str
    model_path: str
    top_k: int = 5
    use_llm: bool = False
    evidence_query: Optional[str] = None
    evidence_max_results: int = 5
    search_depth: str = "advanced"
    include_answer: str = "basic"
    focus_journals: List[str] = Field(default_factory=lambda: ["JACS", "Chemical Science"])


class SessionCreate(BaseModel):
    title: str = "LabPilot Session"
    conversation_id: Optional[str] = None
    dataset_path: str
    model_path: str
    budget: int = 20
    top_k: int = 5
    use_llm: bool = False
    use_tavily: bool = False


class SessionNextRequest(BaseModel):
    top_k: Optional[int] = None
    use_llm: Optional[bool] = None
    use_tavily: Optional[bool] = None


class SessionSubmitResultRequest(BaseModel):
    observed_yield: float
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    conditions: Dict[str, Any] = Field(default_factory=dict)
    recommendation_override: Optional[Dict[str, Any]] = None


class OptimizeStepRequest(BaseModel):
    """Submit last experiment result + get next recommendation in one call."""
    session_id: str
    observed_yield: float
    conditions: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    top_k: int = 5
    use_tavily: bool = False


class ComparisonSuiteRequest(BaseModel):
    dataset_path: str
    model_path: Optional[str] = None
    strategies: List[str] = Field(default_factory=lambda: ["random", "greedy", "adaptive", "contextual_linucb"])
    seeds: List[int] = Field(default_factory=lambda: [11, 22, 33])
    budget: int = 20
    n_init: int = 3
    reward_mode: str = "improvement"
    beta: float = 0.8
    linucb_alpha: float = 1.0
    linucb_lambda: float = 1.0


class RecommendationCandidate(BaseModel):
    rank: int
    predicted_yield: Optional[float] = None
    predicted_uncertainty: Optional[float] = None
    exploit_score: Optional[float] = None
    explore_bonus: Optional[float] = None
    ucb_score: Optional[float] = None
    conditions: Dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None


class RecommendationPayload(BaseModel):
    model_path: Optional[str] = None
    strategy: Optional[str] = None
    predicted_yield: Optional[float] = None
    predicted_uncertainty: Optional[float] = None
    next_experiment: Dict[str, Any] = Field(default_factory=dict)
    top_candidates: List[RecommendationCandidate] = Field(default_factory=list)
    ranked_candidates: List[RecommendationCandidate] = Field(default_factory=list)


class ReasoningPayload(BaseModel):
    summary: Optional[str] = None
    why_now: Optional[str] = None
    confidence: Optional[str] = None
    confidence_note: Optional[str] = None
    caution_note: Optional[str] = None
    cautionary_note: Optional[str] = None
    decision_rule_after_result: Optional[str] = None
    justification_source: Optional[str] = None


class EvidenceItem(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    score: Optional[float] = None
    matched_journals: List[str] = Field(default_factory=list)
    has_preferred_journal_hint: bool = False
    doi_hint: Optional[str] = None


class EvidencePayload(BaseModel):
    status: str = "unknown"
    query: str = ""
    answer: Optional[str] = None
    results: List[EvidenceItem] = Field(default_factory=list)
    message: Optional[str] = None


class RecommendationResponse(BaseModel):
    recommendation: RecommendationPayload
    reasoning: ReasoningPayload = Field(default_factory=ReasoningPayload)
    evidence: Optional[EvidencePayload] = None
    llm_error: Optional[str] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)


class LiteratureExplainRequest(BaseModel):
    query: str
    data_path: Optional[str] = None
    model_path: Optional[str] = None
    top_k: int = 3
    use_llm: bool = False
    max_results: int = 5
    search_depth: str = "advanced"
    include_answer: str = "basic"
    focus_journals: List[str] = Field(default_factory=lambda: ["JACS", "Chemical Science"])


class LiteratureRelevance(BaseModel):
    level: str = "medium"
    why_related: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


class LiteratureExplainResponse(BaseModel):
    query: str
    recommendation_context: Optional[RecommendationPayload] = None
    paper_summary: Optional[str] = None
    relevance: LiteratureRelevance = Field(default_factory=LiteratureRelevance)
    actionable_followups: List[str] = Field(default_factory=list)
    evidence: EvidencePayload = Field(default_factory=EvidencePayload)


class ApiMessage(BaseModel):
    id: str
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ApiConversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: Optional[List[ApiMessage]] = None

