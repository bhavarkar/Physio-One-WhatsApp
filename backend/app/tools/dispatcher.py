"""Tool Dispatcher and Execution Boundary.

Single Organization Edition: Physio One Clinic.
Enforces permission verification, timeouts, argument sanitization, and structured audit logging.
Strictly disallows arbitrary code, shell execution, or unauthorized tool invocations.
"""
import asyncio
import time
import json
import uuid
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool, ToolExecutionContext
from app.tools.registry import ToolRegistry
from app.models.ai import AIToolExecution

logger = logging.getLogger("physio_one.tools.dispatcher")


class ToolDispatcher:
    """Secure dispatcher executing registered tools on behalf of AI Agents."""

    @classmethod
    async def dispatch(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
        allowed_tools: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Dispatch a single tool call with permission checks, timeout, and execution logging."""
        start_time = time.perf_counter()

        # 1. Enforce agent tool whitelist
        if allowed_tools is not None and tool_name not in allowed_tools:
            logger.warning(f"Agent attempted to invoke unauthorized tool: '{tool_name}'")
            return await cls._log_and_return_denial(
                tool_name=tool_name,
                arguments=arguments,
                error_message=f"Access denied. Tool '{tool_name}' is not in the agent's allowed tools.",
                context=context,
                db=db,
                start_time=start_time,
                status="rejected_by_rule",
            )

        # 2. Look up registered tool implementation
        tool = ToolRegistry.get(tool_name)
        if not tool:
            logger.warning(f"Attempted to invoke unregistered tool: '{tool_name}'")
            return await cls._log_and_return_denial(
                tool_name=tool_name,
                arguments=arguments,
                error_message=f"Tool '{tool_name}' is not recognized or not available in the registry.",
                context=context,
                db=db,
                start_time=start_time,
                status="failed",
            )

        # 3. Backend RBAC permission enforcement
        if context.caller_permissions:
            has_perm = (
                "*" in context.caller_permissions
                or tool.requires_permission in context.caller_permissions
                or any(p.startswith(tool.requires_permission.split(":")[0] + ":*") for p in context.caller_permissions)
            )
            if not has_perm:
                logger.warning(
                    f"Tool execution denied: Caller missing required permission '{tool.requires_permission}'"
                )
                return await cls._log_and_return_denial(
                    tool_name=tool_name,
                    arguments=arguments,
                    error_message=f"Access denied. Missing required permission '{tool.requires_permission}'.",
                    context=context,
                    db=db,
                    start_time=start_time,
                    status="rejected_by_rule",
                )

        # 4. Safe execution within timeout boundary
        try:
            result = await asyncio.wait_for(
                tool.execute(arguments=arguments, context=context, db=db),
                timeout=tool.timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Audit log execution
            await cls._record_execution(
                db=db,
                context=context,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                status="success",
                duration_ms=duration_ms,
                error_message=None,
            )

            return {"success": True, "data": result}

        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            err_msg = f"Tool '{tool_name}' timed out after {tool.timeout_seconds}s."
            logger.error(err_msg)
            await cls._record_execution(
                db=db,
                context=context,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                status="failed",
                duration_ms=duration_ms,
                error_message=err_msg,
            )
            return {"success": False, "error": err_msg}

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            err_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            await cls._record_execution(
                db=db,
                context=context,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                status="failed",
                duration_ms=duration_ms,
                error_message=err_msg,
            )
            return {"success": False, "error": err_msg}

    @classmethod
    async def _log_and_return_denial(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        error_message: str,
        context: ToolExecutionContext,
        db: AsyncSession,
        start_time: float,
        status: str,
    ) -> Dict[str, Any]:
        """Record audit log for rejected tool calls."""
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        await cls._record_execution(
            db=db,
            context=context,
            tool_name=tool_name,
            arguments=arguments,
            result=None,
            status=status,
            duration_ms=duration_ms,
            error_message=error_message,
        )
        return {"success": False, "error": error_message}

    @classmethod
    async def _record_execution(
        cls,
        db: AsyncSession,
        context: ToolExecutionContext,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        status: str,
        duration_ms: int,
        error_message: Optional[str],
    ) -> None:
        """Persist structured audit record to ai_tool_executions table."""
        try:
            # Mask arguments if phone present for PHI security
            safe_args = dict(arguments)
            if "phone" in safe_args and isinstance(safe_args["phone"], str):
                raw_ph = safe_args["phone"]
                if len(raw_ph) >= 7:
                    safe_args["phone"] = f"{raw_ph[:3]}***{raw_ph[-3:]}"

            # Ensure arguments and results are JSON serializable
            safe_args = json.loads(json.dumps(safe_args, default=str))
            safe_result = json.loads(json.dumps(result, default=str)) if result is not None else None

            exec_record = AIToolExecution(
                conversation_id=context.conversation_id,
                agent_id=context.agent_id,
                session_id=context.session_id,
                tool_name=tool_name,
                arguments=safe_args,
                result=safe_result,
                status=status,
                execution_duration_ms=duration_ms,
                error_message=error_message,
            )
            db.add(exec_record)
            await db.flush()
        except Exception as e:
            logger.warning(f"Failed to record AIToolExecution log: {e}")
