"""Base Tool Definition and Execution Context.

Single Organization Edition: Physio One Clinic.
Enforces strict schema validation, permission checks, and separation between read-only and mutating actions.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.schemas import ToolDefinition


class ToolExecutionContext(BaseModel):
    """Contextual metadata supplied to tool execution."""
    session_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    caller_permissions: List[str] = []
    metadata: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True


class BaseTool(ABC):
    """Abstract base class for all callable tools."""

    name: str
    description: str
    parameters_schema: Dict[str, Any]
    requires_permission: str = "appointments:read"
    is_mutation: bool = False
    is_idempotent: bool = True
    timeout_seconds: float = 15.0

    def to_tool_definition(self) -> ToolDefinition:
        """Convert to normalized ToolDefinition for LLM consumption."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )

    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Execute tool logic and return sanitized JSON-serializable dictionary."""
        pass
