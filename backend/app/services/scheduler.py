"""Scheduler service — runs the trading agent on a configurable interval."""

from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _scheduled_agent_run():
    """Called by the scheduler to run the trading agent."""
    from app.agent.graph import run_trading_agent

    logger.info("Scheduled agent run starting...")
    try:
        result = await run_trading_agent(trigger_type="scheduled")
        logger.info(
            f"Scheduled run completed: {result.get('signals_placed', 0)} signals placed"
        )
    except Exception as e:
        logger.error(f"Scheduled agent run failed: {e}")


def start_scheduler():
    """Start the APScheduler with the configured interval."""
    hours = settings.agent_schedule_hours
    scheduler.add_job(
        _scheduled_agent_run,
        trigger=IntervalTrigger(hours=hours),
        id="trading_agent_run",
        name=f"Trading Agent (every {hours}h)",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started: agent runs every {hours} hours")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
