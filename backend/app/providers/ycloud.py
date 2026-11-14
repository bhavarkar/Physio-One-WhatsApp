"""YCloud WhatsApp Provider Adapter

Single Organization Edition: Physio One.
Implements the YCloud API integration for existing Physio One WhatsApp workflows.
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
from app.providers.meta import clean_phone_number

logger = logging.getLogger(__name__)


class YCloudProvider(WhatsAppProvider):
    """Adapter for YCloud WhatsApp API."""

    def __init__(
        self,
        api_key: str,
        phone_number: str,
        webhook_secret: Optional[str] = None,
        base_url: str = "https://api.ycloud.com/v2",
    ):
        self.api_key = api_key
        self.phone_number = phone_number
        self.webhook_secret = webhook_secret
        self.base_url = base_url.rstrip("/")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "PhysioOne-YCloud/1.0",
        }

    async def validate_connection(self) -> ConnectionValidationResult:
        """Validate YCloud credentials and phone number status."""
        url = f"{self.base_url}/whatsapp/phoneNumbers"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=self._get_headers())

            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                matched = next(
                    (p for p in items if clean_phone_number(p.get("phoneNumber", "")) == clean_phone_number(self.phone_number)),
                    None,
                )
                if matched:
                    return ConnectionValidationResult(
                        is_valid=True,
                        phone_number=matched.get("phoneNumber"),
                        display_name=matched.get("displayPhoneNumber"),
                        provider_account_id=matched.get("wabaId"),
                        raw_response=matched,
                    )
                # If API key is valid but phone number not listed, return valid key with warning
                return ConnectionValidationResult(
                    is_valid=True,
                    phone_number=self.phone_number,
                    display_name="YCloud Account Active",
                    raw_response=data,
                )

            error_msg = resp.json().get("message") if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            return ConnectionValidationResult(
                is_valid=False,
                error=f"YCloud validation failed: {error_msg}",
            )
        except Exception as e:
            logger.error("YCloud validation exception: %s", str(e))
            return ConnectionValidationResult(is_valid=False, error=str(e))

    async def send_text_message(
        self, to: str, text: str, preview_url: bool = False
    ) -> OutboundSendResult:
        """Send outbound text message via YCloud."""
        url = f"{self.base_url}/whatsapp/messages/send"
        payload = {
            "from": self.phone_number,
            "to": clean_phone_number(to),
            "type": "text",
            "text": {"body": text},
        }
        return await self._dispatch_send(url, payload)

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> OutboundSendResult:
        """Send an approved WhatsApp template message via YCloud."""
        url = f"{self.base_url}/whatsapp/messages/send"
        template_obj: Dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template_obj["components"] = components

        payload = {
            "from": self.phone_number,
            "to": clean_phone_number(to),
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
        """Send a media message (image, document, audio, video) via YCloud."""
        url = f"{self.base_url}/whatsapp/messages/send"
        media_obj: Dict[str, Any] = {"link": media_url}
        if caption:
            media_obj["caption"] = caption
        if filename:
            media_obj["filename"] = filename

        payload = {
            "from": self.phone_number,
            "to": clean_phone_number(to),
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
                msg_id = data.get("id")
                return OutboundSendResult(
                    success=True,
                    provider_message_id=msg_id,
                    status=MessageStatus.ACCEPTED,
                    raw_response=data,
                )

            error_msg = resp.json().get("message") if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            return OutboundSendResult(
                success=False,
                status=MessageStatus.FAILED,
                error=error_msg,
                raw_response=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None,
            )
        except Exception as e:
            logger.error("YCloud message dispatch error: %s", str(e))
            return OutboundSendResult(
                success=False,
                status=MessageStatus.FAILED,
                error=str(e),
            )

    def verify_webhook_signature(
        self, headers: Dict[str, str], raw_body: bytes
    ) -> bool:
        """Verify YCloud HMAC-SHA256 signature."""
        if not self.webhook_secret:
            logger.warning("YCloud webhook verification skipped: webhook_secret is not configured.")
            return False

        sig_header = (
            headers.get("ycloud-signature")
            or headers.get("YCloud-Signature")
            or headers.get("x-ycloud-signature")
            or headers.get("X-YCloud-Signature")
        )
        if not sig_header:
            return False

        # Support both standard t=timestamp,v1=signature and direct hex signature
        expected_sig = None
        if "t=" in sig_header and "v1=" in sig_header:
            parts = dict(item.split("=", 1) for item in sig_header.split(","))
            timestamp = parts.get("t", "")
            received_sig = parts.get("v1", "")
            payload_to_sign = f"{timestamp}.".encode("utf-8") + raw_body
            expected_sig = hmac.new(
                self.webhook_secret.encode("utf-8"),
                payload_to_sign,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(received_sig, expected_sig)
        else:
            expected_sig = hmac.new(
                self.webhook_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(sig_header.strip(), expected_sig)

    def verify_subscription_challenge(
        self, mode: Optional[str], token: Optional[str], challenge: Optional[str]
    ) -> WebhookVerificationResult:
        """YCloud does not use hub.challenge subscription verification."""
        return WebhookVerificationResult(is_valid=True, challenge=challenge)

    def parse_webhook_payload(
        self, payload: Dict[str, Any]
    ) -> Tuple[List[NormalizedInboundMessage], List[NormalizedStatusUpdate]]:
        """Extract inbound messages and status updates from YCloud webhook payload."""
        inbound_messages: List[NormalizedInboundMessage] = []
        status_updates: List[NormalizedStatusUpdate] = []

        event_type = payload.get("type", "")

        # 1. Inbound WhatsApp Message
        if event_type == "whatsapp.inbound_message" or "whatsappInboundMessage" in payload:
            msg_obj = payload.get("whatsappInboundMessage") or payload.get("data", {})
            msg_id = msg_obj.get("id")
            sender = msg_obj.get("from")
            recipient = msg_obj.get("to", self.phone_number)
            msg_type = msg_obj.get("type", "text")

            text_body = None
            if msg_type == "text":
                text_body = msg_obj.get("text", {}).get("body")
            elif msg_type in ["image", "video", "audio", "document"]:
                media_info = msg_obj.get(msg_type, {})
                text_body = media_info.get("caption")

            raw_time = msg_obj.get("sendTime") or msg_obj.get("createTime")
            timestamp = datetime.now(timezone.utc)
            if raw_time:
                try:
                    timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            if msg_id and sender:
                inbound_messages.append(
                    NormalizedInboundMessage(
                        provider=ProviderType.YCLOUD.value,
                        message_id=msg_id,
                        sender_wa_id=sender,
                        recipient_phone=recipient,
                        timestamp=timestamp,
                        message_type=msg_type,
                        text_body=text_body,
                        raw_payload=payload,
                    )
                )

        # 2. Outbound Message Status Updated
        elif event_type == "whatsapp.message.updated" or "whatsappMessage" in payload:
            msg_obj = payload.get("whatsappMessage") or payload.get("data", {})
            msg_id = msg_obj.get("id")
            recipient = msg_obj.get("to", "")
            raw_status = (msg_obj.get("status") or "sent").lower()

            status_enum = MessageStatus.SENT
            if raw_status in ("delivered", "received"):
                status_enum = MessageStatus.DELIVERED
            elif raw_status == "read":
                status_enum = MessageStatus.READ
            elif raw_status in ("failed", "undelivered"):
                status_enum = MessageStatus.FAILED

            raw_time = msg_obj.get("updatedTime") or msg_obj.get("sendTime")
            timestamp = datetime.now(timezone.utc)
            if raw_time:
                try:
                    timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            if msg_id:
                status_updates.append(
                    NormalizedStatusUpdate(
                        provider=ProviderType.YCLOUD.value,
                        message_id=msg_id,
                        recipient_wa_id=recipient,
                        status=status_enum,
                        timestamp=timestamp,
                        error_code=msg_obj.get("errorCode"),
                        error_message=msg_obj.get("errorMessage"),
                        raw_payload=payload,
                    )
                )

        return inbound_messages, status_updates

