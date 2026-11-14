"""Central Tool Registry for AI Agents.

Single Organization Edition: Physio One Clinic.
Maintains validated in-memory tools and exposes schema definitions to LLM Gateway.
"""
from typing import Dict, List, Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
from app.tools.clinical.availability import CheckAvailabilityTool
from app.tools.clinical.patient import FindPatientTool
from app.tools.clinical.knowledge import SearchClinicKnowledgeTool
from app.llm.schemas import ToolDefinition
from app.models.ai import AIToolDefinition

logger = logging.getLogger("physio_one.tools.registry")


class ToolRegistry:
    """Registry maintaining registered tool instances."""

    _tools: Dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """Register a tool instance."""
        cls._tools[tool.name] = tool
        logger.info(f"Registered tool: '{tool.name}' (mutation={tool.is_mutation})")

    @classmethod
    def get(cls, name: str) -> Optional[BaseTool]:
        """Retrieve tool by unique name."""
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> List[BaseTool]:
        """List all registered tools."""
        return list(cls._tools.values())

    @classmethod
    def get_definitions(cls, allowed_names: Optional[List[str]] = None) -> List[ToolDefinition]:
        """Generate normalized ToolDefinition objects for the LLM request.
        
        If allowed_names is provided, only include tools permitted for the specific agent.
        """
        definitions = []
        for name, tool in cls._tools.items():
            if allowed_names is not None and name not in allowed_names:
                continue
            definitions.append(tool.to_tool_definition())
        return definitions

    @classmethod
    async def sync_with_database(cls, db: AsyncSession) -> None:
        """Ensure all registered tools exist in ai_tool_definitions database table."""
        for tool in cls.list_tools():
            stmt = select(AIToolDefinition).where(AIToolDefinition.name == tool.name)
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if not existing:
                db_def = AIToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters_schema=tool.parameters_schema,
                    requires_permission=tool.requires_permission,
                    is_enabled=True,
                )
                db.add(db_def)
            else:
                existing.description = tool.description
                existing.parameters_schema = tool.parameters_schema
                existing.requires_permission = tool.requires_permission
        await db.flush()


# Initialize default clinical tools into registry
ToolRegistry.register(CheckAvailabilityTool())
ToolRegistry.register(FindPatientTool())
ToolRegistry.register(SearchClinicKnowledgeTool())
