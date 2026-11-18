import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from services.executor import run_cmd

router = APIRouter(prefix="/api/packages", tags=["packages"])


class UninstallRequest(BaseModel):
    manager: str  # "apt" | "snap" | "npm" | "pip" | "pipx" | "manual"
    name: str
    revision: Optional[str] = None
    path: Optional[str] = None
    purge_orphans: bool = False
    orphan_paths: Optional[List[str]] = None


class OrphanDeleteRequest(BaseModel):
    paths: List[str]


def _get_dir_size(path: Path) -> int:
    total = 0
    try:
        if path.is_file() or path.is_symlink():
            return path.lstat().st_size
        for root, _, files in os.walk(path, followlinks=False):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    total += os.lstat(fp).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


async def list_apt_manual() -> List[Dict[str, Any]]:
    """
    List explicitly installed APT packages (`apt-mark showmanual`) enriched with
    version, size, and summary from `/var/lib/dpkg/status` without spawning per-package shells.
    """
    res = await run_cmd(["apt-mark", "showmanual"], timeout=15.0)
    if not res["success"]:
        return []
    manual_set = set(line.strip() for line in res["stdout"].splitlines() if line.strip())

    packages: List[Dict[str, Any]] = []
    status_path = Path("/var/lib/dpkg/status")
    if status_path.exists():
        try:
            content = status_path.read_text(encoding="utf-8", errors="replace")
            for block in content.split("\n\n"):
                pkg_name = ""
                version = ""
                size_kb = 0
                desc = ""
                section = ""
                installed = False
                for line in block.splitlines():
                    if line.startswith("Package: "):
                        pkg_name = line[9:].strip()
                    elif line.startswith("Status: "):
                        installed = "install ok installed" in line
                    elif line.startswith("Version: "):
                        version = line[9:].strip()
                    elif line.startswith("Installed-Size: "):
                        try:
                            size_kb = int(line[16:].strip())
                        except ValueError:
                            size_kb = 0
                    elif line.startswith("Section: "):
                        section = line[9:].strip()
                    elif line.startswith("Description: "):
                        desc = line[13:].strip()
                if installed and pkg_name in manual_set:
                    packages.append({
                        "name": pkg_name,
                        "version": version,
                        "size_bytes": size_kb * 1024,
                        "section": section,
                        "description": desc,
                        "manager": "apt",
                    })
        except Exception:
            pass

    packages.sort(key=lambda x: x["size_bytes"], reverse=True)
    return packages


async def list_snaps() -> List[Dict[str, Any]]:
    """
    List all installed Snap revisions (`snap list --all`), flagging disabled old revisions.
    """
    if not shutil.which("snap"):
        return []
    res = await run_cmd(["snap", "list", "--all"], timeout=15.0)
    if not res["success"]:
        return []

    snaps: List[Dict[str, Any]] = []
    lines = res["stdout"].splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 5:
            name = parts[0]
            version = parts[1]
            rev = parts[2]
            tracking = parts[3]
            publisher = parts[4]
            notes = parts[5] if len(parts) >= 6 else ""
            disabled = "disabled" in notes.lower()

            # Check snap file size in /var/lib/snapd/snaps/<name>_<rev>.snap
            snap_file = Path(f"/var/lib/snapd/snaps/{name}_{rev}.snap")
            size_bytes = 0
            try:
                if snap_file.exists():
                    size_bytes = snap_file.stat().st_size
            except OSError:
                pass

            snaps.append({
                "name": name,
                "version": version,
                "revision": rev,
                "tracking": tracking,
                "publisher": publisher,
                "notes": notes,
                "disabled": disabled,
                "size_bytes": size_bytes,
                "manager": "snap",
            })
    return snaps


async def list_npm_global() -> List[Dict[str, Any]]:
    """List global NPM packages (`npm list -g --depth=0 --json`)."""
    if not shutil.which("npm"):
        return []
    res = await run_cmd(["npm", "list", "-g", "--depth=0", "--json"], timeout=15.0)
    if not res["stdout"]:
        return []
    try:
        data = json.loads(res["stdout"])
        deps = data.get("dependencies", {})
        items: List[Dict[str, Any]] = []
        for name, meta in deps.items():
            items.append({
                "name": name,
                "version": meta.get("version", "unknown"),
                "description": f"Global NPM package ({name})",
                "manager": "npm",
            })
        return items
    except Exception:
        return []


