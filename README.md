# Cockpit — Ubuntu 8GB System Assistant & Developer Control Center

Cockpit is a production-ready, ultra-lightweight desktop system assistant and developer control center tailored for Ubuntu Linux laptops with an **8GB RAM constraint**.

## Architecture Highlights
- **Zero-Idle Overhead Backend:** Python 3 + FastAPI + `psutil` + direct `/proc` and `/sys` filesystem reads. Live telemetry streams over `/ws/metrics` every 1.5 seconds **only while a client UI window is connected**.
- **Native PolicyKit Integration (`pkexec`):** Privileged actions (`drop_caches`, `swapoff/swapon`, `apt-get`, `snap`, `systemctl`, `journalctl`, `resolvectl`) invoke Ubuntu's native graphical PolicyKit authentication prompt safely.
- **Standalone Native App Window (`StartupWMClass=Cockpit`):** Compiled Vue 3 + Vite + TailwindCSS + Apache ECharts static assets are served directly by FastAPI on `http://127.0.0.1:8765` and launched in an isolated app profile (`~/.config/cockpit-app-profile`) with `--class=Cockpit --name=Cockpit` so GNOME displays Cockpit's custom radar-gauge icon in the dock.

## Quick Start

```bash
# Install dependencies, compile frontend, register ~/.local/bin/cockpit CLI and ~/.local/share/applications/cockpit.desktop
./install.sh

# Launch from anywhere in terminal
cockpit

# Or restart / stop the background service
cockpit --restart
cockpit --stop
```
