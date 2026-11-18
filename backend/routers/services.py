import os
import re
import socket
from typing import Dict, Any, List, Optional
import psutil
from fastapi import APIRouter
from pydantic import BaseModel
from services.executor import run_cmd
from services.metrics import kill_processes

router = APIRouter(prefix="/api/network", tags=["network_and_services"])


TRACKED_SERVICES = [
    {"unit": "docker", "label": "Docker Engine", "category": "Containers", "icon": "container"},
    {"unit": "postgresql", "label": "PostgreSQL Database", "category": "Database", "icon": "database"},
    {"unit": "redis-server", "alt_unit": "redis", "label": "Redis In-Memory Store", "category": "Database", "icon": "zap"},
    {"unit": "nginx", "label": "Nginx Web Server", "category": "Web / Proxy", "icon": "globe"},
    {"unit": "mysql", "alt_unit": "mariadb", "label": "MySQL / MariaDB", "category": "Database", "icon": "database"},
    {"unit": "ssh", "alt_unit": "sshd", "label": "OpenSSH Server", "category": "Network", "icon": "terminal"},
    {"unit": "ufw", "label": "Uncomplicated Firewall (UFW)", "category": "Security", "icon": "shield"},
    {"unit": "snapd", "label": "Ubuntu Snap Daemon", "category": "System", "icon": "package"},
    {"unit": "cron", "label": "Cron Task Scheduler", "category": "System", "icon": "clock"},
    {"unit": "bluetooth", "label": "Bluetooth Stack", "category": "Hardware", "icon": "radio"},
]


class KillPortRequest(BaseModel):
    port: int
    pid: Optional[int] = None
    force: bool = False


class ServiceActionRequest(BaseModel):
    unit: str
    action: str  # "start" | "stop" | "restart" | "enable" | "disable"


def list_listening_ports_psutil() -> List[Dict[str, Any]]:
    """
    Collect all listening TCP and UDP bound sockets using psutil.net_connections
    and enrich with process metadata.
    """
    entries: List[Dict[str, Any]] = []
    seen_keys = set()

    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        conns = []

    for c in conns:
        is_tcp = c.type == socket.SOCK_STREAM
        is_udp = c.type == socket.SOCK_DGRAM
        if is_tcp and c.status != psutil.CONN_LISTEN:
            continue
        if not c.laddr:
            continue

        ip = c.laddr.ip
        port = c.laddr.port
        proto = "TCP" if is_tcp else "UDP"
        pid = c.pid

        key = (proto, port, pid or 0, ip)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        proc_name = "system / root"
        user = "root"
        cmdline = ""
        rss_bytes = 0

        if pid:
            try:
                p = psutil.Process(pid)
                proc_name = p.name()
                user = p.username()
                raw_cmd = p.cmdline()
                cmdline = " ".join(raw_cmd[:6]) if raw_cmd else proc_name
                rss_bytes = p.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        entries.append({
            "protocol": proto,
            "address": ip,
            "port": port,
            "pid": pid,
            "process_name": proc_name,
            "user": user,
            "cmdline": cmdline,
            "rss_bytes": rss_bytes,
            "is_common_dev_port": port in {
                3000, 3001, 4000, 4200, 5000, 5173, 5432, 5672,
                6379, 8000, 8080, 8081, 8443, 8765, 8888, 9000, 27017
            },
        })

    entries.sort(key=lambda x: (not x["is_common_dev_port"], x["port"]))
    return entries