async def list_pip_packages() -> List[Dict[str, Any]]:
    """List user/global Python packages and pipx tools."""
    items: List[Dict[str, Any]] = []
    seen = set()

    # Check pipx first if installed
    if shutil.which("pipx"):
        res = await run_cmd(["pipx", "list", "--json"], timeout=10.0)
        if res["success"] and res["stdout"]:
            try:
                pdata = json.loads(res["stdout"])
                venvs = pdata.get("venvs", {})
                for pkg_name, vinfo in venvs.items():
                    meta = vinfo.get("metadata", {}).get("main_package", {})
                    ver = meta.get("package_version", "unknown")
                    apps = meta.get("apps", [])
                    items.append({
                        "name": pkg_name,
                        "version": ver,
                        "source": "pipx",
                        "binaries": apps,
                        "description": f"Pipx isolated tool ({', '.join(apps)})" if apps else "Pipx package",
                        "manager": "pipx",
                    })
                    seen.add(pkg_name.lower())
            except Exception:
                pass

    # User-installed pip packages (`pip3 list --user --format=json` or global non-distro)
    pip_bin = shutil.which("pip3") or shutil.which("pip")
    if pip_bin:
        res_user = await run_cmd([pip_bin, "list", "--user", "--format=json"], timeout=15.0)
        if res_user["success"] and res_user["stdout"]:
            try:
                ulist = json.loads(res_user["stdout"])
                for pkg in ulist:
                    pname = pkg.get("name", "")
                    if pname and pname.lower() not in seen:
                        items.append({
                            "name": pname,
                            "version": pkg.get("version", ""),
                            "source": "pip --user",
                            "description": "User site-packages Python library",
                            "manager": "pip",
                        })
                        seen.add(pname.lower())
            except Exception:
                pass

    return items


def list_manual_and_appimages() -> List[Dict[str, Any]]:
    """
    Scan `~/Applications`, `/opt`, and `~/.local/bin` for `.AppImage` files,
    standalone binaries, and manual installations.
    """
    home = Path.home()
    items: List[Dict[str, Any]] = []

    # 1. Scan ~/Applications for .AppImage and executables
    app_dirs = [home / "Applications", home / "Downloads", home / ".local" / "bin"]
    seen_paths = set()

    for d in app_dirs:
        if not d.exists():
            continue
        try:
            for entry in sorted(d.iterdir()):
                if str(entry) in seen_paths:
                    continue
                is_appimage = entry.name.lower().endswith(".appimage")
                is_local_bin = d == (home / ".local" / "bin")
                if not is_appimage and not is_local_bin:
                    continue
                if entry.is_file() or entry.is_symlink():
                    try:
                        st = entry.stat()
                    except OSError:
                        continue
                    kind = "AppImage" if is_appimage else "Local Binary (~/.local/bin)"
                    items.append({
                        "name": entry.name,
                        "version": kind,
                        "path": str(entry),
                        "size_bytes": st.st_size,
                        "modified": int(st.st_mtime),
                        "executable": os.access(entry, os.X_OK),
                        "manager": "manual",
                    })
                    seen_paths.add(str(entry))
        except OSError:
            pass

    # 2. Scan /opt top-level directories
    opt_dir = Path("/opt")
    if opt_dir.exists():
        try:
            for entry in sorted(opt_dir.iterdir()):
                if entry.is_dir():
                    try:
                        st = entry.stat()
                        size_b = _get_dir_size(entry)
                    except OSError:
                        size_b = 0
                        st = None
                    items.append({
                        "name": entry.name,
                        "version": "/opt Directory",
                        "path": str(entry),
                        "size_bytes": size_b,
                        "modified": int(st.st_mtime) if st else 0,
                        "executable": True,
                        "manager": "manual",
                    })
        except OSError:
            pass

    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    return items


@router.get("/list")
async def get_all_packages(tab: Optional[str] = None):
    """Fetch installed packages for a specific tab or all tabs."""
    if tab == "apt":
        return {"apt": await list_apt_manual()}
    if tab == "snap":
        return {"snap": await list_snaps()}
    if tab == "npm":
        return {"npm": await list_npm_global()}
    if tab == "pip":
        return {"pip": await list_pip_packages()}
    if tab == "manual":
        return {"manual": list_manual_and_appimages()}

    return {
        "apt": await list_apt_manual(),
        "snap": await list_snaps(),
        "npm": await list_npm_global(),
        "pip": await list_pip_packages(),
        "manual": list_manual_and_appimages(),
    }


@router.get("/orphans")
async def scan_orphan_configs(app_name: str):
    """
    Scan `~/.config`, `~/.cache`, and `~/.local/share` for leftover folders matching app_name.
    """
    clean_token = app_name.lower().strip()
    for suffix in (".appimage", "-desktop", "-bin", "-client"):
        if clean_token.endswith(suffix):
            clean_token = clean_token[: -len(suffix)]
    clean_token = clean_token.strip("._- ")

    if len(clean_token) < 2:
        return {"orphans": []}

    home = Path.home()
    search_roots = [
        home / ".config",
        home / ".cache",
        home / ".local" / "share",
    ]

    matches: List[Dict[str, Any]] = []
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for entry in root.iterdir():
                ename = entry.name.lower()
                if clean_token in ename:
                    size_b = _get_dir_size(entry)
                    matches.append({
                        "name": entry.name,
                        "path": str(entry),
                        "location": root.name,
                        "size_bytes": size_b,
                    })
        except OSError:
            pass

    return {"app_name": app_name, "orphans": matches}


