"""WhatsApp Provider Factory

Single Organization Edition: Physio One.
Instantiates and configures provider adapters from stored database accounts.
"""
from typing import Optional
from app.models.whatsapp import WhatsAppAccount
from app.providers.base import WhatsAppProvider, ProviderType
from app.providers.meta import MetaCloudProvider
from app.providers.ycloud import YCloudProvider
from app.core.crypto import decrypt_secret


def get_provider_adapter(account: WhatsAppAccount) -> WhatsAppProvider:
    """Instantiate the corresponding provider adapter for a WhatsAppAccount."""
    provider_type = (account.provider or "meta").lower()

    # Decrypt access token and secret key securely
    access_token = decrypt_secret(account.access_token_encrypted)
    secret_key = decrypt_secret(account.secret_key_encrypted) if account.secret_key_encrypted else None

    if provider_type in (ProviderType.META_CLOUD.value, "meta_cloud"):
        return MetaCloudProvider(
            phone_number_id=account.phone_number_id,
            access_token=access_token,
            business_account_id=account.business_account_id,
            app_secret=secret_key,
            webhook_verify_token=account.webhook_verify_token,
        )
    elif provider_type == ProviderType.YCLOUD.value:
        return YCloudProvider(
            api_key=access_token,
            phone_number=account.display_phone_number or account.phone_number_id,
            webhook_secret=secret_key,
        )
    else:
        raise ValueError(f"Unsupported WhatsApp provider type: '{provider_type}'")