async def list_listening_ports_fallback() -> List[Dict[str, Any]]:
    """
    Enrich psutil results with `ss -tulnp` so root-owned processes without PIDs in
    unprivileged psutil still display accurate port rows.
    """
    items = list_listening_ports_psutil()
    known_ports = {(i["protocol"], i["port"], i["address"]) for i in items}

    res = await run_cmd(["ss", "-tulnp"], timeout=5.0)
    if res["success"] and res["stdout"]:
        for line in res["stdout"].splitlines()[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            proto = parts[0].upper()
            if not (proto.startswith("TCP") or proto.startswith("UDP")):
                continue
            proto_clean = "TCP" if proto.startswith("TCP") else "UDP"
            local_addr = parts[4]
            if ":" not in local_addr:
                continue
            addr_part, port_str = local_addr.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                continue

            if (proto_clean, port, addr_part) in known_ports:
                continue

            pid = None
            proc_name = "root / daemon"
            m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
            if m:
                proc_name = m.group(1)
                pid = int(m.group(2))

            items.append({
                "protocol": proto_clean,
                "address": addr_part,
                "port": port,
                "pid": pid,
                "process_name": proc_name,
                "user": "root",
                "cmdline": proc_name,
                "rss_bytes": 0,
                "is_common_dev_port": port in {
                    3000, 3001, 4000, 4200, 5000, 5173, 5432, 5672,
                    6379, 8000, 8080, 8081, 8443, 8765, 8888, 9000, 27017
                },
            })
            known_ports.add((proto_clean, port, addr_part))

    items.sort(key=lambda x: (not x["is_common_dev_port"], x["port"]))
    return items


@router.get("/ports")
async def get_active_ports():
    """Return all listening TCP and UDP ports with PID, process name, and RAM footprint."""
    ports = await list_listening_ports_fallback()
    return {
        "self_pid": os.getpid(),
        "count": len(ports),
        "ports": ports,
    }


@router.post("/ports/kill")
async def kill_port_process(req: KillPortRequest):
    """Kill the process bound to a specific port (by PID or via fuser fallback)."""
    if req.port == 8765 and req.pid == os.getpid():
        return {
            "success": False,
            "message": "Protected: Port 8765 is the active Cockpit Control Center UI server.",
        }

    if req.pid:
        return await kill_processes([req.pid], force=req.force)

    # If PID was hidden because process belongs to root, use pkexec fuser -k
    sig_flag = "-KILL" if req.force else "-TERM"
    res = await run_cmd(
        ["fuser", "-k", sig_flag, f"{req.port}/tcp"],
        timeout=15.0,
        use_pkexec=True,
    )
    return {
        "success": res["success"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "message": (
            f"Freed port {req.port}."
            if res["success"]
            else f"Could not kill process on port {req.port}: {res['stderr']}"
        ),
    }


@router.get("/services")
async def get_systemd_services():
    """Query status, PID, memory usage, and boot state of key developer systemd services."""
    results: List[Dict[str, Any]] = []

    for item in TRACKED_SERVICES:
        unit = item["unit"]
        alt_unit = item.get("alt_unit")

        res = await run_cmd(
            [
                "systemctl",
                "show",
                unit,
                "--property=Id,LoadState,ActiveState,SubState,MainPID,MemoryCurrent,UnitFileState,Description",
            ],
            timeout=5.0,
        )
        props: Dict[str, str] = {}
        for line in res["stdout"].splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v

        if props.get("LoadState") == "not-found" and alt_unit:
            res_alt = await run_cmd(
                [
                    "systemctl",
                    "show",
                    alt_unit,
                    "--property=Id,LoadState,ActiveState,SubState,MainPID,MemoryCurrent,UnitFileState,Description",
                ],
                timeout=5.0,
            )
            props_alt: Dict[str, str] = {}
            for line in res_alt["stdout"].splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    props_alt[k] = v
            if props_alt.get("LoadState") != "not-found":
                props = props_alt
                unit = alt_unit

        load_state = props.get("LoadState", "not-found")
        active_state = props.get("ActiveState", "inactive")
        sub_state = props.get("SubState", "dead")
        unit_file_state = props.get("UnitFileState", "disabled")
        main_pid = int(props.get("MainPID", "0") or 0)

        mem_raw = props.get("MemoryCurrent", "0")
        try:
            mem_bytes = int(mem_raw) if mem_raw.isdigit() else 0
            # Systemd returns uint64 max (18446744073709551615) when accounting is unset
            if mem_bytes > (1 << 50):
                mem_bytes = 0
        except ValueError:
            mem_bytes = 0

        if mem_bytes == 0 and main_pid > 0:
            try:
                mem_bytes = psutil.Process(main_pid).memory_info().rss
            except Exception:
                mem_bytes = 0

        results.append({
            "unit": unit,
            "label": item["label"],
            "category": item["category"],
            "icon": item["icon"],
            "installed": load_state == "loaded",
            "load_state": load_state,
            "active_state": active_state,
            "sub_state": sub_state,
            "is_active": active_state == "active",
            "enabled": unit_file_state in ("enabled", "enabled-runtime", "static"),
            "unit_file_state": unit_file_state,
            "main_pid": main_pid if main_pid > 0 else None,
            "memory_bytes": mem_bytes,
            "description": props.get("Description", item["label"]),
        })

    return {"services": results}


@router.post("/services/action")
async def control_systemd_service(req: ServiceActionRequest):
    """Execute start, stop, restart, enable, or disable on a systemd service using pkexec."""
    allowed_actions = {"start", "stop", "restart", "enable", "disable"}
    action = req.action.lower().strip()
    if action not in allowed_actions:
        return {"success": False, "message": f"Unsupported action: {action}"}

    # Validate unit name characters
    if not re.match(r"^[a-zA-Z0-9_.@-]+$", req.unit):
        return {"success": False, "message": "Invalid systemd unit identifier."}

    res = await run_cmd(
        ["systemctl", action, req.unit],
        timeout=45.0,
        use_pkexec=True,
    )
    return {
        "success": res["success"],
        "unit": req.unit,
        "action": action,
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "message": (
            f"Service '{req.unit}' {action}ed successfully."
            if res["success"]
            else f"Failed to {action} '{req.unit}': {res['stderr']}"
        ),
    }