def _safe_delete_user_paths(paths: List[str]) -> Dict[str, Any]:
    """Safely delete user config/cache folders after verifying they reside inside ~/.config, ~/.cache, or ~/.local/share."""
    home = Path.home().resolve()
    allowed_parents = [
        (home / ".config").resolve(),
        (home / ".cache").resolve(),
        (home / ".local" / "share").resolve(),
        (home / "Applications").resolve(),
        (home / ".local" / "bin").resolve(),
    ]
    deleted: List[str] = []
    errors: List[str] = []
    freed_bytes = 0

    for raw in paths:
        try:
            target = Path(raw).resolve()
            if not any(
                str(target).startswith(str(parent) + os.sep) for parent in allowed_parents
            ):
                errors.append(f"Refused path outside user app directories: {raw}")
                continue
            if not target.exists() and not target.is_symlink():
                continue
            freed_bytes += _get_dir_size(target)
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            deleted.append(raw)
        except Exception as exc:
            errors.append(f"{raw}: {exc}")

    return {"deleted": deleted, "errors": errors, "freed_bytes": freed_bytes}


@router.post("/uninstall")
async def uninstall_package(req: UninstallRequest):
    """Uninstall a package across APT, Snap, NPM, Pip, Pipx, or Manual/AppImage and optionally purge orphan folders."""
    mgr = req.manager.lower()
    res: Dict[str, Any] = {"success": False, "stdout": "", "stderr": ""}

    if mgr == "apt":
        res = await run_cmd(
            ["apt-get", "remove", "--purge", "-y", req.name],
            timeout=180.0,
            use_pkexec=True,
        )
    elif mgr == "snap":
        cmd = ["snap", "remove", req.name]
        if req.revision:
            cmd.extend(["--revision", req.revision])
        res = await run_cmd(cmd, timeout=180.0, use_pkexec=True)
    elif mgr == "npm":
        res = await run_cmd(["npm", "uninstall", "-g", req.name], timeout=90.0)
        if not res["success"] and "EACCES" in res["stderr"]:
            res = await run_cmd(
                ["npm", "uninstall", "-g", req.name], timeout=90.0, use_pkexec=True
            )
    elif mgr == "pipx":
        res = await run_cmd(["pipx", "uninstall", req.name], timeout=60.0)
    elif mgr == "pip":
        pip_bin = shutil.which("pip3") or shutil.which("pip") or "pip3"
        res = await run_cmd([pip_bin, "uninstall", "-y", req.name], timeout=60.0)
    elif mgr == "manual":
        target_path = req.path or ""
        if not target_path:
            return {"success": False, "message": "Missing file path for manual package."}
        if target_path.startswith("/opt/"):
            res = await run_cmd(["rm", "-rf", target_path], timeout=30.0, use_pkexec=True)
        else:
            del_info = _safe_delete_user_paths([target_path])
            res = {
                "success": len(del_info["errors"]) == 0,
                "stdout": f"Removed {', '.join(del_info['deleted'])}",
                "stderr": "; ".join(del_info["errors"]),
            }
    else:
        return {"success": False, "message": f"Unsupported package manager: {mgr}"}

    orphan_result = {"deleted": [], "errors": [], "freed_bytes": 0}
    if req.purge_orphans and req.orphan_paths:
        orphan_result = _safe_delete_user_paths(req.orphan_paths)

    msg = (
        f"Successfully uninstalled {req.name}."
        if res["success"]
        else f"Failed to uninstall {req.name}: {res['stderr']}"
    )
    if orphan_result["deleted"]:
        msg += f" Purged {len(orphan_result['deleted'])} leftover config/cache folder(s)."

    return {
        "success": res["success"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "orphans_purged": orphan_result,
        "message": msg,
    }


@router.post("/orphans/delete")
async def delete_orphan_folders(req: OrphanDeleteRequest):
    """Delete selected leftover config/cache directories."""
    info = _safe_delete_user_paths(req.paths)
    freed_mb = round(info["freed_bytes"] / (1024 * 1024), 2)
    return {
        "success": len(info["errors"]) == 0,
        "deleted": info["deleted"],
        "errors": info["errors"],
        "freed_bytes": info["freed_bytes"],
        "message": f"Deleted {len(info['deleted'])} folder(s), freeing {freed_mb} MB.",
    }
