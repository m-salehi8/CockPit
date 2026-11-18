import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services.executor import run_shell_cmd

router = APIRouter(prefix="/api/commands", tags=["commands"])

COMMANDS_FILE = Path(__file__).resolve().parent.parent / "data" / "commands.json"


class CommandCard(BaseModel):
    id: Optional[str] = None
    title: str
    category: str = "Custom"
    description: str = ""
    command: str
    requires_root: bool = False
    icon: str = "terminal"


class ExecuteCommandRequest(BaseModel):
    id: Optional[str] = None
    command: str
    requires_root: bool = False
    timeout: float = 120.0


def _load_commands() -> List[Dict[str, Any]]:
    if not COMMANDS_FILE.exists():
        return []
    try:
        return json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_commands(items: List[Dict[str, Any]]) -> None:
    COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMMANDS_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@router.get("")
async def list_commands():
    """Return all saved command deck cards from commands.json."""
    return {"commands": _load_commands()}


@router.post("/save")
async def save_command(card: CommandCard):
    """Add or update a command card in commands.json."""
    items = _load_commands()
    card_data = card.model_dump()
    if not card_data.get("id"):
        card_data["id"] = f"cmd-{uuid.uuid4().hex[:8]}"

    updated = False
    for idx, existing in enumerate(items):
        if existing.get("id") == card_data["id"]:
            items[idx] = card_data
            updated = True
            break
    if not updated:
        items.append(card_data)

    _save_commands(items)
    return {
        "success": True,
        "command": card_data,
        "commands": items,
        "message": f"Saved command card '{card_data['title']}'.",
    }


@router.delete("/{cmd_id}")
async def delete_command(cmd_id: str):
    """Remove a command card by ID from commands.json."""
    items = _load_commands()
    filtered = [c for c in items if c.get("id") != cmd_id]
    _save_commands(filtered)
    return {
        "success": True,
        "commands": filtered,
        "message": "Command card deleted.",
    }


@router.post("/execute")
async def execute_command(req: ExecuteCommandRequest):
    """Execute a command and return stdout, stderr, returncode, and duration."""
    started = time.monotonic()
    res = await run_shell_cmd(
        req.command,
        timeout=req.timeout,
        use_pkexec=req.requires_root,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    res["duration_ms"] = elapsed_ms
    return res


@router.post("/stream")
async def stream_command(req: ExecuteCommandRequest):
    """
    Stream live stdout/stderr line-by-line as NDJSON chunks so the slide-over
    terminal drawer renders output in real time.
    """
    final_cmd = (
        ["pkexec", "/bin/bash", "-c", req.command]
        if req.requires_root
        else ["/bin/bash", "-c", req.command]
    )

    async def event_generator():
        started = time.monotonic()
        yield json.dumps({
            "type": "start",
            "command": req.command,
            "requires_root": req.requires_root,
            "timestamp": time.time(),
        }) + "\n"

        try:
            proc = await asyncio.create_subprocess_exec(
                *final_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            queue: asyncio.Queue = asyncio.Queue()

            async def _pump(stream, stream_name: str):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    await queue.put((stream_name, line.decode("utf-8", errors="replace")))
                await queue.put((stream_name, None))

            t_out = asyncio.create_task(_pump(proc.stdout, "stdout"))
            t_err = asyncio.create_task(_pump(proc.stderr, "stderr"))

            closed_streams = 0
            while closed_streams < 2:
                stream_name, text = await queue.get()
                if text is None:
                    closed_streams += 1
                else:
                    yield json.dumps({"type": stream_name, "data": text}) + "\n"

            await asyncio.gather(t_out, t_err, return_exceptions=True)
            rc = await proc.wait()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            yield json.dumps({
                "type": "exit",
                "returncode": rc,
                "success": rc == 0,
                "duration_ms": elapsed_ms,
            }) + "\n"
        except Exception as exc:
            yield json.dumps({
                "type": "error",
                "data": str(exc),
                "returncode": 1,
                "success": False,
            }) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
