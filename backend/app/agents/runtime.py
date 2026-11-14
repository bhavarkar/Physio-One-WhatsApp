"""AI Agent Execution Runtime.

Single Organization Edition: Physio One Clinic.
Coordinates context staging, token budget enforcement, LLM Gateway calls,
multi-step tool dispatching, execution safety, and comprehensive session audit logging.
"""
import asyncio
import time
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.ai import (
    AIAgent,
    AIAgentVersion,
    AIAgentSession,
    AIAgentExecution,
)
from app.llm.gateway import LLMGateway
from app.llm.schemas import (
    ChatMessage,
    MessageRole,
    LLMOptions,
    ToolCall,
)
from app.llm.errors import LLMError
from app.tools.base import ToolExecutionContext
from app.tools.registry import ToolRegistry
from app.tools.dispatcher import ToolDispatcher
from app.services.retrieval_service import RetrievalService
from app.services.memory_service import MemoryService

logger = logging.getLogger("physio_one.agent.runtime")


class AgentRunResult(BaseModel):
    """Normalized structured outcome of an agent execution session."""
    session_id: str
    agent_id: str
    agent_name: str
    status: str  # completed, failed, cancelled
    response_text: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    rag_sources: List[Dict[str, Any]] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    model: str = ""
    provider: str = ""
    error_message: Optional[str] = None


