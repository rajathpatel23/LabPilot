from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi import File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .db import ensure_db
from .schemas import (
    ApiConversation,
    ApiMessage,
    ComparisonSuiteRequest,
    ConversationCreate,
    EvidenceSearchRequest,
    ExperimentRunCreate,
    MessageCreate,
    LiteratureExplainRequest,
    LiteratureExplainResponse,
    RecommendationRequest,
    RecommendationResponse,
    RecommendationWithEvidenceRequest,
    SessionCreate,
    SessionNextRequest,
    SessionSubmitResultRequest,
    OptimizeStepRequest,
    TrainingRunCreate,
)
from .service import (
    create_session,
    create_conversation,
    create_experiment_run,
    create_training_run,
    get_conversation,
    get_dataset,
    get_dataset_models,
    get_experiment_run,
    get_session_state,
    get_training_run,
    list_conversations,
    list_datasets,
    list_experiment_runs,
    list_messages,
    list_sessions,
    list_training_runs,
    get_evaluation_snapshot,
    get_latest_comparison_suite,
    register_dataset,
    run_recommendation_with_evidence,
    run_recommendation_with_reasoning,
    explain_literature_relevance,
    session_next_recommendation,
    session_submit_result,
    search_literature_evidence,
    run_agent_turn,
    run_comparison_suite,
)


# Auto-load project .env so API keys (TAVILY_API_KEY, LLM keys) are available in backend routes.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(title="LabPilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_db()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/datasets/upload")
async def api_upload_dataset(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name missing.")
    allowed = {".csv", ".xlsx", ".xls"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail="Only CSV/XLSX/XLS files are supported.")

    upload_dir = Path(__file__).resolve().parent.parent / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid4().hex}_{Path(file.filename).name}"
    out_path = upload_dir / safe_name
    content = await file.read()
    out_path.write_bytes(content)

    # Register in dataset registry with column metadata
    ds = register_dataset(
        original_filename=file.filename,
        stored_path=str(out_path),
        size_bytes=len(content),
    )
    return {
        "filename": file.filename,
        "stored_path": str(out_path),
        "size_bytes": len(content),
        "dataset": ds,
    }


@app.get("/api/datasets")
def api_list_datasets() -> list[dict]:
    return list_datasets()


@app.get("/api/datasets/{dataset_id}")
def api_get_dataset(dataset_id: str) -> dict:
    ds = get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return ds


@app.get("/api/datasets/{dataset_id}/models")
def api_get_dataset_models(dataset_id: str) -> list[dict]:
    ds = get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return get_dataset_models(dataset_id)


@app.post("/api/conversations", response_model=ApiConversation)
def api_create_conversation(body: ConversationCreate) -> ApiConversation:
    row = create_conversation(body.title)
    return ApiConversation(**row)


@app.get("/api/conversations", response_model=list[ApiConversation])
def api_list_conversations() -> list[ApiConversation]:
    return [ApiConversation(**row) for row in list_conversations()]


@app.get("/api/conversations/{conversation_id}", response_model=ApiConversation)
def api_get_conversation(conversation_id: str) -> ApiConversation:
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = [ApiMessage(**m) for m in list_messages(conversation_id)]
    return ApiConversation(**conv, messages=messages)


@app.get("/api/conversations/{conversation_id}/messages", response_model=list[ApiMessage])
def api_list_messages(conversation_id: str) -> list[ApiMessage]:
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return [ApiMessage(**m) for m in list_messages(conversation_id)]


@app.post("/api/conversations/{conversation_id}/messages", response_model=ApiMessage)
def api_post_message(conversation_id: str, body: MessageCreate) -> ApiMessage:
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    msg = run_agent_turn(
        conversation_id=conversation_id,
        user_text=body.content,
        data_path=body.data_path,
        model_path=body.model_path,
        top_k=body.top_k,
        use_llm=body.use_llm,
        use_tavily=body.use_tavily,
    )
    return ApiMessage(**msg)


@app.post("/api/training/runs")
def api_create_training_run(body: TrainingRunCreate) -> dict:
    return create_training_run(
        dataset_path=body.dataset_path,
        target_column=body.target_column,
        features=body.features,
        output_name=body.output_name,
    )


@app.get("/api/training/runs")
def api_list_training_runs() -> list[dict]:
    return list_training_runs()


@app.get("/api/training/runs/{run_id}")
def api_get_training_run(run_id: str) -> dict:
    run = get_training_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found.")
    return run


@app.post("/api/experiments/runs")
def api_create_experiment_run(body: ExperimentRunCreate) -> dict:
    return create_experiment_run(
        strategy=body.strategy,
        dataset_path=body.dataset_path,
        model_path=body.model_path,
        budget=body.budget,
        n_init=body.n_init,
        seed=body.seed,
        reward_mode=body.reward_mode,
        beta=body.beta,
        linucb_alpha=body.linucb_alpha,
        linucb_lambda=body.linucb_lambda,
    )


