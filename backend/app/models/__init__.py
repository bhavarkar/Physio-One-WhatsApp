"""SQLAlchemy Models Package

Registers all 30 single-tenant entities for Alembic and application runtime.
"""
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin

# 1. User & Access Control
from app.models.user import Role, Permission, User, UserSession, AuditLog

# 2. WhatsApp Ingress & Messaging
from app.models.whatsapp import (
    WhatsAppAccount,
    WhatsAppContact,
    Conversation,
    WhatsAppMessage,
    WebhookEvent,
    MessageDebounce,
    WhatsAppTemplate,
)

# 3. Patient & Appointments
from app.models.patient import Patient, PatientConsent, Appointment, AppointmentHistory

# 4. AI Agents & Tools
from app.models.ai import (
    AIProvider,
    AIModel,
    AIAgent,
    AIAgentVersion,
    AIAgentSession,
    AIAgentExecution,
    LLMUsageLog,
    AIToolDefinition,
    AIToolExecution,
)

# 5. Memory & Knowledge Base (pgvector)
from app.models.memory import (
    ConversationSummary,
    ConversationMemory,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeChunk,
    AIRetrievalLog,
)

# 7. Inbound AI Orchestration, Queue & Handoff
from app.models.inbound import (
    InboundProcessingJob,
    AIInboundSettings,
    ConversationHandoff,
    AIResponseDraft,
    OutboundIdempotencyKey,
)

# 8. Appointment AI Workflows & Approvals (Task 10)
from app.models.workflow import (
    AppointmentAIWorkflow,
    AppointmentWorkflowEvent,
    AppointmentConfirmation,
    AppointmentApprovalRequest,
    AppointmentOperationIdempotency,
    AppointmentWorkflowSettings,
)

# 9. Campaigns (Task 12)
from app.models.campaign import (
    CampaignTemplate,
    CampaignMedia,
    Campaign,
    CampaignVersion,
    CampaignAudience,
    CampaignRecipient,
    CampaignApproval,
    CampaignDelivery,
    CampaignDeliveryEvent,
    CampaignConversionEvent,
    LegacyWorkflowMigration,
)

# 7. Follow-ups & Automations (Task 11)
from app.models.followup import (
    ScheduledFollowup,
    AutomationMessageTemplate,
    AutomationRule,
    AutomationScheduledJob,
    AutomationExecutionLog,
    AutomationSuppressionLog,
    AutomationSettings,
    AutomationContactCooldown,
    BackgroundJob,
)

# 8. Settings
from app.models.setting import SystemSetting


__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "Role",
    "Permission",
    "User",
    "UserSession",
    "AuditLog",
    "WhatsAppAccount",
    "WhatsAppContact",
    "Conversation",
    "WhatsAppMessage",
    "WebhookEvent",
    "MessageDebounce",
    "WhatsAppTemplate",
    "Patient",
    "PatientConsent",
    "Appointment",
    "AppointmentHistory",
    "AIProvider",
    "AIModel",
    "AIAgent",
    "AIAgentVersion",
    "AIAgentSession",
    "AIAgentExecution",
    "LLMUsageLog",
    "AIToolDefinition",
    "AIToolExecution",
    "ConversationSummary",
    "ConversationMemory",
    "KnowledgeBase",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "AIRetrievalLog",
    "InboundProcessingJob",
    "AIInboundSettings",
    "ConversationHandoff",
    "AIResponseDraft",
    "OutboundIdempotencyKey",
    "AppointmentAIWorkflow",
    "AppointmentWorkflowEvent",
    "AppointmentConfirmation",
    "AppointmentApprovalRequest",
    "AppointmentOperationIdempotency",
    "AppointmentWorkflowSettings",
    "CampaignTemplate",
    "CampaignMedia",
    "Campaign",
    "CampaignVersion",
    "CampaignAudience",
    "CampaignRecipient",
    "CampaignApproval",
    "CampaignDelivery",
    "CampaignDeliveryEvent",
    "CampaignConversionEvent",
    "LegacyWorkflowMigration",
    "ScheduledFollowup",
    "AutomationMessageTemplate",
    "AutomationRule",
    "AutomationScheduledJob",
    "AutomationExecutionLog",
    "AutomationSuppressionLog",
    "AutomationSettings",
    "AutomationContactCooldown",
    "BackgroundJob",
    "SystemSetting",
]

