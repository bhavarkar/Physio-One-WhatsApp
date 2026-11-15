"""Cloud Tasks dispatch (Task 14).

PostgreSQL job tables remain the durable source of truth. Cloud Tasks is only
an authenticated delivery trigger for the existing worker HTTP endpoints —
it is NOT a second queue: task bodies carry only an opaque job reference and
handlers re-read/claim state from PostgreSQL (leases + idempotency keys make
duplicate delivery safe).

Disabled by default (CLOUD_TASKS_ENABLED=false). When disabled or the client
library/credentials are unavailable, dispatch returns a structured no-op so
local development and the polling worker (local Compose only) are unaffected.
Cloud Run must NOT run the polling loop as a service; use Cloud Tasks /
Cloud Scheduler -> these endpoints, or a Cloud Run Job invoking
``python -m app.workers.runner --once`` (see runner).
"""
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("physio_one.cloud_tasks")

ENDPOINTS = {
    "inbound": "/api/v1/ai-inbound/process-due",
    "automation": "/api/v1/automations/process-due",
    "inactivity": "/api/v1/automations/scan-inactivity",
    "campaigns": "/api/v1/campaigns/worker/run",
}
QUEUES = {
    "inbound": "CLOUD_TASKS_INBOUND_QUEUE",
    "automation": "CLOUD_TASKS_AUTOMATION_QUEUE",
    "inactivity": "CLOUD_TASKS_AUTOMATION_QUEUE",
    "campaigns": "CLOUD_TASKS_CAMPAIGN_QUEUE",
}


def task_name_for(queue_path: str, dedup_key: str) -> str:
    """Deterministic task name -> Cloud Tasks rejects duplicate creates."""
    digest = hashlib.sha256(dedup_key.encode()).hexdigest()[:48]
    return f"{queue_path}/tasks/{digest}"


def dispatch_worker_task(kind: str, dedup_key: str, payload: Optional[Dict[str, Any]] = None,
                         schedule_seconds: int = 0) -> Dict[str, Any]:
    """Create an OIDC-authenticated Cloud Task for a worker endpoint.

    Returns {dispatched: bool, reason: str, task_name?: str}. Never raises.
    """
    if kind not in ENDPOINTS:
        return {"dispatched": False, "reason": f"unknown_kind:{kind}"}
    if not settings.CLOUD_TASKS_ENABLED:
        return {"dispatched": False, "reason": "cloud_tasks_disabled"}
    if not (settings.GCP_PROJECT_ID and settings.WORKER_BASE_URL and settings.WORKER_SERVICE_ACCOUNT_EMAIL):
        return {"dispatched": False, "reason": "cloud_tasks_unconfigured"}
    try:
        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2, timestamp_pb2
        import time as _time
    except Exception as exc:  # library not installed locally
        logger.warning("Cloud Tasks client unavailable: %s", exc)
        return {"dispatched": False, "reason": "client_unavailable"}
    try:
        client = tasks_v2.CloudTasksClient()
        queue = getattr(settings, QUEUES[kind])
        parent = client.queue_path(settings.GCP_PROJECT_ID, settings.CLOUD_TASKS_LOCATION, queue)
        url = settings.WORKER_BASE_URL.rstrip("/") + ENDPOINTS[kind]
        audience = settings.OIDC_AUDIENCE or settings.WORKER_BASE_URL
        task: Dict[str, Any] = {
            "name": task_name_for(parent, dedup_key),
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload or {}).encode(),
                "oidc_token": {"service_account_email": settings.WORKER_SERVICE_ACCOUNT_EMAIL,
                               "audience": audience},
            },
        }
        if schedule_seconds > 0:
            ts = timestamp_pb2.Timestamp()
            ts.FromSeconds(int(_time.time()) + schedule_seconds)
            task["schedule_time"] = ts
        created = client.create_task(parent=parent, task=task)
        return {"dispatched": True, "reason": "created", "task_name": created.name}
    except Exception as exc:  # duplicate name -> AlreadyExists is a safe success-equivalent
        if "ALREADY_EXISTS" in str(exc) or "AlreadyExists" in type(exc).__name__:
            return {"dispatched": True, "reason": "already_exists"}
        logger.error("Cloud Tasks dispatch failed (%s): %s", kind, exc)
        return {"dispatched": False, "reason": f"error:{type(exc).__name__}"}
