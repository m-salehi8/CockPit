import asyncio
import os
import time
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional
import psutil
from services.executor import run_cmd, run_shell_cmd


# State tracker for network & disk I/O rate calculations (zero memory growth)
class MetricsState:
    def __init__(self) -> None:
        self.last_time: float = 0.0
        self.last_net_sent: int = 0
        self.last_net_recv: int = 0
        self.last_disk_read: int = 0
        self.last_disk_write: int = 0
        self.focus_mode_active: bool = False
        self.stopped_by_focus_mode: List[str] = []
        self.dns_profile: str = "Auto"
        self.dns_servers: List[str] = []
        self.dns_last_check: float = 0.0
        self.ping_ms: Optional[int] = None
        self.ping_last_check: float = 0.0


_state = MetricsState()

# Map common sub-process executable names to canonical application group names
APP_GROUP_ALIASES = {
    "chrome": "Google Chrome",
    "google-chrome": "Google Chrome",
    "chromium": "Chromium Browser",
    "chromium-browser": "Chromium Browser",
    "brave": "Brave Browser",
    "firefox": "Mozilla Firefox",
    "firefox-bin": "Mozilla Firefox",
    "code": "VS Code",
    "codium": "VSCodium",
    "cursor": "Cursor IDE",
    "pycharm": "PyCharm",
    "idea": "IntelliJ IDEA",
    "webstorm": "WebStorm",
    "goland": "GoLand",
    "dockerd": "Docker Engine",
    "containerd": "Docker / Containerd",
    "containerd-shim": "Docker / Containerd",
    "containerd-shim-runc-v2": "Docker / Containerd",
    "postgres": "PostgreSQL",
    "redis-server": "Redis Server",
    "mysqld": "MySQL Server",
    "mariadbd": "MariaDB Server",
    "node": "Node.js Runtime",
    "python": "Python Runtime",
    "python3": "Python Runtime",
    "uvicorn": "Python / Uvicorn",
    "gnome-shell": "GNOME Desktop Shell",
    "Xorg": "Xorg Display Server",
    "Xwayland": "Xwayland Display",
    "snapd": "Snap Daemon",
    "slack": "Slack",
    "discord": "Discord",
    "telegram-desktop": "Telegram Desktop",
    "spotify": "Spotify",
}


def _read_sysfs_str(path: Path) -> Optional[str]:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        pass
    return None


def _read_sysfs_int(path: Path) -> Optional[int]:
    val = _read_sysfs_str(path)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return None


def get_cpu_temperature() -> Optional[float]:
    """Read CPU package temperature via psutil or direct /sys/class/thermal sysfs."""
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ("coretemp", "k10temp", "zenpower", "acpitz", "cpu_thermal"):
                if key in temps and temps[key]:
                    return round(temps[key][0].current, 1)
            for entries in temps.values():
                if entries:
                    return round(entries[0].current, 1)
    except Exception:
        pass

    # Fallback direct sysfs read
    thermal_base = Path("/sys/class/thermal")
    if thermal_base.exists():
        for zone in sorted(thermal_base.glob("thermal_zone*")):
            val = _read_sysfs_int(zone / "temp")
            if val and val > 0:
                return round(val / 1000.0, 1)
    return None


def get_battery_details() -> Dict[str, Any]:
    """Read battery percentage, status, time left, and real-time wattage from /sys/class/power_supply."""
    info: Dict[str, Any] = {
        "present": False,
        "percent": None,
        "power_plugged": None,
        "wattage": None,
        "status": "AC / Desktop",
        "secsleft": None,
    }
    try:
        batt = psutil.sensors_battery()
        if batt is not None:
            info["present"] = True
            info["percent"] = round(batt.percent, 1)
            info["power_plugged"] = bool(batt.power_plugged)
            info["secsleft"] = (
                batt.secsleft
                if batt.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
                else None
            )
    except Exception:
        pass

    ps_base = Path("/sys/class/power_supply")
    if ps_base.exists():
        for bat_dir in sorted(ps_base.glob("BAT*")):
            info["present"] = True
            status = _read_sysfs_str(bat_dir / "status")
            if status:
                info["status"] = status
            power_uw = _read_sysfs_int(bat_dir / "power_now")
            if power_uw is not None:
                info["wattage"] = round(power_uw / 1_000_000.0, 2)
            else:
                curr_ua = _read_sysfs_int(bat_dir / "current_now")
                volt_uv = _read_sysfs_int(bat_dir / "voltage_now")
                if curr_ua is not None and volt_uv is not None:
                    info["wattage"] = round((curr_ua * volt_uv) / 1e12, 2)
            break

    return info


