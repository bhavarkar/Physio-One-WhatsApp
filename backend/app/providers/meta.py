"""Meta WhatsApp Cloud API Adapter

Single Organization Edition: Physio One.
Implements the official Meta WhatsApp Cloud API (Graph API v20.0).
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import httpx

from app.providers.base import (
    WhatsAppProvider,
    ConnectionValidationResult,
    OutboundSendResult,
    NormalizedInboundMessage,
    NormalizedStatusUpdate,
    WebhookVerificationResult,
    MessageStatus,
    MessageType,
    ProviderType,
)

logger = logging.getLogger(__name__)


def clean_phone_number(phone: str) -> str:
    """Standardize phone number to digits only with leading plus removed."""
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits


class MetaCloudProvider(WhatsAppProvider):
    """Adapter for official Meta WhatsApp Cloud API."""

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        business_account_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        webhook_verify_token: Optional[str] = None,
        api_version: str = "v20.0",
        base_url: str = "https://graph.facebook.com",
    ):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.business_account_id = business_account_id
        self.app_secret = app_secret
        self.webhook_verify_token = webhook_verify_token
        self.api_version = api_version
        self.base_url = f"{base_url.rstrip('/')}/{self.api_version}"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "PhysioOne-WhatsApp/1.0",
        }

    async def validate_connection(self) -> ConnectionValidationResult:
        """Validate connection by fetching phone number details from Graph API."""
        url = f"{self.base_url}/{self.phone_number_id}"
        params = {"fields": "id,display_phone_number,verified_name,quality_rating"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=self._get_headers(), params=params)
                
            if resp.status_code == 200:
                data = resp.json()
                return ConnectionValidationResult(
                    is_valid=True,
                    phone_number=data.get("display_phone_number"),
                    display_name=data.get("verified_name"),
                    provider_account_id=data.get("id"),
                    raw_response=data,
                )
            
            error_data = resp.json().get("error", {})
            error_msg = error_data.get("message") or f"HTTP {resp.status_code}: {resp.text}"
            return ConnectionValidationResult(
                is_valid=False,
                error=error_msg,
                raw_response=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None,
            )
        except Exception as e:
            logger.error("Meta connection validation failed: %s", str(e))
            return ConnectionValidationResult(is_valid=False, error=str(e))

    async def send_text_message(
        self, to: str, text: str, preview_url: bool = False
    ) -> OutboundSendResult:
        """Send outbound text message via Meta Cloud API."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        recipient = clean_phone_number(to)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": text,
            },
        }

        return await self._dispatch_send(url, payload)

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> OutboundSendResult:
        """Send an approved WhatsApp template message."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        recipient = clean_phone_number(to)

        template_obj: Dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template_obj["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": template_obj,
        }

        return await self._dispatch_send(url, payload)

    async def send_media_message(
        self,
        to: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> OutboundSendResult:
        """Send media message (image, document, audio, video) via Meta Cloud API."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        recipient = clean_phone_number(to)

        media_obj: Dict[str, Any] = {"link": media_url}
        if caption and media_type in ["image", "video", "document"]:
            media_obj["caption"] = caption
        if filename and media_type == "document":
            media_obj["filename"] = filename

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": media_type,
            media_type: media_obj,
        }

        return await self._dispatch_send(url, payload)

    async def _dispatch_send(self, url: str, payload: Dict[str, Any]) -> OutboundSendResult:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)

            if resp.status_code in (200, 201):
                data = resp.json()
                messages = data.get("messages", [])
                provider_msg_id = messages[0].get("id") if messages else None
                return OutboundSendResult(
                    success=True,
                    provider_message_id=provider_msg_id,
                    status=MessageStatus.SENT,
                    raw_response=data,
                )

            error_data = resp.json().get("error", {})
            error_msg = error_data.get("message") or f"HTTP {resp.status_code}: {resp.text}"
            return OutboundSendResult(
                success=False,
                status=MessageStatus.FAILED,
                error=error_msg,
                raw_response=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None,
            )
        except Exception as e:
            logger.error("Meta message dispatch error: %s", str(e))
            return OutboundSendResult(
                success=False,
                status=MessageStatus.FAILED,
                error=str(e),
            )

    def verify_webhook_signature(
        self, headers: Dict[str, str], raw_body: bytes
    ) -> bool:
        """Verify Meta X-Hub-Signature-256 header against app_secret."""
        if not self.app_secret:
            logger.warning("Meta webhook verification skipped: app_secret is not configured.")
            return False

        # Header can be lowercase or mixed case in HTTP/2 / ASGI
        signature_header = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        if not signature_header or not signature_header.startswith("sha256="):
            return False

        received_hash = signature_header.split("sha256=", 1)[1].strip()
        expected_hash = hmac.new(
            self.app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(received_hash, expected_hash)

    def verify_subscription_challenge(
        self, mode: Optional[str], token: Optional[str], challenge: Optional[str]
    ) -> WebhookVerificationResult:
        """Verify Meta webhook challenge verification."""
        if mode == "subscribe" and token and token == self.webhook_verify_token:
            return WebhookVerificationResult(is_valid=True, challenge=challenge)
        return WebhookVerificationResult(
            is_valid=False,
            error="Invalid verify token or subscription mode."
        )

    def parse_webhook_payload(
        self, payload: Dict[str, Any]
    ) -> Tuple[List[NormalizedInboundMessage], List[NormalizedStatusUpdate]]:
        """Extract inbound messages and status updates from Meta webhook payload."""
        inbound_messages: List[NormalizedInboundMessage] = []
        status_updates: List[NormalizedStatusUpdate] = []

        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                recipient_phone = metadata.get("display_phone_number", "")

                # 1. Process Inbound Messages
                raw_messages = value.get("messages", [])
                contacts = value.get("contacts", [])
                contact_map = {c.get("wa_id"): c.get("profile", {}).get("name") for c in contacts}

                for msg in raw_messages:
                    msg_id = msg.get("id")
                    from_wa_id = msg.get("from")
                    raw_time = msg.get("timestamp")
                    try:
                        timestamp = datetime.fromtimestamp(int(raw_time), tz=timezone.utc)
                    except (ValueError, TypeError):
                        timestamp = datetime.now(timezone.utc)

                    msg_type = msg.get("type", "text")
                    text_body = None
                    media_url = None
                    media_mime = None
                    media_id = None

                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body")
                    elif msg_type in ["image", "video", "audio", "document", "voice"]:
                        media_info = msg.get(msg_type, {})
                        media_id = media_info.get("id")
                        media_mime = media_info.get("mime_type")
                        text_body = media_info.get("caption")

                    if msg_id and from_wa_id:
                        inbound_messages.append(
                            NormalizedInboundMessage(
                                provider=ProviderType.META_CLOUD.value,
                                message_id=msg_id,
                                sender_wa_id=from_wa_id,
                                recipient_phone=recipient_phone,
                                timestamp=timestamp,
                                message_type=msg_type,
                                text_body=text_body,
                                media_url=media_url,
                                media_mime_type=media_mime,
                                media_id=media_id,
                                raw_payload=msg,
                            )
                        )

                # 2. Process Delivery Statuses
                raw_statuses = value.get("statuses", [])
                for st in raw_statuses:
                    msg_id = st.get("id")
                    recipient_wa_id = st.get("recipient_id", "")
                    raw_status_str = st.get("status", "sent").lower()
                    raw_time = st.get("timestamp")
                    try:
                        timestamp = datetime.fromtimestamp(int(raw_time), tz=timezone.utc)
                    except (ValueError, TypeError):
                        timestamp = datetime.now(timezone.utc)

                    # Normalize status
                    status_enum = MessageStatus.SENT
                    if raw_status_str == "delivered":
                        status_enum = MessageStatus.DELIVERED
                    elif raw_status_str == "read":
                        status_enum = MessageStatus.READ
                    elif raw_status_str == "failed":
                        status_enum = MessageStatus.FAILED

                    error_code = None
                    error_message = None
                    errors = st.get("errors", [])
                    if errors:
                        error_code = str(errors[0].get("code"))
                        error_message = errors[0].get("title") or errors[0].get("message")

                    if msg_id:
                        status_updates.append(
                            NormalizedStatusUpdate(
                                provider=ProviderType.META_CLOUD.value,
                                message_id=msg_id,
                                recipient_wa_id=recipient_wa_id,
                                status=status_enum,
                                timestamp=timestamp,
                                error_code=error_code,
                                error_message=error_message,
                                raw_payload=st,
                            )
                        )

        return inbound_messages, status_updates