class AgentRuntime:
    """Controlled multi-step AI Agent execution engine."""

    @classmethod
    async def run(
        cls,
        db: AsyncSession,
        agent_id: uuid.UUID,
        user_message: str,
        conversation_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        caller_permissions: Optional[List[str]] = None,
        history_messages: Optional[List[ChatMessage]] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
        allow_fallback: bool = False,
        override_http_client: Optional[Any] = None,
    ) -> AgentRunResult:
        """Execute agent runtime session."""
        start_time = time.perf_counter()

        # 1. Load Agent Configuration
        agent_stmt = (
            select(AIAgent)
            .options(
                selectinload(AIAgent.primary_model),
                selectinload(AIAgent.fallback_model),
                selectinload(AIAgent.versions),
            )
            .where(AIAgent.id == agent_id)
        )
        agent = (await db.execute(agent_stmt)).scalar_one_or_none()
        if not agent:
            raise ValueError(f"Agent with ID '{agent_id}' does not exist.")

        if not agent.is_active:
            raise ValueError(f"Agent '{agent.name}' is currently disabled.")

        # Find latest version ID
        latest_version = max(agent.versions, key=lambda v: v.version_number) if agent.versions else None
        agent_version_id = latest_version.id if latest_version else None

        # 2. Create Initial Session Record
        session = AIAgentSession(
            agent_id=agent.id,
            agent_version_id=agent_version_id,
            conversation_id=conversation_id,
            status="running",
            session_metadata=session_metadata or {},
            total_input_tokens=0,
            total_output_tokens=0,
            total_execution_steps=0,
            started_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()

        # 3. Resolve Provider Adapters
        try:
            primary_adapter, primary_model_ident = await LLMGateway.resolve_adapter_for_model(
                db=db,
                model_id=agent.primary_model_id,
                override_http_client=override_http_client,
            )

            fallback_adapter = None
            fallback_model_ident = None
            if agent.fallback_model_id and allow_fallback:
                fallback_adapter, fallback_model_ident = await LLMGateway.resolve_adapter_for_model(
                    db=db,
                    model_id=agent.fallback_model_id,
                    override_http_client=override_http_client,
                )
        except Exception as e:
            session.status = "failed"
            session.error_message = f"Failed to initialize LLM provider: {str(e)}"
            session.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise

        # 4. Context Assembly and Deterministic Budget Truncation
        # Always preserve System Prompt and Current User Message
        system_msg = ChatMessage(role=MessageRole.SYSTEM, content=agent.system_prompt)
        current_user_msg = ChatMessage(role=MessageRole.USER, content=user_message)

        # Estimate tokens roughly (1 token ~ 3.5 chars)
        def estimate_tokens(text: Optional[str]) -> int:
            return max(1, len(text or "") // 3)

        sys_tokens = estimate_tokens(agent.system_prompt)
        user_tokens = estimate_tokens(user_message)
        context_budget = agent.context_budget_tokens or 4000
        available_history_budget = max(0, context_budget - sys_tokens - user_tokens - 200)

        truncated_history: List[ChatMessage] = []
        if history_messages:
            accumulated_history_tokens = 0
            # Walk backwards from most recent message
            for h in reversed(history_messages):
                h_tok = estimate_tokens(h.content)
                if accumulated_history_tokens + h_tok <= available_history_budget:
                    truncated_history.insert(0, h)
                    accumulated_history_tokens += h_tok
                else:
                    break

        conversation_staging: List[ChatMessage] = [system_msg] + truncated_history + [current_user_msg]

        # Staging RAG Context & Patient Memory
        retrieved_rag_sources: List[Dict[str, Any]] = []

        # 1. Clinic Knowledge Retrieval (if agent has knowledge_base_id and rag_enabled or requested via metadata)
        is_rag_active = agent.rag_enabled or (session_metadata and session_metadata.get("rag_enabled"))
        kb_target_id = agent.knowledge_base_id
        if session_metadata and session_metadata.get("knowledge_base_id"):
            try:
                kb_target_id = uuid.UUID(str(session_metadata["knowledge_base_id"]))
            except ValueError:
                pass

        if is_rag_active and kb_target_id:
            try:
                rag_res = await RetrievalService.build_rag_context(
                    db=db,
                    query=user_message,
                    knowledge_base_id=kb_target_id,
                    top_k=int(agent.rag_top_k or 3),
                    similarity_threshold=float(agent.rag_similarity_threshold or 0.65),
                    session_id=session.id,
                )
                if rag_res.get("has_context"):
                    rag_msg = ChatMessage(role=MessageRole.SYSTEM, content=rag_res["context_text"])
                    conversation_staging.insert(1, rag_msg)
                    retrieved_rag_sources = rag_res.get("sources", [])
            except Exception as e:
                logger.warning(f"RAG context retrieval failed: {e}")

        # 2. Patient Memory Staging (isolated by contact_id)
        contact_id_val = session_metadata.get("contact_id") if session_metadata else None
        if contact_id_val:
            try:
                c_uuid = uuid.UUID(str(contact_id_val))
                mem_ctx = await MemoryService.build_patient_memory_context(db, c_uuid)
                if mem_ctx:
                    mem_msg = ChatMessage(role=MessageRole.SYSTEM, content=mem_ctx)
                    conversation_staging.insert(1, mem_msg)
            except Exception as e:
                logger.warning(f"Patient memory staging failed: {e}")

        # Allowed Tools definition
        allowed_tools_list = agent.allowed_tools or []
        tool_definitions = ToolRegistry.get_definitions(allowed_names=allowed_tools_list)

        # Execution boundaries
        max_steps = agent.max_execution_steps or 5
        timeout_sec = float(agent.execution_timeout_seconds or 60)
        options = LLMOptions(
            temperature=float(agent.temperature or 0.2),
            max_tokens=agent.max_tokens or 1000,
            timeout_seconds=min(30.0, timeout_sec),
        )

        tool_context = ToolExecutionContext(
            session_id=session.id,
            agent_id=agent.id,
            conversation_id=conversation_id,
            user_id=user_id,
            caller_permissions=caller_permissions or ["*"],
            metadata=session_metadata or {},
        )

        steps_summary: List[Dict[str, Any]] = []
        all_tool_calls: List[Dict[str, Any]] = []
        final_response_text: Optional[str] = None
        current_step = 0
        total_in_tokens = 0
        total_out_tokens = 0
        active_model = primary_model_ident
        active_provider = primary_adapter.name

        try:
            # 5. Step Execution Loop bounded by max_steps and timeout
            async def run_loop():
                nonlocal current_step, total_in_tokens, total_out_tokens
                nonlocal final_response_text, active_model, active_provider

                while current_step < max_steps:
                    current_step += 1
                    step_start = time.perf_counter()

                    # Call LLM Gateway
                    llm_resp = await LLMGateway.execute(
                        primary_provider=primary_adapter,
                        primary_model=primary_model_ident,
                        messages=conversation_staging,
                        options=options,
                        tools=tool_definitions if tool_definitions else None,
                        fallback_provider=fallback_adapter,
                        fallback_model=fallback_model_ident,
                        allow_fallback=allow_fallback,
                        has_mutating_side_effects=False,
                        session_id=session.id,
                        agent_id=agent.id,
                        db=db,
                    )

                    active_model = llm_resp.model
                    active_provider = llm_resp.provider
                    step_duration = int((time.perf_counter() - step_start) * 1000)

                    total_in_tokens += llm_resp.usage.input_tokens
                    total_out_tokens += llm_resp.usage.output_tokens

                    # Record Step in AIAgentExecution
                    step_record = AIAgentExecution(
                        session_id=session.id,
                        agent_id=agent.id,
                        step_number=current_step,
                        status="completed",
                        prompt_messages=[m.model_dump() for m in conversation_staging[-3:]],
                        response_text=llm_resp.content,
                        tool_calls=[tc.model_dump() for tc in llm_resp.tool_calls] if llm_resp.tool_calls else None,
                        input_tokens=llm_resp.usage.input_tokens,
                        output_tokens=llm_resp.usage.output_tokens,
                        duration_ms=step_duration,
                    )
                    db.add(step_record)
                    await db.flush()

                    steps_summary.append({
                        "step": current_step,
                        "duration_ms": step_duration,
                        "tool_calls_count": len(llm_resp.tool_calls),
                        "has_content": bool(llm_resp.content),
                    })

                    # If model returned tool calls, process them via ToolDispatcher
                    if llm_resp.tool_calls:
                        # Append assistant message with tool calls to history
                        conversation_staging.append(
                            ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=llm_resp.content or "",
                                tool_calls=llm_resp.tool_calls,
                            )
                        )

                        for tc in llm_resp.tool_calls:
                            dispatch_res = await ToolDispatcher.dispatch(
                                tool_name=tc.name,
                                arguments=tc.arguments,
                                context=tool_context,
                                db=db,
                                allowed_tools=allowed_tools_list,
                            )

                            all_tool_calls.append({
                                "step": current_step,
                                "id": tc.id,
                                "name": tc.name,
                                "arguments": tc.arguments,
                                "result": dispatch_res,
                            })

                            # Append tool execution result back into conversation staging
                            conversation_staging.append(
                                ChatMessage(
                                    role=MessageRole.TOOL,
                                    name=tc.name,
                                    tool_call_id=tc.id,
                                    content=json.dumps(dispatch_res, default=str),
                                )
                            )

                        # Continue loop to allow model to consume tool result
                        continue

                    # If no tool calls, this is the final conversational answer
                    final_response_text = llm_resp.content
                    break

            # Execute with overall session timeout guardrail
            await asyncio.wait_for(run_loop(), timeout=timeout_sec)

            # Update session to completed
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
            session.total_input_tokens = total_in_tokens
            session.total_output_tokens = total_out_tokens
            session.total_execution_steps = current_step
            await db.commit()

            total_duration = int((time.perf_counter() - start_time) * 1000)

            return AgentRunResult(
                session_id=str(session.id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                status="completed",
                response_text=final_response_text or "",
                steps=steps_summary,
                tool_calls=all_tool_calls,
                rag_sources=retrieved_rag_sources,
                total_input_tokens=total_in_tokens,
                total_output_tokens=total_out_tokens,
                total_tokens=total_in_tokens + total_out_tokens,
                duration_ms=total_duration,
                model=active_model,
                provider=active_provider,
            )

        except asyncio.TimeoutError:
            total_duration = int((time.perf_counter() - start_time) * 1000)
            err_msg = f"Agent execution exceeded configured timeout of {timeout_sec}s."
            logger.error(err_msg)
            session.status = "failed"
            session.error_message = err_msg
            session.completed_at = datetime.now(timezone.utc)
            session.total_input_tokens = total_in_tokens
            session.total_output_tokens = total_out_tokens
            session.total_execution_steps = current_step
            await db.commit()

            return AgentRunResult(
                session_id=str(session.id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                status="failed",
                response_text=final_response_text,
                steps=steps_summary,
                tool_calls=all_tool_calls,
                rag_sources=retrieved_rag_sources,
                total_input_tokens=total_in_tokens,
                total_output_tokens=total_out_tokens,
                total_tokens=total_in_tokens + total_out_tokens,
                duration_ms=total_duration,
                model=active_model,
                provider=active_provider,
                error_message=err_msg,
            )

        except Exception as e:
            total_duration = int((time.perf_counter() - start_time) * 1000)
            err_msg = str(e)
            logger.error(f"Agent execution failed: {err_msg}", exc_info=True)
            session.status = "failed"
            session.error_message = err_msg
            session.completed_at = datetime.now(timezone.utc)
            session.total_input_tokens = total_in_tokens
            session.total_output_tokens = total_out_tokens
            session.total_execution_steps = current_step
            await db.commit()

            return AgentRunResult(
                session_id=str(session.id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                status="failed",
                response_text=final_response_text,
                steps=steps_summary,
                tool_calls=all_tool_calls,
                rag_sources=retrieved_rag_sources,
                total_input_tokens=total_in_tokens,
                total_output_tokens=total_out_tokens,
                total_tokens=total_in_tokens + total_out_tokens,
                duration_ms=total_duration,
                model=active_model,
                provider=active_provider,
                error_message=err_msg,
            )