def get_zram_details() -> Dict[str, Any]:
    """Parse /proc/swaps and /sys/block/zram* directly to avoid subprocess overhead."""
    zram_devices: List[Dict[str, Any]] = []
    total_zram_disk_bytes = 0
    total_zram_orig_bytes = 0
    total_zram_compr_bytes = 0

    sys_block = Path("/sys/block")
    if sys_block.exists():
        for zdir in sorted(sys_block.glob("zram*")):
            disksize = _read_sysfs_int(zdir / "disksize") or 0
            mm_stat = _read_sysfs_str(zdir / "mm_stat")
            orig_size = 0
            compr_size = 0
            mem_used = 0
            if mm_stat:
                parts = mm_stat.split()
                if len(parts) >= 3:
                    try:
                        orig_size = int(parts[0])
                        compr_size = int(parts[1])
                        mem_used = int(parts[2])
                    except ValueError:
                        pass
            if disksize > 0:
                total_zram_disk_bytes += disksize
                total_zram_orig_bytes += orig_size
                total_zram_compr_bytes += compr_size
                ratio = round(orig_size / compr_size, 2) if compr_size > 0 else 1.0
                zram_devices.append({
                    "device": zdir.name,
                    "disksize_bytes": disksize,
                    "orig_data_bytes": orig_size,
                    "compr_data_bytes": compr_size,
                    "mem_used_bytes": mem_used,
                    "compression_ratio": ratio,
                })

    swaps: List[Dict[str, Any]] = []
    proc_swaps = Path("/proc/swaps")
    if proc_swaps.exists():
        try:
            lines = proc_swaps.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    swaps.append({
                        "filename": parts[0],
                        "type": parts[1],
                        "size_bytes": int(parts[2]) * 1024,
                        "used_bytes": int(parts[3]) * 1024,
                        "priority": int(parts[4]),
                    })
        except Exception:
            pass

    return {
        "enabled": len(zram_devices) > 0,
        "devices": zram_devices,
        "total_disksize_bytes": total_zram_disk_bytes,
        "total_orig_bytes": total_zram_orig_bytes,
        "total_compr_bytes": total_zram_compr_bytes,
        "swaps": swaps,
    }


