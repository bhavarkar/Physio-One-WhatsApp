"""Common WhatsApp Provider Interface and Data Transfer Objects

Single Organization Edition: Physio One.
Defines standard contracts for Meta WhatsApp Cloud API and YCloud providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple


class ProviderType(str, Enum):
    META_CLOUD = "meta"
    YCLOUD = "ycloud"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    RECEIVED = "received"
    ACCEPTED = "accepted"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageType(str, Enum):
    TEXT = "text"
    TEMPLATE = "template"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    INTERACTIVE = "interactive"


@dataclass
class ConnectionValidationResult:
    is_valid: bool
    phone_number: Optional[str] = None
    display_name: Optional[str] = None
    provider_account_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class OutboundSendResult:
    success: bool
    provider_message_id: Optional[str] = None
    status: MessageStatus = MessageStatus.SENT
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class NormalizedInboundMessage:
    provider: str
    message_id: str
    sender_wa_id: str
    recipient_phone: str
    timestamp: datetime
    message_type: str
    text_body: Optional[str] = None
    media_url: Optional[str] = None
    media_mime_type: Optional[str] = None
    media_id: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedStatusUpdate:
    provider: str
    message_id: str
    recipient_wa_id: str
    status: MessageStatus
    timestamp: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookVerificationResult:
    is_valid: bool
    challenge: Optional[str] = None
    error: Optional[str] = None


class WhatsAppProvider(ABC):
    """Abstract Base Class for WhatsApp Integration Adapters."""

    @abstractmethod
    async def validate_connection(self) -> ConnectionValidationResult:
        """Validate credentials and phone number configuration against provider API."""
        pass

    @abstractmethod
    async def send_text_message(
        self, to: str, text: str, preview_url: bool = False
    ) -> OutboundSendResult:
        """Send an outbound text message to a contact."""
        pass

    @abstractmethod
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> OutboundSendResult:
        """Send an approved WhatsApp template message."""
        pass

    @abstractmethod
    async def send_media_message(
        self,
        to: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> OutboundSendResult:
        """Send a media message (image, audio, document, video)."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self, headers: Dict[str, str], raw_body: bytes
    ) -> bool:
        """Verify the cryptographic authenticity of an inbound webhook request."""
        pass

    @abstractmethod
    def verify_subscription_challenge(
        self, mode: Optional[str], token: Optional[str], challenge: Optional[str]
    ) -> WebhookVerificationResult:
        """Verify the provider's initial webhook subscription challenge (e.g. Meta hub.challenge)."""
        pass

    @abstractmethod
    def parse_webhook_payload(
        self, payload: Dict[str, Any]
    ) -> Tuple[List[NormalizedInboundMessage], List[NormalizedStatusUpdate]]:
        """Parse raw webhook JSON into normalized inbound messages and status updates."""
        pass
