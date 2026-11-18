import asyncio
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import psutil
from fastapi import APIRouter
from pydantic import BaseModel
from services.executor import run_cmd

router = APIRouter(prefix="/api/storage", tags=["storage"])

DEV_JUNK_TARGETS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    "target",
}

SKIP_SYSTEM_DIRS = {
    ".git",
    ".cache",
    ".local",
    ".config",
    ".npm",
    ".cargo",
    ".rustup",
    "snap",
    "proc",
    "sys",
    "dev",
}


class ScanRequest(BaseModel):
    root_path: str = "~/projects"
    max_depth: int = 6


class BulkDeleteRequest(BaseModel):
    paths: List[str]


class CacheCleanRequest(BaseModel):
    target: str  # "apt" | "snap_old" | "journal" | "pip" | "npm" | "docker"


def _calc_dir_size_fast(path: str) -> int:
    total = 0
    stack = [path]
    while stack:
        curr = stack.pop()
        try:
            with os.scandir(curr) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def _scan_dev_junk_sync(root_path: str, max_depth: int = 6) -> Dict[str, Any]:
    expanded = os.path.expanduser(root_path)
    if not os.path.exists(expanded):
        # Fallback to home directory if ~/projects doesn't exist
        expanded = str(Path.home())

    root_resolved = os.path.realpath(expanded)
    # Protect our own active runtime virtual environment if any
    own_backend_venv = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "..", ".venv")
    )

    found: List[Dict[str, Any]] = []
    total_bytes = 0

    def _walk(curr_dir: str, depth: int) -> None:
        nonlocal total_bytes
        if depth > max_depth:
            return
        try:
            with os.scandir(curr_dir) as it:
                for entry in it:
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        continue
                    name = entry.name
                    full_path = entry.path

                    if name in DEV_JUNK_TARGETS:
                        # For 'target', only flag if Cargo.toml exists in parent (Rust build artifact)
                        if name == "target" and not os.path.exists(
                            os.path.join(curr_dir, "Cargo.toml")
                        ):
                            continue
                        if os.path.realpath(full_path) == own_backend_venv:
                            continue

                        size_b = _calc_dir_size_fast(full_path)
                        if size_b < 64 * 1024:
                            # Ignore tiny <64KB folders to keep list actionable
                            continue
                        try:
                            mtime = int(entry.stat(follow_symlinks=False).st_mtime)
                        except OSError:
                            mtime = 0

                        project_name = os.path.basename(curr_dir)
                        found.append({
                            "path": full_path,
                            "type": name,
                            "project": project_name,
                            "size_bytes": size_b,
                            "modified": mtime,
                        })
                        total_bytes += size_b
                        # Do not descend inside a matched node_modules or .venv
                        continue

                    if name in SKIP_SYSTEM_DIRS or (name.startswith(".") and name not in DEV_JUNK_TARGETS):
                        continue

                    _walk(full_path, depth + 1)
        except OSError:
            pass

    _walk(root_resolved, 0)
    found.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "scanned_root": root_resolved,
        "total_size_bytes": total_bytes,
        "item_count": len(found),
        "items": found[:150],
    }


def get_disk_partitions_overview() -> Dict[str, Any]:
    """Return usage breakdown of main disk partitions and key user directories."""
    root_usage = psutil.disk_usage("/")
    home_path = str(Path.home())
    home_usage = psutil.disk_usage(home_path)

    partitions: List[Dict[str, Any]] = []
    seen_devs = set()
    for part in psutil.disk_partitions(all=False):
        if part.device in seen_devs or "/snap/" in part.mountpoint or part.fstype == "squashfs":
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
            seen_devs.add(part.device)
            partitions.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_bytes": u.total,
                "used_bytes": u.used,
                "free_bytes": u.free,
                "percent": round(u.percent, 1),
            })
        except OSError:
            continue

    return {
        "root": {
            "total_bytes": root_usage.total,
            "used_bytes": root_usage.used,
            "free_bytes": root_usage.free,
            "percent": round(root_usage.percent, 1),
        },
        "home": {
            "path": home_path,
            "total_bytes": home_usage.total,
            "used_bytes": home_usage.used,
            "free_bytes": home_usage.free,
            "percent": round(home_usage.percent, 1),
        },
        "partitions": partitions,
    }


