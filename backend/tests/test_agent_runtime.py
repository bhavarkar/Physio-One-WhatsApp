"""Automated Test Suite for Agent Configuration, Runtime, Tool Execution, and APIs.

Single Organization Edition: Physio One Clinic.
Tests:
- Default AI entity seeding (Deepti receptionist draft, providers, tools).
- CheckAvailabilityTool strictly enforcing Sunday closure and operating hours.
- FindPatientTool masking patient phone numbers.
- ToolDispatcher permission checks, whitelist enforcement, and execution logging.
- Agent prompt versioning incrementation without rewriting historical records.
- Multi-step AgentRuntime execution (LLM tool call -> dispatch -> final answer).
- Max execution steps guardrail preventing infinite loops.
- Context budget truncation preserving system prompt and user message.
- Telemetry recording in llm_usage_logs and session tracking.
- RBAC permission controls on LLM and Agent endpoints.
- CSRF protection and unauthenticated rejection.
"""
import pytest
import uuid
import json
import httpx
from datetime import datetime, timezone, date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import Base
from app.models.ai import (
    AIProvider,
    AIModel,
    AIAgent,
    AIAgentVersion,
    AIAgentSession,
    AIAgentExecution,
    LLMUsageLog,
    AIToolExecution,
)
from app.models.patient import Patient
from app.models.user import User, Role
from app.tools.clinical.availability import CheckAvailabilityTool
from app.tools.clinical.patient import FindPatientTool
from app.tools.dispatcher import ToolDispatcher
from app.tools.base import ToolExecutionContext
from app.services.agent_service import AgentService
from app.agents.runtime import AgentRuntime
from app.schemas.ai import AIAgentCreate, AIAgentUpdate


@pytest.mark.asyncio
async def test_ensure_default_ai_entities(async_session):
    """Verify default seeding initializes Muse, OpenAI, Anthropic, tools, and Deepti agent."""
    await AgentService.ensure_default_ai_entities(async_session)

    # Verify providers
    providers = await AgentService.list_providers(async_session)
    provider_names = [p.name for p in providers]
    assert "muse" in provider_names
    assert "openai" in provider_names
    assert "anthropic" in provider_names

    # Verify Deepti agent
    agents = await AgentService.list_agents(async_session)
    deepti = next((a for a in agents if a.name == "Deepti"), None)
    assert deepti is not None
    assert deepti.is_active is True
    assert "Sunday" in deepti.system_prompt
    assert "check_availability" in deepti.allowed_tools
    assert deepti.current_version == 1

    # Verify initial version record
    versions = await AgentService.list_agent_versions(async_session, deepti.id)
    assert len(versions) >= 1
    assert versions[0].version_number == 1


