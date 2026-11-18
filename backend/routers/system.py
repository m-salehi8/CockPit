from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from services.metrics import (
    collect_live_metrics,
    get_grouped_processes,
    get_lite_vitals,
    get_focus_mode_state,
    kill_processes,
    drop_memory_caches,
    refresh_swap,
    toggle_dev_focus_mode,
    refresh_network_indicators,
    switch_dns_profile,
    enable_zram_swap,
)
from services.policy_guard import policy_guard

router = APIRouter(prefix="/api/system", tags=["system"])


class KillRequest(BaseModel):
    pids: List[int]
    force: bool = False


class FocusModeRequest(BaseModel):
    enable: Optional[bool] = None
    services: Optional[List[str]] = None


class DnsSwitchRequest(BaseModel):
    profile: str


class PolicyUpdateRequest(BaseModel):
    policies: Dict[str, Dict[str, Any]]


@router.get("/snapshot")
async def get_system_snapshot():
    """Return a single on-demand snapshot of system metrics."""
    await refresh_network_indicators()
    return collect_live_metrics()


@router.get("/processes")
async def list_grouped_processes(limit: int = 45):
    """Return running processes aggregated by parent application group."""
    return get_grouped_processes(limit=limit)


@router.post("/processes/kill")
async def terminate_processes(req: KillRequest):
    """Terminate or kill one or more PIDs (individual process or whole application group)."""
    return await kill_processes(req.pids, force=req.force)


@router.post("/rescue/drop-caches")
@router.post("/drop-caches")
async def action_drop_caches():
    """Drop Linux kernel PageCache, dentries, and inodes via PolicyKit."""
    return await drop_memory_caches()


@router.post("/rescue/swap-refresh")
async def action_swap_refresh():
    """Safely cycle swapoff/swapon via PolicyKit when free RAM is sufficient."""
    return await refresh_swap()


@router.post("/rescue/focus-mode")
@router.post("/focus-mode")
async def action_focus_mode(req: Optional[FocusModeRequest] = None):
    """Toggle Dev Focus Mode to pause or restore heavy background services."""
    target_enable = (
        req.enable
        if (req is not None and req.enable is not None)
        else (not get_focus_mode_state())
    )
    custom_svcs = req.services if req is not None else None
    return await toggle_dev_focus_mode(enable=target_enable, custom_services=custom_svcs)


@router.post("/rescue/enable-zram")
async def action_enable_zram():
    """Configure and enable a compressed ZRAM swap device via PolicyKit."""
    return await enable_zram_swap()


@router.get("/dns")
async def get_dns_status():
    """Return active DNS profile and latency."""
    return await refresh_network_indicators(force=True)


@router.post("/dns/switch")
async def action_switch_dns(req: DnsSwitchRequest):
    """Switch active interface DNS profile (Shecan / 1.1.1.1 / Auto)."""
    return await switch_dns_profile(req.profile)


@router.get("/policies")
async def get_guard_policies():
    """Return current System Guard policies, thresholds, and recent triggered alerts."""
    return policy_guard.get_state()


@router.put("/policies")
@router.post("/policies")
async def update_guard_policies(req: PolicyUpdateRequest):
    """Update System Guard policy toggles and thresholds."""
    return policy_guard.update_policies(req.policies)


@router.post("/policies/test-notification")
@router.post("/policies/test")
async def test_guard_notification():
    """Send an immediate test desktop notification via notify-send."""
    return await policy_guard.trigger_test_notification()


@router.post("/policies/clear-logs")
async def clear_guard_alert_logs():
    """Clear recent triggered alert logs."""
    return policy_guard.clear_alerts()
