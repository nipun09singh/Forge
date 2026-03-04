"""CodeFusionAI — API Server"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from main import build_agency

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("codefusionai-api")


class TaskRequest(BaseModel):
    """Request to execute a task."""
    task: str
    team: str | None = None
    context: dict | None = None
    use_planner: bool = False


class TaskResponse(BaseModel):
    """Response from task execution."""
    success: bool
    output: str
    data: dict = {}


class PlanRequest(BaseModel):
    """Request to plan a task (without executing)."""
    task: str
    context: dict | None = None


class ScheduleRequest(BaseModel):
    """Request to create a scheduled task."""
    name: str
    task: str
    team: str = ""
    interval_seconds: int = 3600


class MemorySearchRequest(BaseModel):
    """Request to search agency memory."""
    keyword: str = ""
    tag: str = ""
    limit: int = 20


_agency = None
_event_log = None


def _get_api_key():
    """Get the configured API key (None = auth disabled)."""
    return os.getenv("AGENCY_API_KEY", "")


async def verify_api_key(authorization: str = Header(default="", alias="Authorization")):
    """Verify API key from Authorization: Bearer <key> header."""
    expected = _get_api_key()
    if not expected:
        return  # Auth disabled if no key configured

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Authorization: Bearer <your-api-key>")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization format. Use: Authorization: Bearer <your-api-key>")

    if parts[1] != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agency, _event_log
    _agency, _event_log = build_agency()
    logger.info(f"Agency '{_agency.name}' started")
    await _agency.scheduler.start()
    yield
    await _agency.scheduler.stop()
    logger.info("Agency shutting down")


app = FastAPI(
    title="CodeFusionAI API",
    description="CodeFusionAI is an AI-powered software development agency that leverages machine learning to write code, run tests, and deploy applications far more efficiently than human teams, offering game-changing cost savings and speed for businesses of all sizes.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/api/task", response_model=TaskResponse, dependencies=[Depends(verify_api_key)])
async def execute_task(request: TaskRequest):
    """Execute a task through the agency."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    
    result = await _agency.execute(
        task=request.task,
        team_name=request.team,
        context=request.context,
        use_planner=request.use_planner,
    )
    return TaskResponse(
        success=result.success,
        output=result.output,
        data=result.data if hasattr(result, 'data') else {},
    )


@app.post("/api/plan", dependencies=[Depends(verify_api_key)])
async def plan_task(request: PlanRequest):
    """Plan a complex task (decompose into steps without executing)."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    
    plan = await _agency.planner.plan(request.task, request.context)
    return {
        "plan_id": plan.id,
        "task": plan.task,
        "steps": [
            {
                "id": s.id,
                "description": s.description,
                "assigned_team": s.assigned_team,
                "depends_on": s.depends_on,
                "status": s.status.value,
            }
            for s in plan.steps
        ],
        "summary": plan.to_summary(),
    }


@app.post("/api/plan/{plan_id}/execute", dependencies=[Depends(verify_api_key)])
async def execute_plan(plan_id: str):
    """Execute a previously created plan."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    
    plan = _agency.planner._active_plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    result = await _agency.planner.execute_plan(plan)
    return result


@app.get("/api/status", dependencies=[Depends(verify_api_key)])
async def get_status():
    """Get agency status including all teams, agents, and metrics."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    
    status = _agency.get_status()
    costs = _event_log.cost_tracker.get_summary() if _event_log else {}
    events_summary = _event_log.get_summary() if _event_log else {}

    return {
        **status,
        "costs": costs,
        "events": events_summary,
    }


@app.get("/api/events", dependencies=[Depends(verify_api_key)])
async def get_events(trace_id: str = "", agent: str = "", limit: int = 100):
    """Get recent observable events (LLM calls, tool uses, errors)."""
    if not _event_log:
        raise HTTPException(status_code=503, detail="Event log not initialized")
    
    events = _event_log.events[-limit:]
    if trace_id:
        events = [e for e in events if e.trace_id == trace_id]
    if agent:
        events = [e for e in events if e.agent_name == agent]

    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
    }


@app.get("/api/costs", dependencies=[Depends(verify_api_key)])
async def get_costs():
    """Get cost tracking summary — tokens used, estimated $ cost, per-agent breakdown."""
    if not _event_log:
        raise HTTPException(status_code=503, detail="Event log not initialized")
    
    return _event_log.cost_tracker.get_summary()


@app.post("/api/memory/search", dependencies=[Depends(verify_api_key)])
async def search_memory(request: MemorySearchRequest):
    """Search the agency's persistent memory."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    
    results = _agency.memory.search_keyword(request.keyword, limit=request.limit)
    return {"results": results, "count": len(results)}