def collect_live_metrics() -> Dict[str, Any]:
    """
    Collect full live system metrics using direct psutil and /proc /sys reads.
    Called only when at least one WebSocket client is connected.
    """
    now = time.monotonic()
    dt = now - _state.last_time if _state.last_time > 0 else 0.0

    # CPU usage per core and overall
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    cpu_total = round(sum(per_core) / len(per_core), 1) if per_core else 0.0

    freq_info = psutil.cpu_freq()
    cpu_freq_mhz = round(freq_info.current, 0) if freq_info else None
    cpu_freq_max = round(freq_info.max, 0) if freq_info and freq_info.max else None

    load_1, load_5, load_15 = os.getloadavg()

    # Memory & Swap breakdown
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    zram = get_zram_details()

    # Disk I/O rates
    dio = psutil.disk_io_counters()
    read_bytes = dio.read_bytes if dio else 0
    write_bytes = dio.write_bytes if dio else 0
    disk_read_rate = 0.0
    disk_write_rate = 0.0
    if dt > 0 and _state.last_disk_read > 0:
        disk_read_rate = max(0.0, (read_bytes - _state.last_disk_read) / dt)
        disk_write_rate = max(0.0, (write_bytes - _state.last_disk_write) / dt)

    # Network I/O rates
    nio = psutil.net_io_counters()
    net_sent = nio.bytes_sent if nio else 0
    net_recv = nio.bytes_recv if nio else 0
    net_up_rate = 0.0
    net_down_rate = 0.0
    if dt > 0 and _state.last_net_sent > 0:
        net_up_rate = max(0.0, (net_sent - _state.last_net_sent) / dt)
        net_down_rate = max(0.0, (net_recv - _state.last_net_recv) / dt)

    _state.last_time = now
    _state.last_disk_read = read_bytes
    _state.last_disk_write = write_bytes
    _state.last_net_sent = net_sent
    _state.last_net_recv = net_recv

    # Self memory footprint check (Backend RSS)
    self_rss_bytes = psutil.Process(os.getpid()).memory_info().rss

    # Pressure advice for 8GB RAM laptops
    available_gb = vm.available / (1024 ** 3)
    if available_gb < 0.85:
        pressure_level = "critical"
        pressure_msg = "Critical RAM pressure (<850 MB available). Drop caches or enable Dev Focus Mode immediately."
    elif available_gb < 1.8:
        pressure_level = "elevated"
        pressure_msg = "Elevated RAM usage. Consider closing unused browser tabs or dropping slab caches."
    else:
        pressure_level = "optimal"
        pressure_msg = "Memory headroom is healthy for an 8GB system."

    return {
        "timestamp": time.time(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "backend_rss_mb": round(self_rss_bytes / (1024 * 1024), 2),
        "focus_mode_active": _state.focus_mode_active,
        "stopped_by_focus_mode": _state.stopped_by_focus_mode,
        "cpu": {
            "total_percent": cpu_total,
            "per_core_percent": [round(c, 1) for c in per_core],
            "core_count": len(per_core),
            "freq_mhz": cpu_freq_mhz,
            "freq_max_mhz": cpu_freq_max,
            "temperature_c": get_cpu_temperature(),
            "load_avg": [round(load_1, 2), round(load_5, 2), round(load_15, 2)],
        },
        "memory": {
            "total_bytes": vm.total,
            "available_bytes": vm.available,
            "used_bytes": vm.used,
            "free_bytes": vm.free,
            "active_bytes": getattr(vm, "active", 0),
            "inactive_bytes": getattr(vm, "inactive", 0),
            "buffers_bytes": getattr(vm, "buffers", 0),
            "cached_bytes": getattr(vm, "cached", 0),
            "shared_bytes": getattr(vm, "shared", 0),
            "slab_bytes": getattr(vm, "slab", 0),
            "percent": round(vm.percent, 1),
            "pressure_level": pressure_level,
            "pressure_message": pressure_msg,
        },
        "swap": {
            "total_bytes": sm.total,
            "used_bytes": sm.used,
            "free_bytes": sm.free,
            "percent": round(sm.percent, 1),
            "sin_bytes": sm.sin,
            "sout_bytes": sm.sout,
            "zram": zram,
        },
        "disk_io": {
            "read_bytes_per_sec": round(disk_read_rate, 1),
            "write_bytes_per_sec": round(disk_write_rate, 1),
            "total_read_bytes": read_bytes,
            "total_write_bytes": write_bytes,
        },
        "network": {
            "upload_bytes_per_sec": round(net_up_rate, 1),
            "download_bytes_per_sec": round(net_down_rate, 1),
            "total_sent_bytes": net_sent,
            "total_recv_bytes": net_recv,
            "dns_profile": _state.dns_profile,
            "dns_servers": _state.dns_servers,
            "ping_ms": _state.ping_ms,
        },
        "battery": get_battery_details(),
    }


async def refresh_network_indicators(force: bool = False) -> Dict[str, Any]:
    """
    Lightweight on-demand check for current DNS profile and gateway/resolver TCP latency.
    Cached for 6 seconds unless force=True to keep CPU and RAM footprint near zero.
    """
    now = time.monotonic()

    if force or (now - _state.dns_last_check) >= 6.0:
        _state.dns_last_check = now
        res = await run_cmd(["resolvectl", "dns"], timeout=2.5)
        raw = res["stdout"] if res["success"] else ""
        servers: List[str] = []
        for line in raw.splitlines():
            if ":" in line:
                after = line.split(":", 1)[1].strip()
                if after:
                    for token in after.split():
                        if token not in servers:
                            servers.append(token)
        _state.dns_servers = servers
        joined = " ".join(servers)
        if "178.22.122.100" in joined or "185.51.200.2" in joined:
            _state.dns_profile = "Shecan"
        elif "1.1.1.1" in joined or "1.0.0.1" in joined:
            _state.dns_profile = "1.1.1.1"
        else:
            _state.dns_profile = "Auto"

    if force or (now - _state.ping_last_check) >= 4.5:
        _state.ping_last_check = now
        target_host = "1.1.1.1"
        if _state.dns_servers:
            first_srv = _state.dns_servers[0]
            if "." in first_srv:
                target_host = first_srv
        t0 = time.monotonic()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, 53), timeout=1.2
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            _state.ping_ms = max(1, int((time.monotonic() - t0) * 1000))
        except Exception:
            # Fallback check to 1.1.1.1:53 if local resolver port 53 refused
            try:
                t1 = time.monotonic()
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection("1.1.1.1", 53), timeout=1.2
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                _state.ping_ms = max(1, int((time.monotonic() - t1) * 1000))
            except Exception:
                _state.ping_ms = None

    return {
        "dns_profile": _state.dns_profile,
        "dns_servers": _state.dns_servers,
        "ping_ms": _state.ping_ms,
    }


