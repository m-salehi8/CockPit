import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.executor import run_cmd
from services.metrics import drop_memory_caches, get_lite_vitals

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ICON_PATH = str(PROJECT_ROOT / "cockpit.svg")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POLICIES_FILE = DATA_DIR / "policies.json"

COOLDOWN_SECONDS = 300.0  # 5 minutes cooldown per rule
CHECK_INTERVAL_SECONDS = 5.0

DEFAULT_POLICIES: Dict[str, Any] = {
    "ram_pressure": {
        "id": "ram_pressure",
        "name": "High RAM Pressure Alert",
        "description": "Alert when physical RAM usage stays above threshold for 10s, naming the top memory consumer.",
        "enabled": True,
        "threshold": 85,
        "min": 50,
        "max": 98,
        "unit": "%",
        "min_breach_checks": 2,
    },
    "auto_rescue_ram": {
        "id": "auto_rescue_ram",
        "name": "Auto-Free RAM Cache on Critical Pressure",
        "description": "Automatically flush kernel page caches and notify when RAM exceeds critical threshold.",
        "enabled": True,
        "threshold": 92,
        "min": 75,
        "max": 99,
        "unit": "%",
        "min_breach_checks": 2,
    },
    "cpu_thermal": {
        "id": "cpu_thermal",
        "name": "CPU Thermal Guard",
        "description": "Alert when CPU package temperature exceeds safe operating threshold for 10s.",
        "enabled": True,
        "threshold": 85,
        "min": 60,
        "max": 100,
        "unit": "°C",
        "min_breach_checks": 2,
    },
    "cpu_load": {
        "id": "cpu_load",
        "name": "Sustained High CPU Load",
        "description": "Alert when total CPU load exceeds threshold continuously for more than 20 seconds.",
        "enabled": True,
        "threshold": 90,
        "min": 50,
        "max": 99,
        "unit": "%",
        "min_breach_checks": 4,
    },
    "swap_thrashing": {
        "id": "swap_thrashing",
        "name": "Swap Thrashing Warning",
        "description": "Alert when swap/ZRAM utilization exceeds threshold for 10s.",
        "enabled": True,
        "threshold": 80,
        "min": 40,
        "max": 98,
        "unit": "%",
        "min_breach_checks": 2,
    },
}