@app.post("/api/memory/store", dependencies=[Depends(verify_api_key)])
async def store_memory(key: str, value: str, tags: str = ""):
    """Store a value in agency memory."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    _agency.memory.store(key, value, author="api", tags=tag_list)
    return {"success": True, "key": key}


from fastapi.responses import StreamingResponse as FastAPIStreamingResponse
import json as _json

@app.post("/api/task/stream", dependencies=[Depends(verify_api_key)])
async def stream_task(request: TaskRequest):
    """Execute a task with streaming response (Server-Sent Events)."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")

    async def event_stream():
        # Pick first team's first agent for streaming
        agent = None
        if request.team and request.team in _agency.teams:
            team = _agency.teams[request.team]
            agent = team.lead or (team.agents[0] if team.agents else None)
        else:
            for team in _agency.teams.values():
                agent = team.lead or (team.agents[0] if team.agents else None)
                if agent:
                    break

        if not agent:
            yield f"data: {_json.dumps({'error': 'No agent available'})}\n\n"
            return

        async for chunk in agent.execute_stream(request.task, request.context):
            yield f"data: {_json.dumps({'delta': chunk.delta, 'done': chunk.done, 'full_text': chunk.full_text if chunk.done else ''})}\n\n"

    return FastAPIStreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/schedules", dependencies=[Depends(verify_api_key)])
async def create_schedule(request: ScheduleRequest):
    """Create a recurring scheduled task."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")

    from forge.runtime.scheduler import TaskSchedule
    schedule = TaskSchedule(
        name=request.name,
        task=request.task,
        team=request.team,
        interval_seconds=request.interval_seconds,
    )
    sid = _agency.scheduler.add(schedule)
    return {"id": sid, "name": request.name, "interval_seconds": request.interval_seconds}


@app.get("/api/schedules", dependencies=[Depends(verify_api_key)])
async def list_schedules():
    """List all scheduled tasks."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    return {"schedules": _agency.scheduler.list_schedules()}


