#!/usr/bin/python3
"""
Cockpit — Native Ubuntu Top Bar AppIndicator (System Tray Icon & GNOME Menu)
Ultra-lightweight GTK3 / AppIndicator3 client polling /api/vitals/lite every 4 seconds.
"""

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ValueError, ImportError):
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator

from gi.repository import GLib, Gtk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = str(PROJECT_ROOT / "cockpit.svg")
LAUNCH_SCRIPT = str(PROJECT_ROOT / "launch.sh")
API_BASE = "http://127.0.0.1:8765"
LOCK_FILE = "/tmp/cockpit-tray-indicator.lock"
PID_FILE = "/tmp/cockpit-tray-indicator.pid"
POLL_INTERVAL_MS = 4000


def send_desktop_notification(title: str, body: str, urgency: str = "normal") -> None:
    """Display a native Ubuntu desktop notification via notify-send."""
    try:
        subprocess.Popen(
            [
                "notify-send",
                "-a",
                "Cockpit Guard",
                "-i",
                ICON_PATH,
                "-u",
                urgency,
                title,
                body,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def api_request(path: str, method: str = "GET", payload: dict | None = None, timeout: float = 35.0) -> dict | None:
    """Perform a lightweight HTTP request to the local Cockpit FastAPI server."""
    url = f"{API_BASE}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception:
        return None


class CockpitTrayIndicator:
    def __init__(self) -> None:
        if hasattr(AppIndicator.Indicator, "new_with_path"):
            self.indicator = AppIndicator.Indicator.new_with_path(
                "cockpit-system-guard",
                "cockpit",
                AppIndicator.IndicatorCategory.SYSTEM_SERVICES,
                str(PROJECT_ROOT),
            )
        else:
            self.indicator = AppIndicator.Indicator.new(
                "cockpit-system-guard",
                ICON_PATH,
                AppIndicator.IndicatorCategory.SYSTEM_SERVICES,
            )
            if hasattr(self.indicator, "set_icon_theme_path"):
                self.indicator.set_icon_theme_path(str(PROJECT_ROOT))

        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Cockpit System Guard")
        if os.path.exists(ICON_PATH):
            self.indicator.set_icon_full(ICON_PATH, "Cockpit")

        self.menu = Gtk.Menu()

        # 1. Top status header item (disabled/greyed-out label like native Ubuntu indicators)
        self.item_vitals = Gtk.MenuItem(label="RAM: -- / -- GB (--%)  •  CPU: --%")
        self.item_vitals.set_sensitive(False)
        self.menu.append(self.item_vitals)

        # 2. Top RAM Consumer label (disabled/greyed-out sub-label)
        self.item_hog = Gtk.MenuItem(label="Top Hog: scanning...")
        self.item_hog.set_sensitive(False)
        self.menu.append(self.item_hog)

        # 3. Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # 4. Open Cockpit
        self.item_open = Gtk.MenuItem(label="Open Cockpit")
        self.item_open.connect("activate", self.on_open_cockpit)
        self.menu.append(self.item_open)

        # 5. Free RAM & Drop Caches
        self.item_drop_caches = Gtk.MenuItem(label="⚡ Free RAM & Drop Caches")
        self.item_drop_caches.connect("activate", self.on_drop_caches)
        self.menu.append(self.item_drop_caches)

        # 6. Toggle Dev Focus (Panic Mode)
        self.item_focus_mode = Gtk.MenuItem(label="🛡 Toggle Dev Focus (Panic Mode)")
        self.item_focus_mode.connect("activate", self.on_toggle_focus_mode)
        self.menu.append(self.item_focus_mode)

        # 7. Quick DNS Switch submenu
        self.item_dns_root = Gtk.MenuItem(label="🌐 Quick DNS Switch")
        self.dns_submenu = Gtk.Menu()

        self.item_dns_shecan = Gtk.MenuItem(label="Shecan DNS")
        self.item_dns_shecan.connect("activate", self.on_switch_dns, "Shecan")
        self.dns_submenu.append(self.item_dns_shecan)

        self.item_dns_cf = Gtk.MenuItem(label="Cloudflare (1.1.1.1)")
        self.item_dns_cf.connect("activate", self.on_switch_dns, "1.1.1.1")
        self.dns_submenu.append(self.item_dns_cf)

        self.item_dns_auto = Gtk.MenuItem(label="Automatic (DHCP)")
        self.item_dns_auto.connect("activate", self.on_switch_dns, "Auto")
        self.dns_submenu.append(self.item_dns_auto)

        self.item_dns_root.set_submenu(self.dns_submenu)
        self.menu.append(self.item_dns_root)

        # 8. Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # 9. Quit Cockpit
        self.item_quit = Gtk.MenuItem(label="Quit Cockpit")
        self.item_quit.connect("activate", self.on_quit_cockpit)
        self.menu.append(self.item_quit)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        # Initial fetch and 4-second periodic polling
        self._trigger_poll()
        GLib.timeout_add(POLL_INTERVAL_MS, self._trigger_poll)

    def _trigger_poll(self) -> bool:
        threading.Thread(target=self._poll_worker, daemon=True).start()
        return True

    def _poll_worker(self) -> None:
        data = api_request("/api/vitals/lite", method="GET", timeout=2.0)
        GLib.idle_add(self._apply_vitals, data)

    def _apply_vitals(self, data: dict | None) -> bool:
        if not data:
            self.item_vitals.set_label("Cockpit Backend: Offline")
            self.item_hog.set_label("Click 'Open Cockpit' to start")
            return False

        header_label = data.get("header_label") or "RAM: -- / -- GB  •  CPU: --%"
        hog_label = data.get("hog_label") or "Top Hog: --"
        self.item_vitals.set_label(header_label)
        self.item_hog.set_label(hog_label)

        focus_active = bool(data.get("focus_mode_active"))
        if focus_active:
            self.item_focus_mode.set_label("🛡 Toggle Dev Focus (Active • ON)")
        else:
            self.item_focus_mode.set_label("🛡 Toggle Dev Focus (Panic Mode)")

        dns_profile = data.get("dns_profile") or "Auto"
        self.item_dns_shecan.set_label(
            "• Shecan DNS (Active)" if dns_profile == "Shecan" else "Shecan DNS"
        )
        self.item_dns_cf.set_label(
            "• Cloudflare (1.1.1.1) (Active)" if dns_profile == "1.1.1.1" else "Cloudflare (1.1.1.1)"
        )
        self.item_dns_auto.set_label(
            "• Automatic (DHCP) (Active)" if dns_profile == "Auto" else "Automatic (DHCP)"
        )
        return False

    def on_open_cockpit(self, _widget: Gtk.MenuItem) -> None:
        subprocess.Popen(
            [LAUNCH_SCRIPT, "--open-only"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def on_drop_caches(self, _widget: Gtk.MenuItem) -> None:
        def worker() -> None:
            res = api_request("/api/system/drop-caches", method="POST", payload={}, timeout=40.0)
            if res and res.get("success"):
                freed_mb = res.get("freed_mb", 0)
                send_desktop_notification(
                    "RAM Freed & Caches Dropped",
                    f"Reclaimed ~{freed_mb} MB of available physical memory.",
                    urgency="normal",
                )
            elif res:
                send_desktop_notification(
                    "Free RAM Cancelled",
                    res.get("message", "Could not drop kernel caches."),
                    urgency="low",
                )
            self._poll_worker()

        threading.Thread(target=worker, daemon=True).start()

    def on_toggle_focus_mode(self, _widget: Gtk.MenuItem) -> None:
        def worker() -> None:
            res = api_request("/api/system/focus-mode", method="POST", payload={}, timeout=65.0)
            if res and res.get("success"):
                state_str = "Enabled" if res.get("focus_mode_active") else "Restored"
                send_desktop_notification(
                    f"Dev Focus Mode {state_str}",
                    res.get("message", "Background service state updated."),
                    urgency="normal",
                )
            elif res:
                send_desktop_notification(
                    "Dev Focus Mode Error",
                    res.get("message", "Operation cancelled or failed."),
                    urgency="low",
                )
            self._poll_worker()

        threading.Thread(target=worker, daemon=True).start()

    def on_switch_dns(self, _widget: Gtk.MenuItem, profile: str) -> None:
        def worker() -> None:
            res = api_request(
                "/api/system/dns/switch",
                method="POST",
                payload={"profile": profile},
                timeout=35.0,
            )
            if res and res.get("success"):
                send_desktop_notification(
                    f"DNS Switched: {res.get('dns_profile', profile)}",
                    res.get("message", f"Active DNS profile set to {profile}."),
                    urgency="normal",
                )
            elif res:
                send_desktop_notification(
                    "DNS Switch Cancelled",
                    res.get("message", "DNS change was not applied."),
                    urgency="low",
                )
            self._poll_worker()

        threading.Thread(target=worker, daemon=True).start()

    def on_quit_cockpit(self, _widget: Gtk.MenuItem) -> None:
        subprocess.Popen(
            [LAUNCH_SCRIPT, "--stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        Gtk.main_quit()


def acquire_single_instance_lock():
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)
    Path(PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
    return lock_fd


def main() -> None:
    _lock = acquire_single_instance_lock()
    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    CockpitTrayIndicator()
    Gtk.main()


if __name__ == "__main__":
    main()