class PolicyGuardEngine:
    def __init__(self) -> None:
        self.policies: Dict[str, Dict[str, Any]] = {}
        self.alerts_log: List[Dict[str, Any]] = []
        self.breach_counts: Dict[str, int] = {k: 0 for k in DEFAULT_POLICIES}
        self.last_fired: Dict[str, float] = {k: 0.0 for k in DEFAULT_POLICIES}
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._load_state()

    def _load_state(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        merged: Dict[str, Dict[str, Any]] = {}
        for key, default_cfg in DEFAULT_POLICIES.items():
            merged[key] = dict(default_cfg)

        if POLICIES_FILE.exists():
            try:
                raw = json.loads(POLICIES_FILE.read_text(encoding="utf-8"))
                saved_policies = raw.get("policies", raw)
                if isinstance(saved_policies, dict):
                    for key, cfg in saved_policies.items():
                        if key in merged and isinstance(cfg, dict):
                            if "enabled" in cfg:
                                merged[key]["enabled"] = bool(cfg["enabled"])
                            if "threshold" in cfg:
                                val = int(cfg["threshold"])
                                lo = merged[key]["min"]
                                hi = merged[key]["max"]
                                merged[key]["threshold"] = max(lo, min(hi, val))
                saved_alerts = raw.get("alerts_log", [])
                if isinstance(saved_alerts, list):
                    self.alerts_log = saved_alerts[:30]
            except Exception:
                pass

        self.policies = merged
        self._save_state()

    def _save_state(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "policies": {
                    k: {
                        "enabled": v["enabled"],
                        "threshold": v["threshold"],
                    }
                    for k, v in self.policies.items()
                },
                "alerts_log": self.alerts_log[:30],
            }
            POLICIES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_state(self) -> Dict[str, Any]:
        now = time.monotonic()
        rules_list: List[Dict[str, Any]] = []
        for key in (
            "ram_pressure",
            "auto_rescue_ram",
            "cpu_thermal",
            "cpu_load",
            "swap_thrashing",
        ):
            rule = dict(self.policies[key])
            last_t = self.last_fired.get(key, 0.0)
            cooldown_rem = max(0, int(COOLDOWN_SECONDS - (now - last_t))) if last_t > 0 else 0
            rule["breach_streak"] = self.breach_counts.get(key, 0)
            rule["cooldown_remaining_sec"] = cooldown_rem
            rules_list.append(rule)

        return {
            "monitor_active": self._running,
            "check_interval_sec": int(CHECK_INTERVAL_SECONDS),
            "cooldown_sec": int(COOLDOWN_SECONDS),
            "policies": self.policies,
            "rules": rules_list,
            "alerts_log": self.alerts_log[:30],
        }

    def update_policies(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        for key, patch in updates.items():
            if key in self.policies and isinstance(patch, dict):
                rule = self.policies[key]
                if "enabled" in patch:
                    rule["enabled"] = bool(patch["enabled"])
                    if not rule["enabled"]:
                        self.breach_counts[key] = 0
                if "threshold" in patch:
                    try:
                        val = int(round(float(patch["threshold"])))
                        rule["threshold"] = max(rule["min"], min(rule["max"], val))
                    except (ValueError, TypeError):
                        pass
        self._save_state()
        return self.get_state()

    def clear_alerts(self) -> Dict[str, Any]:
        self.alerts_log = []
        self._save_state()
        return self.get_state()

    async def send_notification(
        self,
        title: str,
        body: str,
        urgency: str = "normal",
        rule_id: str = "manual_test",
        severity: str = "info",
    ) -> bool:
        """
        Send a native Ubuntu GNOME desktop notification using notify-send and record it in alerts_log.
        """
        uid = os.getuid()
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")

        cmd = [
            "notify-send",
            "-a",
            "Cockpit Guard",
            "-i",
            ICON_PATH,
            "-u",
            urgency,
            title,
            body,
        ]

        sent = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
            await asyncio.wait_for(proc.wait(), timeout=4.0)
            sent = proc.returncode == 0
        except Exception:
            res = await run_cmd(cmd, timeout=4.0)
            sent = res["success"]

        entry = {
            "id": f"{int(time.time() * 1000)}-{rule_id}",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "iso_time": datetime.now().isoformat(timespec="seconds"),
            "rule_id": rule_id,
            "title": title,
            "message": body,
            "severity": severity,
        }
        self.alerts_log.insert(0, entry)
        if len(self.alerts_log) > 30:
            self.alerts_log = self.alerts_log[:30]
        self._save_state()
        return sent

    async def trigger_test_notification(self) -> Dict[str, Any]:
        vitals = get_lite_vitals()
        top_ram = vitals["top_ram_hog"]
        title = "Cockpit Guard — Active & Monitoring"
        body = (
            f"RAM: {vitals['ram_percent']}% ({vitals['ram_used_gb']:.1f} / {vitals['ram_total_gb']:.1f} GB) • "
            f"CPU: {vitals['cpu_percent']}%. "
            f"Top consumer: {top_ram['display_name']} ({top_ram['rss_gb']:.1f} GB)"
        )
        ok = await self.send_notification(
            title=title,
            body=body,
            urgency="normal",
            rule_id="test_alert",
            severity="info",
        )
        return {
            "success": ok,
            "title": title,
            "message": body,
            "state": self.get_state(),
        }

    def _can_fire(self, rule_id: str, now: float) -> bool:
        rule = self.policies.get(rule_id)
        if not rule or not rule.get("enabled"):
            return False
        min_checks = int(rule.get("min_breach_checks", 2))
        if self.breach_counts.get(rule_id, 0) < min_checks:
            return False
        last = self.last_fired.get(rule_id, 0.0)
        if last > 0.0 and (now - last) < COOLDOWN_SECONDS:
            return False
        return True

    async def _evaluate_tick(self) -> None:
        vitals = get_lite_vitals()
        now = time.monotonic()

        ram_pct = vitals["ram_percent"]
        ram_used_gb = vitals["ram_used_gb"]
        cpu_pct = vitals["cpu_percent"]
        cpu_temp = vitals["cpu_temp_c"]
        swap_pct = vitals["swap_percent"]
        top_ram = vitals["top_ram_hog"]
        top_cpu = vitals["top_cpu_hog"]

        # 1. High RAM Pressure Alert
        r_ram = self.policies["ram_pressure"]
        if r_ram["enabled"] and ram_pct >= r_ram["threshold"]:
            self.breach_counts["ram_pressure"] += 1
            if self._can_fire("ram_pressure", now):
                self.last_fired["ram_pressure"] = now
                body = (
                    f"RAM is at {int(round(ram_pct))}% ({ram_used_gb:.1f} GB). "
                    f"Top consumer: {top_ram['display_name']} ({top_ram['rss_gb']:.1f} GB)"
                )
                await self.send_notification(
                    title="High RAM Pressure Alert",
                    body=body,
                    urgency="critical" if ram_pct >= 92 else "normal",
                    rule_id="ram_pressure",
                    severity="warning",
                )
        else:
            self.breach_counts["ram_pressure"] = 0

        # 2. Auto-Rescue on Critical RAM
        r_rescue = self.policies["auto_rescue_ram"]
        if r_rescue["enabled"] and ram_pct >= r_rescue["threshold"]:
            self.breach_counts["auto_rescue_ram"] += 1
            if self._can_fire("auto_rescue_ram", now):
                self.last_fired["auto_rescue_ram"] = now
                drop_res = await drop_memory_caches()
                if drop_res.get("success"):
                    body = (
                        f"Critical RAM ({int(round(ram_pct))}%) breached {r_rescue['threshold']}%. "
                        f"Auto-flushed kernel caches and reclaimed ~{drop_res.get('freed_mb', 0)} MB."
                    )
                else:
                    body = (
                        f"Critical RAM ({int(round(ram_pct))}%) breached {r_rescue['threshold']}%. "
                        f"Top consumer: {top_ram['display_name']} ({top_ram['rss_gb']:.1f} GB). "
                        f"Click 'Free RAM & Drop Caches' in Cockpit tray."
                    )
                await self.send_notification(
                    title="Critical RAM Auto-Rescue Triggered",
                    body=body,
                    urgency="critical",
                    rule_id="auto_rescue_ram",
                    severity="critical",
                )
        else:
            self.breach_counts["auto_rescue_ram"] = 0

        # 3. CPU Thermal Guard
        r_therm = self.policies["cpu_thermal"]
        if r_therm["enabled"] and cpu_temp is not None and cpu_temp >= r_therm["threshold"]:
            self.breach_counts["cpu_thermal"] += 1
            if self._can_fire("cpu_thermal", now):
                self.last_fired["cpu_thermal"] = now
                body = (
                    f"CPU temperature reached {int(round(cpu_temp))}°C (threshold: {r_therm['threshold']}°C). "
                    f"Top CPU consumer: {top_cpu['display_name']} ({top_cpu['cpu_percent']}%)"
                )
                await self.send_notification(
                    title="CPU Thermal Guard Alert",
                    body=body,
                    urgency="critical",
                    rule_id="cpu_thermal",
                    severity="critical",
                )
        else:
            self.breach_counts["cpu_thermal"] = 0

        # 4. Sustained High CPU Load (>20s / 4 checks)
        r_cpu = self.policies["cpu_load"]
        if r_cpu["enabled"] and cpu_pct >= r_cpu["threshold"]:
            self.breach_counts["cpu_load"] += 1
            if self._can_fire("cpu_load", now):
                self.last_fired["cpu_load"] = now
                body = (
                    f"CPU usage sustained at {int(round(cpu_pct))}% for >20s. "
                    f"Top process: {top_cpu['display_name']} ({top_cpu['cpu_percent']}%)"
                )
                await self.send_notification(
                    title="Sustained High CPU Load",
                    body=body,
                    urgency="normal",
                    rule_id="cpu_load",
                    severity="warning",
                )
        else:
            self.breach_counts["cpu_load"] = 0

        # 5. Swap Thrashing Warning
        r_swap = self.policies["swap_thrashing"]
        if r_swap["enabled"] and swap_pct >= r_swap["threshold"]:
            self.breach_counts["swap_thrashing"] += 1
            if self._can_fire("swap_thrashing", now):
                self.last_fired["swap_thrashing"] = now
                body = (
                    f"Swap usage is at {int(round(swap_pct))}% (threshold: {r_swap['threshold']}%). "
                    f"Top memory hog: {top_ram['display_name']} ({top_ram['rss_gb']:.1f} GB)"
                )
                await self.send_notification(
                    title="Swap Thrashing Warning",
                    body=body,
                    urgency="normal",
                    rule_id="swap_thrashing",
                    severity="warning",
                )
        else:
            self.breach_counts["swap_thrashing"] = 0

    async def _monitor_loop(self) -> None:
        self._running = True
        try:
            while self._running:
                try:
                    await self._evaluate_tick()
                except Exception:
                    pass
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        finally:
            self._running = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


policy_guard = PolicyGuardEngine()