async def inspect_system_caches() -> Dict[str, Any]:
    """Calculate current sizes of APT cache, Old Snap revisions, Systemd journals, Pip, NPM, and Docker."""
    home = Path.home()

    # 1. APT cache (/var/cache/apt/archives)
    apt_cache_dir = "/var/cache/apt/archives"
    apt_bytes = await asyncio.to_thread(_calc_dir_size_fast, apt_cache_dir)

    # 2. Old disabled Snap revisions
    snap_old_bytes = 0
    snap_old_count = 0
    snap_old_list: List[Dict[str, str]] = []
    if shutil.which("snap"):
        res = await run_cmd(["snap", "list", "--all"], timeout=10.0)
        if res["success"]:
            for line in res["stdout"].splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 6 and "disabled" in parts[5].lower():
                    sname, srev = parts[0], parts[2]
                    snap_old_count += 1
                    snap_old_list.append({"name": sname, "revision": srev})
                    sfile = Path(f"/var/lib/snapd/snaps/{sname}_{srev}.snap")
                    try:
                        if sfile.exists():
                            snap_old_bytes += sfile.stat().st_size
                    except OSError:
                        pass

    # 3. Systemd Journal logs (/var/log/journal)
    journal_bytes = await asyncio.to_thread(_calc_dir_size_fast, "/var/log/journal")

    # 4. Pip cache (~/.cache/pip)
    pip_cache_path = str(home / ".cache" / "pip")
    pip_bytes = await asyncio.to_thread(_calc_dir_size_fast, pip_cache_path)

    # 5. NPM cache (~/.npm)
    npm_cache_path = str(home / ".npm")
    npm_bytes = await asyncio.to_thread(_calc_dir_size_fast, npm_cache_path)

    # 6. Docker system df summary
    docker_available = shutil.which("docker") is not None
    docker_summary = "Docker not installed or daemon stopped"
    docker_raw: List[Dict[str, str]] = []
    if docker_available:
        dres = await run_cmd(
            ["docker", "system", "df", "--format", "{{.Type}}|{{.TotalCount}}|{{.Size}}|{{.Reclaimable}}"],
            timeout=8.0,
        )
        if dres["success"] and dres["stdout"]:
            lines = []
            for row in dres["stdout"].splitlines():
                cols = row.split("|")
                if len(cols) == 4:
                    docker_raw.append({
                        "type": cols[0],
                        "count": cols[1],
                        "size": cols[2],
                        "reclaimable": cols[3],
                    })
                    lines.append(f"{cols[0]}: {cols[2]} ({cols[3]} reclaimable)")
            docker_summary = " • ".join(lines) if lines else "No Docker objects"

    return {
        "apt_cache": {
            "id": "apt",
            "title": "APT Package Archives",
            "path": apt_cache_dir,
            "command_preview": "pkexec sh -c 'apt-get clean && apt-get autoremove -y'",
            "size_bytes": apt_bytes,
            "requires_root": True,
        },
        "snap_old": {
            "id": "snap_old",
            "title": f"Disabled Snap Revisions ({snap_old_count})",
            "path": "/var/lib/snapd/snaps",
            "command_preview": "pkexec snap remove <pkg> --revision=<rev>",
            "size_bytes": snap_old_bytes,
            "count": snap_old_count,
            "items": snap_old_list,
            "requires_root": True,
        },
        "journal_logs": {
            "id": "journal",
            "title": "Systemd Journal Logs (>3 days)",
            "path": "/var/log/journal",
            "command_preview": "pkexec journalctl --vacuum-time=3d",
            "size_bytes": journal_bytes,
            "requires_root": True,
        },
        "pip_cache": {
            "id": "pip",
            "title": "Python Pip Wheel Cache",
            "path": pip_cache_path,
            "command_preview": "rm -rf ~/.cache/pip/*",
            "size_bytes": pip_bytes,
            "requires_root": False,
        },
        "npm_cache": {
            "id": "npm",
            "title": "Node / NPM Cache",
            "path": npm_cache_path,
            "command_preview": "npm cache clean --force",
            "size_bytes": npm_bytes,
            "requires_root": False,
        },
        "docker": {
            "id": "docker",
            "title": "Docker Dangling Images & Build Cache",
            "path": "/var/lib/docker",
            "command_preview": "docker system prune -f",
            "available": docker_available,
            "summary": docker_summary,
            "breakdown": docker_raw,
            "requires_root": False,
        },
    }


@router.get("/overview")
async def storage_overview():
    """Return disk partition breakdown and system cache sizes."""
    disks = get_disk_partitions_overview()
    caches = await inspect_system_caches()
    return {
        "disks": disks,
        "caches": caches,
    }


@router.post("/scan-dev-junk")
async def scan_dev_junk(req: ScanRequest):
    """Asynchronously scan workspace directory for heavy node_modules, .venv, venv, __pycache__, etc."""
    result = await asyncio.to_thread(_scan_dev_junk_sync, req.root_path, req.max_depth)
    return result


