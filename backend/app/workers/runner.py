"""Durable Background Automation and Campaign Worker Daemon.

Physio One WhatsApp AI Platform (Single Organization Edition).
Periodically executes:
1. Scheduled automation jobs and lease timeouts via AutomationWorkerService.
2. Instagram re-engagement campaigns via CampaignService.
3. Inbound AI debounced queue processing via InboundQueueService & InboundOrchestrator.

Supports graceful shutdown (SIGINT/SIGTERM) and resilient error handling.
"""
import os
import sys
import time
import signal
import asyncio
import logging
from typing import Optional

from app.core.database import AsyncSessionLocal
from app.services.automation_worker import AutomationWorkerService
from app.services.campaign_service import CampaignService
from app.services.inbound_queue import InboundQueueService
from app.services.inbound_orchestrator import InboundOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("physio_one.worker.daemon")

POLL_INTERVAL_SECONDS = int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "15"))


class WorkerDaemon:
    def __init__(self):
        self._running = False
        self._shutdown_event = asyncio.Event()

    def signal_handler(self, sig, frame):
        logger.info("Received termination signal %s. Initiating graceful shutdown...", sig)
        self._running = False
        self._shutdown_event.set()

    async def run_cycle(self):
        """Execute one complete processing cycle across all worker queues."""
        async with AsyncSessionLocal() as db:
            # 1. Scheduled Automations (Reminders, inactivity check-ins, recovery)
            try:
                auto_stats = await AutomationWorkerService.run_worker_cycle(db, limit=20)
                if any(v > 0 for k, v in auto_stats.items() if k != "processed_count"):
                    logger.info("Automation cycle completed: %s", auto_stats)
            except Exception as exc:
                logger.error("Error in automation worker cycle: %s", exc, exc_info=True)

            # 2. Instagram Re-engagement Campaigns
            try:
                camp_stats = await CampaignService.run_reengagement_cycle(db, limit=25)
                if camp_stats.get("dispatched_count", 0) > 0 or camp_stats.get("suppressed_count", 0) > 0:
                    logger.info("Campaign cycle completed: %s", camp_stats)
            except Exception as exc:
                logger.error("Error in campaign worker cycle: %s", exc, exc_info=True)

            # 3. Inbound AI Debounced Jobs
            try:
                due_inbound = await InboundQueueService.fetch_and_lock_due_jobs(db, limit=10)
                for job in due_inbound:
                    outcome = await InboundOrchestrator.process_job(db, job)
                    logger.info("Processed inbound job %s: status=%s", job.id, outcome.get("status"))
            except Exception as exc:
                logger.error("Error in inbound queue cycle: %s", exc, exc_info=True)

    async def start(self):
        """Start worker daemon loop."""
        self._running = True
        logger.info(
            "Physio One Worker Daemon started. Polling every %d seconds.",
            POLL_INTERVAL_SECONDS,
        )

        while self._running:
            start_time = time.monotonic()
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.error("Unhandled exception in worker loop: %s", exc, exc_info=True)

            elapsed = time.monotonic() - start_time
            sleep_time = max(1.0, POLL_INTERVAL_SECONDS - elapsed)

            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=sleep_time)
                break  # Shutdown event was set
            except asyncio.TimeoutError:
                pass  # Normal loop timeout, continue next cycle

        logger.info("Physio One Worker Daemon stopped gracefully.")


async def main():
    daemon = WorkerDaemon()

    # Register OS signals for graceful shutdown
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: daemon.signal_handler(s, None))
    else:
        signal.signal(signal.SIGINT, daemon.signal_handler)
        signal.signal(signal.SIGTERM, daemon.signal_handler)

    await daemon.start()


if __name__ == "__main__":
    # `--once`: single bounded cycle — the supported mode for Cloud Run Jobs /
    # Cloud Scheduler-triggered execution. Without it, a polling daemon runs,
    # which is ONLY appropriate for local Docker Compose (Cloud Run services
    # scale to zero / throttle CPU outside requests; never deploy the loop there).
    if "--once" in sys.argv:
        asyncio.run(WorkerDaemon().run_cycle())
    else:
        asyncio.run(main())
