"""
Monitoring endpoints: agents, streams, circuits.
"""
from __future__ import annotations

from fastapi import APIRouter
from shared.models import AgentInfo, AgentStatus, CircuitInfo, CircuitState, StreamInfo
from shared.redis_client import get_all_agents, get_all_circuits, get_redis, get_stream_depths

router = APIRouter(prefix="/api", tags=["monitor"])


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    r = await get_redis()
    raw = await get_all_agents(r)
    agents: list[AgentInfo] = []
    for d in raw:
        try:
            last_hb = int(d.get("last_heartbeat", 0)) if d.get("last_heartbeat") else None
            agents.append(
                AgentInfo(
                    agent_id=d["agent_id"],
                    tier=int(d.get("tier", 1)),
                    status=AgentStatus(d.get("status", "IDLE")),
                    current_url=d.get("current_url") or None,
                    error_count=int(d.get("error_count", 0)),
                    last_heartbeat=last_hb,
                )
            )
        except Exception:
            continue
    return agents


@router.get("/streams", response_model=list[StreamInfo])
async def list_streams() -> list[StreamInfo]:
    r = await get_redis()
    depths = await get_stream_depths(r)
    return [StreamInfo(name=d["name"], depth=d["depth"]) for d in depths]


@router.get("/circuits", response_model=list[CircuitInfo])
async def list_circuits() -> list[CircuitInfo]:
    r = await get_redis()
    raw = await get_all_circuits(r)
    circuits: list[CircuitInfo] = []
    for d in raw:
        try:
            circuits.append(
                CircuitInfo(
                    domain=d["domain"],
                    state=CircuitState(d.get("state", "CLOSED")),
                    failures=int(d.get("failures", 0)),
                    last_error=d.get("last_error"),
                )
            )
        except Exception:
            continue
    return circuits