@router.post("/delete-dev-junk")
async def delete_dev_junk(req: BulkDeleteRequest):
    """Safely delete selected developer artifact directories."""
    own_backend_venv = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "..", ".venv")
    )
    deleted: List[str] = []
    errors: List[str] = []
    freed_bytes = 0

    for raw_path in req.paths:
        try:
            real_target = os.path.realpath(raw_path)
            base_name = os.path.basename(real_target)
            if base_name not in DEV_JUNK_TARGETS:
                errors.append(f"Refused non-artifact folder: {raw_path}")
                continue
            if real_target == own_backend_venv:
                errors.append("Skipped active Cockpit backend virtualenv.")
                continue
            if not os.path.exists(real_target):
                continue

            size_b = await asyncio.to_thread(_calc_dir_size_fast, real_target)
            await asyncio.to_thread(shutil.rmtree, real_target)
            freed_bytes += size_b
            deleted.append(raw_path)
        except Exception as exc:
            errors.append(f"{raw_path}: {exc}")

    freed_mb = round(freed_bytes / (1024 * 1024), 1)
    return {
        "success": len(errors) == 0,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "errors": errors,
        "freed_bytes": freed_bytes,
        "message": f"Deleted {len(deleted)} artifact folder(s), reclaiming {freed_mb} MB.",
    }


@router.post("/clean-cache")
async def clean_system_cache(req: CacheCleanRequest):
    """Execute system cache cleaning action for APT, Snap old revisions, Systemd journals, Pip, NPM, or Docker."""
    target = req.target.lower()
    home = Path.home()

    if target == "apt":
        res = await run_cmd(
            ["sh", "-c", "apt-get clean && apt-get autoremove -y"],
            timeout=180.0,
            use_pkexec=True,
        )
        return {
            "success": res["success"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "message": "APT package cache cleaned and unused dependencies removed."
            if res["success"]
            else f"APT clean failed: {res['stderr']}",
        }

    if target == "snap_old":
        caches = await inspect_system_caches()
        items = caches["snap_old"]["items"]
        if not items:
            return {"success": True, "message": "No disabled Snap revisions found to remove."}
        cmds = [f"snap remove {i['name']} --revision={i['revision']}" for i in items]
        res = await run_cmd(
            ["sh", "-c", " && ".join(cmds)],
            timeout=240.0,
            use_pkexec=True,
        )
        return {
            "success": res["success"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "message": f"Removed {len(items)} old Snap revision(s)."
            if res["success"]
            else f"Snap cleanup failed: {res['stderr']}",
        }

    if target == "journal":
        res = await run_cmd(
            ["journalctl", "--vacuum-time=3d"],
            timeout=60.0,
            use_pkexec=True,
        )
        return {
            "success": res["success"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "message": "Systemd journal logs vacuumed to last 3 days."
            if res["success"]
            else f"Journal vacuum failed: {res['stderr']}",
        }

    if target == "pip":
        pip_dir = home / ".cache" / "pip"
        freed = await asyncio.to_thread(_calc_dir_size_fast, str(pip_dir))
        if pip_dir.exists():
            await asyncio.to_thread(shutil.rmtree, str(pip_dir), True)
            pip_dir.mkdir(parents=True, exist_ok=True)
        freed_mb = round(freed / (1024 * 1024), 1)
        return {
            "success": True,
            "stdout": f"Removed {pip_dir}",
            "stderr": "",
            "message": f"Cleared Pip wheel cache (~{freed_mb} MB freed).",
        }

    if target == "npm":
        npm_dir = home / ".npm"
        freed = await asyncio.to_thread(_calc_dir_size_fast, str(npm_dir))
        if shutil.which("npm"):
            await run_cmd(["npm", "cache", "clean", "--force"], timeout=60.0)
        elif npm_dir.exists():
            await asyncio.to_thread(shutil.rmtree, str(npm_dir), True)
        freed_mb = round(freed / (1024 * 1024), 1)
        return {
            "success": True,
            "stdout": "npm cache clean --force completed",
            "stderr": "",
            "message": f"Cleared NPM cache (~{freed_mb} MB freed).",
        }

    if target == "docker":
        res = await run_cmd(["docker", "system", "prune", "-f"], timeout=120.0)
        if not res["success"] and "permission denied" in res["stderr"].lower():
            res = await run_cmd(
                ["docker", "system", "prune", "-f"], timeout=120.0, use_pkexec=True
            )
        return {
            "success": res["success"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "message": "Docker dangling images, containers, and build cache pruned."
            if res["success"]
            else f"Docker prune failed: {res['stderr']}",
        }

    return {"success": False, "message": f"Unknown cache target: {target}"}