async def switch_dns_profile(profile: str) -> Dict[str, Any]:
    """
    Switch active network interface DNS between Shecan, Cloudflare (1.1.1.1), and Auto (DHCP).
    """
    target = profile.lower().strip()
    if target == "shecan":
        script = (
            "IFACE=$(ip route show default | awk '{print $5}' | head -n1); "
            "resolvectl dns \"$IFACE\" 178.22.122.100 185.51.200.2 && resolvectl flush-caches"
        )
        label = "Shecan"
    elif target in ("cloudflare", "1.1.1.1"):
        script = (
            "IFACE=$(ip route show default | awk '{print $5}' | head -n1); "
            "resolvectl dns \"$IFACE\" 1.1.1.1 1.0.0.1 && resolvectl flush-caches"
        )
        label = "1.1.1.1"
    else:
        script = (
            "IFACE=$(ip route show default | awk '{print $5}' | head -n1); "
            "resolvectl revert \"$IFACE\" && resolvectl flush-caches"
        )
        label = "Auto"

    res = await run_cmd(["sh", "-c", script], timeout=30.0, use_pkexec=True)
    await refresh_network_indicators(force=True)
    return {
        "success": res["success"],
        "dns_profile": _state.dns_profile,
        "dns_servers": _state.dns_servers,
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "message": (
            f"DNS switched to {label}."
            if res["success"]
            else f"DNS switch cancelled or failed: {res['stderr']}"
        ),
    }


