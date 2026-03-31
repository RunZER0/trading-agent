"""WebSocket endpoints for real-time updates."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.dependencies import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# Connected clients
_signal_clients: list[WebSocket] = []
_agent_clients: list[WebSocket] = []


@router.websocket("/ws/signals")
async def signals_websocket(websocket: WebSocket):
    """Stream new trading signals in real-time."""
    await websocket.accept()
    _signal_clients.append(websocket)
    logger.info(f"Signal WS client connected ({len(_signal_clients)} total)")

    try:
        # Poll Supabase for new signals (Supabase realtime requires JS client;
        # for Python we poll efficiently)
        last_id = None
        while True:
            supabase = get_supabase()
            query = (
                supabase.table("trading_signals")
                .select("*")
                .order("created_at", desc=True)
                .limit(1)
            )
            resp = query.execute()

            if resp.data:
                current_id = resp.data[0]["id"]
                if last_id is not None and current_id != last_id:
                    await websocket.send_json({
                        "type": "new_signal",
                        "data": resp.data[0],
                    })
                last_id = current_id

            await asyncio.sleep(5)
    except WebSocketDisconnect:
        _signal_clients.remove(websocket)
        logger.info(f"Signal WS client disconnected ({len(_signal_clients)} total)")


@router.websocket("/ws/agent-status")
async def agent_status_websocket(websocket: WebSocket):
    """Stream agent run status updates."""
    await websocket.accept()
    _agent_clients.append(websocket)
    logger.info(f"Agent WS client connected ({len(_agent_clients)} total)")

    try:
        last_status = None
        while True:
            supabase = get_supabase()
            resp = (
                supabase.table("agent_runs")
                .select("*")
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )

            if resp.data:
                current = resp.data[0]
                status_key = f"{current['id']}_{current['status']}"
                if status_key != last_status:
                    await websocket.send_json({
                        "type": "agent_status",
                        "data": current,
                    })
                    last_status = status_key

            await asyncio.sleep(3)
    except WebSocketDisconnect:
        _agent_clients.remove(websocket)
        logger.info(f"Agent WS client disconnected ({len(_agent_clients)} total)")


async def broadcast_signal(signal_data: dict[str, Any]) -> None:
    """Broadcast a new signal to all connected WebSocket clients."""
    disconnected = []
    for ws in _signal_clients:
        try:
            await ws.send_json({"type": "new_signal", "data": signal_data})
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _signal_clients.remove(ws)