@app.post("/api/recommendations/next", response_model=RecommendationResponse)
def api_recommend_next(body: RecommendationRequest) -> RecommendationResponse:
    return run_recommendation_with_reasoning(
        data_path=body.data_path,
        model_path=body.model_path,
        top_k=body.top_k,
        use_llm=body.use_llm,
    )


@app.post("/api/recommendations/next_with_evidence", response_model=RecommendationResponse)
def api_recommend_next_with_evidence(body: RecommendationWithEvidenceRequest) -> RecommendationResponse:
    return run_recommendation_with_evidence(
        data_path=body.data_path,
        model_path=body.model_path,
        top_k=body.top_k,
        use_llm=body.use_llm,
        evidence_query=body.evidence_query,
        evidence_max_results=body.evidence_max_results,
        search_depth=body.search_depth,
        include_answer=body.include_answer,
        focus_journals=body.focus_journals,
    )


@app.post("/api/evidence/search")
def api_evidence_search(body: EvidenceSearchRequest) -> dict:
    return search_literature_evidence(
        query=body.query,
        max_results=body.max_results,
        search_depth=body.search_depth,
        include_answer=body.include_answer,
        focus_journals=body.focus_journals,
    )


@app.post("/api/literature/explain", response_model=LiteratureExplainResponse)
def api_literature_explain(body: LiteratureExplainRequest) -> LiteratureExplainResponse:
    return explain_literature_relevance(
        query=body.query,
        data_path=body.data_path,
        model_path=body.model_path,
        top_k=body.top_k,
        use_llm=body.use_llm,
        max_results=body.max_results,
        search_depth=body.search_depth,
        include_answer=body.include_answer,
        focus_journals=body.focus_journals,
    )


@app.post("/api/sessions")
def api_create_session(body: SessionCreate) -> dict:
    return create_session(
        title=body.title,
        conversation_id=body.conversation_id,
        dataset_path=body.dataset_path,
        model_path=body.model_path,
        budget=body.budget,
        top_k=body.top_k,
        use_llm=body.use_llm,
        use_tavily=body.use_tavily,
    )


@app.get("/api/sessions")
def api_list_sessions() -> list[dict]:
    return list_sessions()


@app.post("/api/sessions/{session_id}/next")
def api_session_next(session_id: str, body: SessionNextRequest) -> dict:
    try:
        return session_next_recommendation(
            session_id=session_id,
            top_k=body.top_k,
            use_llm=body.use_llm,
            use_tavily=body.use_tavily,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e


@app.post("/api/sessions/{session_id}/submit-result")
def api_session_submit_result(session_id: str, body: SessionSubmitResultRequest) -> dict:
    try:
        return session_submit_result(
            session_id=session_id,
            observed_yield=body.observed_yield,
            notes=body.notes,
            metadata=body.metadata,
            conditions=body.conditions,
            recommendation_override=body.recommendation_override,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e


@app.get("/api/sessions/{session_id}/state")
def api_session_state(session_id: str) -> dict:
    state = get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")
    return state


@app.get("/api/experiments/runs")
def api_list_experiment_runs() -> list[dict]:
    return list_experiment_runs()


@app.get("/api/experiments/runs/{run_id}")
def api_get_experiment_run(run_id: str) -> dict:
    run = get_experiment_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Experiment run not found.")
    return run


@app.post("/api/optimize/step")
def api_optimize_step(body: OptimizeStepRequest) -> dict:
    """Submit last experiment outcome + get next ranked recommendations in one call."""
    from .service import optimize_step
    try:
        return optimize_step(
            session_id=body.session_id,
            observed_yield=body.observed_yield,
            conditions=body.conditions,
            notes=body.notes,
            top_k=body.top_k,
            use_tavily=body.use_tavily,
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e


@app.get("/api/optimize/session/{session_id}")
def api_optimize_session_state(session_id: str) -> dict:
    """Full optimization state: session info, history, feature columns, next recommendations."""
    from .service import get_optimize_state
    state = get_optimize_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")
    return state


@app.get("/api/evaluation/snapshot")
def api_evaluation_snapshot() -> dict:
    return get_evaluation_snapshot()


@app.post("/api/evaluation/compare-suite")
def api_run_comparison_suite(body: ComparisonSuiteRequest) -> dict:
    try:
        return run_comparison_suite(
            dataset_path=body.dataset_path,
            model_path=body.model_path,
            strategies=body.strategies,
            seeds=body.seeds,
            budget=body.budget,
            n_init=body.n_init,
            reward_mode=body.reward_mode,
            beta=body.beta,
            linucb_alpha=body.linucb_alpha,
            linucb_lambda=body.linucb_lambda,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/evaluation/compare-suite/latest")
def api_latest_comparison_suite() -> dict:
    latest = get_latest_comparison_suite()
    if not latest:
        raise HTTPException(status_code=404, detail="No comparison suite artifact found yet.")
    return latest