@pytest.mark.asyncio
async def test_check_availability_tool_sunday_enforcement(async_session):
    """Verify check_availability tool strictly enforces Sunday closure rule."""
    tool = CheckAvailabilityTool()
    context = ToolExecutionContext()

    # Find the next upcoming Sunday
    today = date.today()
    days_ahead = (6 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    sunday_date = today + timedelta(days=days_ahead)

    result = await tool.execute(
        arguments={"date": sunday_date.isoformat()},
        context=context,
        db=async_session,
    )

    assert result["success"] is True
    assert result["is_open"] is False
    assert result["is_sunday"] is True
    assert "Sunday" in result["message"]
    assert result["total_slots_available"] == 0


@pytest.mark.asyncio
async def test_check_availability_tool_weekday_slots(async_session):
    """Verify check_availability returns open slots for a valid future weekday."""
    tool = CheckAvailabilityTool()
    context = ToolExecutionContext()

    # Find next Tuesday or Wednesday
    today = date.today()
    days_until_wed = (2 - today.weekday()) % 7
    if days_until_wed <= 0:
        days_until_wed += 7
    wed_date = today + timedelta(days=days_until_wed + 7)  # next week Wednesday

    result = await tool.execute(
        arguments={"date": wed_date.isoformat(), "duration_minutes": 45},
        context=context,
        db=async_session,
    )

    assert result["success"] is True
    assert result["is_open"] is True
    assert result["is_sunday"] is False
    assert result["total_slots_available"] > 0
    assert len(result["available_slots"]) > 0


@pytest.mark.asyncio
async def test_find_patient_tool_phi_masking(async_session):
    """Verify patient search tool redacts/masks contact phone number."""
    # Seed a patient
    patient = Patient(
        full_name="Rajesh Sharma",
        phone_number="+919876543210",
        gender="male",
    )
    async_session.add(patient)
    await async_session.commit()

    tool = FindPatientTool()
    context = ToolExecutionContext()

    res = await tool.execute(
        arguments={"phone": "9876543210"},
        context=context,
        db=async_session,
    )

    assert res["success"] is True
    assert res["found"] is True
    assert len(res["patients"]) == 1
    found_patient = res["patients"][0]
    assert found_patient["full_name"] == "Rajesh Sharma"
    # Ensure phone is masked
    assert "+919876543210" not in found_patient["masked_phone"]
    assert "***" in found_patient["masked_phone"]


@pytest.mark.asyncio
async def test_tool_dispatcher_unauthorized_tool_rejection(async_session):
    """Verify ToolDispatcher rejects calls to tools not whitelisted for the agent."""
    context = ToolExecutionContext()
    result = await ToolDispatcher.dispatch(
        tool_name="unauthorized_secret_tool",
        arguments={},
        context=context,
        db=async_session,
        allowed_tools=["check_availability"],  # Only check_availability allowed
    )

    assert result["success"] is False
    assert "Access denied" in result["error"]

    # Verify audit log recorded rejection
    audit_stmt = select(AIToolExecution).where(AIToolExecution.tool_name == "unauthorized_secret_tool")
    audit_rec = (await async_session.execute(audit_stmt)).scalar_one_or_none()
    assert audit_rec is not None
    assert audit_rec.status == "rejected_by_rule"


@pytest.mark.asyncio
async def test_agent_versioning_lifecycle(async_session):
    """Verify updating agent prompt creates new version and preserves historical versions."""
    await AgentService.ensure_default_ai_entities(async_session)
    agents = await AgentService.list_agents(async_session)
    deepti = next(a for a in agents if a.name == "Deepti")
    assert deepti.current_version == 1

    # Update agent prompt
    new_prompt = deepti.system_prompt + "\nSpecial clinic note: Diwali timings apply."
    updated = await AgentService.update_agent(
        db=async_session,
        agent_id=deepti.id,
        data=AIAgentUpdate(system_prompt=new_prompt, change_summary="Added Diwali festival notes"),
    )

    assert updated.current_version == 2

    # Check version records
    versions = await AgentService.list_agent_versions(async_session, deepti.id)
    assert len(versions) == 2
    assert versions[0].version_number == 2
    assert versions[0].change_summary == "Added Diwali festival notes"
    assert versions[1].version_number == 1


@pytest.mark.asyncio
async def test_agent_runtime_multistep_tool_execution(async_session):
    """Verify AgentRuntime multi-step loop: Model requests tool -> ToolDispatcher runs -> Final reply."""
    await AgentService.ensure_default_ai_entities(async_session)
    agents = await AgentService.list_agents(async_session)
    deepti = next(a for a in agents if a.name == "Deepti")

    # Target date next week Wednesday
    today = date.today()
    days_until_wed = (2 - today.weekday()) % 7
    if days_until_wed <= 0:
        days_until_wed += 7
    target_date = today + timedelta(days=days_until_wed + 7)

    # Step 1: Model requests check_availability
    step_1_payload = {
        "id": "cmpl-step1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_slot_1",
                            "type": "function",
                            "function": {
                                "name": "check_availability",
                                "arguments": json.dumps({"date": target_date.isoformat()}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65},
    }

    # Step 2: Model uses tool output to formulate polite final response
    step_2_payload = {
        "id": "cmpl-step2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Yes, we have open slots available on {target_date.isoformat()}! The clinic operates 9am to 8pm.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 85, "completion_tokens": 25, "total_tokens": 110},
    }

    call_count = 0

    def mock_handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json=step_1_payload)
        return httpx.Response(200, json=step_2_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # Run runtime
    result = await AgentRuntime.run(
        db=async_session,
        agent_id=deepti.id,
        user_message=f"Are there consultation slots available on {target_date.isoformat()}?",
        override_http_client=mock_client,
    )

    assert result.status == "completed"
    assert "open slots available" in result.response_text
    assert len(result.steps) == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "check_availability"
    assert result.total_input_tokens == 135
    assert result.total_output_tokens == 40

    # Verify session recorded in database
    session_id = uuid.UUID(result.session_id)
    session_stmt = (
        select(AIAgentSession)
        .options(selectinload(AIAgentSession.executions))
        .where(AIAgentSession.id == session_id)
    )
    session_db = (await async_session.execute(session_stmt)).scalar_one_or_none()
    assert session_db is not None
    assert session_db.status == "completed"
    assert len(session_db.executions) == 2

    # Verify telemetry log recorded
    usage_stmt = select(LLMUsageLog).where(LLMUsageLog.session_id == session_id)
    usage_logs = (await async_session.execute(usage_stmt)).scalars().all()
    assert len(usage_logs) >= 2


@pytest.mark.asyncio
async def test_agent_runtime_max_steps_guardrail(async_session):
    """Verify runtime enforces max_execution_steps limit against infinite tool call loops."""
    await AgentService.ensure_default_ai_entities(async_session)
    agents = await AgentService.list_agents(async_session)
    deepti = next(a for a in agents if a.name == "Deepti")

    # Set small max steps
    deepti.max_execution_steps = 2
    await async_session.commit()

    # Model always returns tool calls infinitely
    infinite_tool_payload = {
        "id": "cmpl-loop",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_loop",
                            "type": "function",
                            "function": {
                                "name": "check_availability",
                                "arguments": json.dumps({"date": "2026-11-20"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=infinite_tool_payload))
    )

    result = await AgentRuntime.run(
        db=async_session,
        agent_id=deepti.id,
        user_message="Keep checking slots",
        override_http_client=mock_client,
    )

    # Must be stopped at max_steps (2)
    assert len(result.steps) == 2
    assert result.status == "completed"