async def enable_zram_swap() -> Dict[str, Any]:
    """
    Configure and activate a compressed ZRAM swap device (50% of physical RAM) via pkexec.
    """
    zram_now = get_zram_details()
    if zram_now["enabled"]:
        return {
            "success": True,
            "message": "ZRAM is already active on this system.",
            "zram": zram_now,
        }

    total_mem = psutil.virtual_memory().total
    zram_size_bytes = max(1024 * 1024 * 1024, total_mem // 2)

    script = (
        "modprobe zram && "
        " DEV=$(zramctl --find --size " + str(zram_size_bytes) + " --algorithm zstd 2>/dev/null "
        "|| zramctl --find --size " + str(zram_size_bytes) + ") && "
        "mkswap \"$DEV\" && swapon -p 100 \"$DEV\""
    )
    res = await run_cmd(["sh", "-c", script], timeout=45.0, use_pkexec=True)
    updated_zram = get_zram_details()
    return {
        "success": res["success"] and updated_zram["enabled"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "zram": updated_zram,
        "message": (
            f"ZRAM compressed swap enabled ({round(zram_size_bytes / (1024**3), 1)} GB)."
            if res["success"]
            else f"Failed to enable ZRAM: {res['stderr']}"
        ),
    }


def _resolve_group_name(name: str, cmdline: List[str]) -> str:
    """Resolve canonical application group name from process name and command line."""
    base = name.lower().strip()
    if base in APP_GROUP_ALIASES:
        return APP_GROUP_ALIASES[base]

    if cmdline:
        first_arg = os.path.basename(cmdline[0]).lower()
        for key, label in APP_GROUP_ALIASES.items():
            if key == first_arg or first_arg.startswith(key + "-"):
                return label
        joined = " ".join(cmdline[:4]).lower()
        if "/snap/" in joined:
            parts = joined.split("/snap/")
            if len(parts) > 1:
                snap_app = parts[1].split("/")[0]
                if snap_app:
                    return f"Snap: {snap_app.capitalize()}"
        if "code" in first_arg or "/usr/share/code" in joined:
            return "VS Code"
        if "chrome" in first_arg:
            return "Google Chrome"
        if "firefox" in first_arg:
            return "Mozilla Firefox"
        if "pycharm" in joined:
            return "PyCharm"
        if "docker" in first_arg:
            return "Docker Engine"

    return name


def get_grouped_processes(limit: int = 40) -> Dict[str, Any]:
    """
    Aggregate running processes by parent application name to expose true total RAM consumption
    for heavy multi-process applications (e.g. Chrome, VS Code, Docker, PyCharm, Python).
    Uses PSS (Proportional Set Size) when readable from /proc/[pid]/smaps_rollup, falling back to RSS,
    or sums RSS and USS accurately.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    total_procs = 0

    attrs = ["pid", "ppid", "name", "username", "cpu_percent", "memory_info", "cmdline", "status"]
    for proc in psutil.process_iter(attrs=attrs):
        try:
            info = proc.info
            pid = info["pid"]
            name = info["name"] or "unknown"
            mem_info = info["memory_info"]
            if not mem_info:
                continue

            rss = mem_info.rss
            if rss <= 0:
                continue

            total_procs += 1
            cmdline = info.get("cmdline") or []
            cpu_pct = info.get("cpu_percent") or 0.0
            username = info.get("username") or "root"

            group_key = _resolve_group_name(name, cmdline)
            if group_key not in groups:
                groups[group_key] = {
                    "group_name": group_key,
                    "base_executable": name,
                    "total_rss_bytes": 0,
                    "total_cpu_percent": 0.0,
                    "process_count": 0,
                    "user": username,
                    "pids": [],
                    "processes": [],
                }

            g = groups[group_key]
            g["total_rss_bytes"] += rss
            g["total_cpu_percent"] = round(g["total_cpu_percent"] + cpu_pct, 1)
            g["process_count"] += 1
            g["pids"].append(pid)
            g["processes"].append({
                "pid": pid,
                "ppid": info.get("ppid"),
                "name": name,
                "user": username,
                "rss_bytes": rss,
                "cpu_percent": round(cpu_pct, 1),
                "cmdline": " ".join(cmdline[:6]) if cmdline else name,
                "status": info.get("status", "running"),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    vm_total = psutil.virtual_memory().total
    sorted_groups = sorted(
        groups.values(), key=lambda x: x["total_rss_bytes"], reverse=True
    )[:limit]

    for g in sorted_groups:
        g["memory_percent"] = round((g["total_rss_bytes"] / vm_total) * 100.0, 1) if vm_total else 0.0
        g["processes"] = sorted(g["processes"], key=lambda p: p["rss_bytes"], reverse=True)[:25]

    return {
        "total_process_count": total_procs,
        "group_count": len(groups),
        "groups": sorted_groups,
    }


async def kill_processes(pids: List[int], force: bool = False) -> Dict[str, Any]:
    """
    Terminate or force-kill a list of PIDs. Protects PID 1 and the current backend process.
    Falls back to pkexec kill if permission is denied for root processes.
    """
    self_pid = os.getpid()
    sig = signal.SIGKILL if force else signal.SIGTERM
    killed: List[int] = []
    need_root: List[int] = []
    errors: List[str] = []

    for pid in pids:
        if pid <= 1 or pid == self_pid:
            errors.append(f"Skipped protected PID {pid}")
            continue
        try:
            os.kill(pid, sig)
            killed.append(pid)
        except ProcessLookupError:
            continue
        except PermissionError:
            need_root.append(pid)
        except Exception as exc:
            errors.append(f"PID {pid}: {exc}")

    if need_root:
        sig_flag = "-9" if force else "-15"
        cmd = ["kill", sig_flag] + [str(p) for p in need_root]
        res = await run_cmd(cmd, use_pkexec=True)
        if res["success"]:
            killed.extend(need_root)
        else:
            errors.append(res["stderr"] or "PolicyKit authentication failed or declined.")

    return {
        "success": len(errors) == 0 or len(killed) > 0,
        "killed_pids": killed,
        "errors": errors,
        "message": f"Signaled {len(killed)} process(es) ({'SIGKILL' if force else 'SIGTERM'}).",
    }


async def drop_memory_caches() -> Dict[str, Any]:
    """
    Execute `pkexec sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"` and measure reclaimed RAM.
    """
    before_avail = psutil.virtual_memory().available
    res = await run_cmd(
        ["sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"],
        timeout=30.0,
        use_pkexec=True,
    )
    after_avail = psutil.virtual_memory().available
    freed_bytes = max(0, after_avail - before_avail)
    freed_mb = round(freed_bytes / (1024 * 1024), 1)

    return {
        "success": res["success"],
        "freed_bytes": freed_bytes,
        "freed_mb": freed_mb,
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "message": (
            f"PageCache, dentries, and inodes dropped. Reclaimed ~{freed_mb} MB available RAM."
            if res["success"]
            else f"Failed to drop caches: {res['stderr']}"
        ),
    }


async def refresh_swap() -> Dict[str, Any]:
    """
    Safely cycle swap (`swapoff -a && swapon -a`) after verifying free/available physical RAM
    exceeds currently used swap with a safe 350MB margin.
    """
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    safety_margin = 350 * 1024 * 1024

    if sm.total == 0:
        return {
            "success": False,
            "message": "No active swap devices or ZRAM partitions detected on this system.",
        }

    if vm.available <= (sm.used + safety_margin):
        avail_mb = round(vm.available / (1024 * 1024))
        swap_used_mb = round(sm.used / (1024 * 1024))
        return {
            "success": False,
            "message": (
                f"Unsafe to cycle swap right now: {swap_used_mb} MB swap is in use, "
                f"but only {avail_mb} MB RAM is available. Drop caches or close apps first."
            ),
        }

    res = await run_cmd(
        ["sh", "-c", "swapoff -a && swapon -a"],
        timeout=120.0,
        use_pkexec=True,
    )
    return {
        "success": res["success"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "message": (
            "Swap space flushed back into RAM and re-enabled cleanly."
            if res["success"]
            else f"Swap refresh failed: {res['stderr']}"
        ),
    }


DEFAULT_FOCUS_SERVICES = [
    "docker",
    "docker.socket",
    "postgresql",
    "redis-server",
    "redis",
    "mysql",
    "mariadb",
    "snapd",
    "snapd.socket",
]


async def get_active_services_subset(candidates: List[str]) -> List[str]:
    """Return which services from candidates are currently active."""
    active: List[str] = []
    for svc in candidates:
        res = await run_cmd(["systemctl", "is-active", svc], timeout=5.0)
        if res["stdout"].strip() == "active":
            active.append(svc)
    return active


async def toggle_dev_focus_mode(
    enable: bool, custom_services: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Dev Focus Mode (Panic Button):
    When enabled, detects currently running heavy background services from the target list,
    stops them with a single pkexec systemctl call, and stores the list so toggling off
    restores the exact services that were running.
    """
    targets = custom_services if custom_services else DEFAULT_FOCUS_SERVICES
    vm_before = psutil.virtual_memory().available

    if enable:
        currently_active = await get_active_services_subset(targets)
        if not currently_active:
            _state.focus_mode_active = True
            _state.stopped_by_focus_mode = []
            return {
                "success": True,
                "focus_mode_active": True,
                "services_affected": [],
                "freed_mb": 0.0,
                "message": "Dev Focus Mode enabled (no heavy background services were running).",
            }

        res = await run_cmd(
            ["systemctl", "stop"] + currently_active,
            timeout=60.0,
            use_pkexec=True,
        )
        vm_after = psutil.virtual_memory().available
        freed_mb = round(max(0, vm_after - vm_before) / (1024 * 1024), 1)
        if res["success"]:
            _state.focus_mode_active = True
            _state.stopped_by_focus_mode = currently_active
            return {
                "success": True,
                "focus_mode_active": True,
                "services_affected": currently_active,
                "freed_mb": freed_mb,
                "message": (
                    f"Dev Focus Mode ON: Stopped {', '.join(currently_active)}. "
                    f"Freed ~{freed_mb} MB RAM."
                ),
            }
        return {
            "success": False,
            "focus_mode_active": _state.focus_mode_active,
            "services_affected": [],
            "message": f"Failed to stop services: {res['stderr']}",
        }
    else:
        to_restore = _state.stopped_by_focus_mode or [
            s for s in targets if not s.endswith(".socket")
        ]
        if not to_restore:
            _state.focus_mode_active = False
            return {
                "success": True,
                "focus_mode_active": False,
                "services_affected": [],
                "message": "Dev Focus Mode disabled.",
            }

        res = await run_cmd(
            ["systemctl", "start"] + to_restore,
            timeout=60.0,
            use_pkexec=True,
        )
        if res["success"]:
            restored = list(to_restore)
            _state.focus_mode_active = False
            _state.stopped_by_focus_mode = []
            return {
                "success": True,
                "focus_mode_active": False,
                "services_affected": restored,
                "message": f"Dev Focus Mode OFF: Restored {', '.join(restored)}.",
            }
        return {
            "success": False,
            "focus_mode_active": _state.focus_mode_active,
            "services_affected": [],
            "message": f"Failed to restore services: {res['stderr']}",
        }
