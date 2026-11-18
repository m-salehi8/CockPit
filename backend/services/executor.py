import asyncio
import shlex
from typing import Dict, Any, List, Optional


async def run_cmd(
    cmd: List[str],
    timeout: float = 60.0,
    use_pkexec: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Safely execute a system command asynchronously and return structured output.
    If use_pkexec is True, prefixes the command with 'pkexec' to trigger the
    Ubuntu PolicyKit graphical authentication dialog.
    """
    final_cmd = ["pkexec"] + cmd if use_pkexec else cmd
    try:
        proc = await asyncio.create_subprocess_exec(
            *final_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds.",
                "command": " ".join(shlex.quote(c) for c in final_cmd),
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "command": " ".join(shlex.quote(c) for c in final_cmd),
        }
    except FileNotFoundError:
        return {
            "success": False,
            "returncode": 127,
            "stdout": "",
            "stderr": f"Executable not found: {final_cmd[0]}",
            "command": " ".join(shlex.quote(c) for c in final_cmd),
        }
    except Exception as exc:
        return {
            "success": False,
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "command": " ".join(shlex.quote(c) for c in final_cmd),
        }


async def run_shell_cmd(
    shell_script: str,
    timeout: float = 120.0,
    use_pkexec: bool = False,
) -> Dict[str, Any]:
    """
    Execute a shell command string via /bin/bash -c (optionally through pkexec).
    """
    cmd = ["/bin/bash", "-c", shell_script]
    return await run_cmd(cmd, timeout=timeout, use_pkexec=use_pkexec)