@app.delete("/api/schedules/{schedule_id}", dependencies=[Depends(verify_api_key)])
async def delete_schedule(schedule_id: str):
    """Delete a scheduled task."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    if _agency.scheduler.remove(schedule_id):
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Schedule not found")


# ═══════════════════════════════════════════════════════════
# Revenue & Analytics Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/api/analytics/revenue", dependencies=[Depends(verify_api_key)])
async def get_revenue():
    """Get revenue tracking and ROI summary."""
    if not _agency or not hasattr(_agency, '_revenue_tracker'):
        return {"total_value_generated_usd": 0, "message": "Revenue tracking not initialized"}
    
    cost = _event_log.cost_tracker.total_cost_usd if _event_log else 0
    return _agency._revenue_tracker.get_roi_summary(agency_cost_usd=cost)


@app.get("/api/analytics/predictions", dependencies=[Depends(verify_api_key)])
async def get_predictions():
    """Get failure prediction statistics."""
    if not _agency or not hasattr(_agency, '_failure_predictor'):
        return {"message": "Failure predictor not initialized"}
    return {
        "predictor": repr(_agency._failure_predictor),
        "agents_tracked": len(_agency._failure_predictor._task_history),
    }


@app.get("/api/analytics/model-routing", dependencies=[Depends(verify_api_key)])
async def get_model_routing():
    """Get smart model routing statistics and cost savings."""
    if not _agency or not hasattr(_agency, '_model_router'):
        return {"message": "Model routing not initialized"}
    return _agency._model_router.get_stats()


# ═══════════════════════════════════════════════════════════
# Customer Communication Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/api/customer/satisfaction", dependencies=[Depends(verify_api_key)])
async def get_satisfaction(customer_id: str = ""):
    """Get customer satisfaction scores (CSAT)."""
    if not _agency or not hasattr(_agency, '_customer_comms'):
        return {"csat_score": 0, "message": "Customer comms not initialized"}
    return _agency._customer_comms.get_satisfaction_score(customer_id)


class FeedbackRequest(BaseModel):
    customer_id: str
    task_id: str = ""
    agent_name: str = ""
    rating: int = 0
    sentiment: str = ""
    comment: str = ""


@app.post("/api/customer/feedback", dependencies=[Depends(verify_api_key)])
async def submit_feedback(request: FeedbackRequest):
    """Submit customer feedback on agent performance."""
    if not _agency or not hasattr(_agency, '_customer_comms'):
        raise HTTPException(status_code=503, detail="Customer comms not initialized")
    
    from forge.runtime.customer_comms import CustomerFeedback
    feedback = CustomerFeedback(
        customer_id=request.customer_id,
        task_id=request.task_id,
        agent_name=request.agent_name,
        rating=request.rating,
        sentiment=request.sentiment,
        comment=request.comment,
    )
    _agency._customer_comms.collect_feedback(feedback)
    return {"received": True, "feedback_id": feedback.id}


@app.get("/api/customer/notifications", dependencies=[Depends(verify_api_key)])
async def get_notifications(customer_id: str = "", limit: int = 50):
    """Get notification history."""
    if not _agency or not hasattr(_agency, '_customer_comms'):
        return {"notifications": []}
    return {"notifications": _agency._customer_comms.get_notifications(customer_id, limit)}


# ═══════════════════════════════════════════════════════════
# Checkpointing Endpoints
# ═══════════════════════════════════════════════════════════

@app.post("/api/checkpoint", dependencies=[Depends(verify_api_key)])
async def create_checkpoint():
    """Create a checkpoint of the entire agency state."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    try:
        cp_id = _agency.checkpoint()
        return {"checkpoint_id": cp_id, "success": True}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}


@app.get("/api/checkpoints", dependencies=[Depends(verify_api_key)])
async def list_checkpoints(limit: int = 20):
    """List available checkpoints."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    return {"checkpoints": _agency.list_checkpoints(limit=limit)}


@app.post("/api/restore/{checkpoint_id}", dependencies=[Depends(verify_api_key)])
async def restore_checkpoint(checkpoint_id: str):
    """Restore agency state from a checkpoint."""
    if not _agency:
        raise HTTPException(status_code=503, detail="Agency not initialized")
    try:
        success = _agency.restore(checkpoint_id)
        return {"restored": success, "checkpoint_id": checkpoint_id}
    except RuntimeError as e:
        return {"restored": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
# Negotiation Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/api/negotiations", dependencies=[Depends(verify_api_key)])
async def get_negotiations(limit: int = 20):
    """Get negotiation history."""
    if not _agency or not hasattr(_agency, '_negotiation_engine'):
        return {"negotiations": []}
    return {"negotiations": _agency._negotiation_engine.get_history(limit)}


# ═══════════════════════════════════════════════════════════
# A/B Testing Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/api/experiments", dependencies=[Depends(verify_api_key)])
async def get_experiments():
    """Get A/B test results."""
    if not _agency or not hasattr(_agency, '_ab_test_manager'):
        return {"active": [], "completed": []}
    return {
        "active": _agency._ab_test_manager.get_active_tests(),
        "completed": _agency._ab_test_manager.get_completed_tests(),
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "agency": "codefusionai",
        "agents": len(_agency.get_status()["teams"]) if _agency else 0,
    }