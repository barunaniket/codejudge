"""CodeJudge API server.

Run:  .venv/bin/uvicorn server:app --port 8000
Then open http://localhost:8000
"""
import asyncio
import json
import math
import re
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import ollama_client as oc
from core import storage
from core.config import MODEL_CATALOG, SAMPLES_DIR, STATIC_DIR
from core.gpu import gpu_info
from core.pipeline import run_audit
from core.report import build_pdf

app = FastAPI(title="CodeJudge", version="1.0")

# The model the user picked and loaded on the "Select Model" screen.
STATE: dict = {"model": None, "load_seconds": None}


def ndjson(gen):
    """Stream a generator of dicts as newline-delimited JSON."""
    async def body():
        async for event in gen:
            yield json.dumps(event) + "\n"
    return StreamingResponse(body(), media_type="application/x-ndjson")


class LoadRequest(BaseModel):
    model: str


class AuditRequest(BaseModel):
    code: str
    filename: str = "snippet.py"


# ------------------------------------------------------------------ status
@app.get("/api/status")
async def status():
    up = await oc.is_up()
    loaded = None
    if up and STATE["model"]:
        for m in await oc.running():
            if m["name"] == STATE["model"]:
                loaded = {"vram_mb": round(m.get("size_vram", 0) / 2**20),
                          "gpu_pct": round(100 * m.get("size_vram", 0) / max(m.get("size", 1), 1))}
        if loaded is None:          # Ollama unloaded it (idle timeout) -> force reselect
            STATE["model"] = None
    return {"ollama": up, "model": STATE["model"], "loaded": loaded,
            "load_seconds": STATE["load_seconds"], "gpu": await asyncio.to_thread(gpu_info)}


# ------------------------------------------------------------------ models
@app.get("/api/models")
async def models():
    installed = await oc.list_installed() if await oc.is_up() else []
    names = {m["name"] for m in MODEL_CATALOG}
    catalog = [dict(m, installed=m["name"] in installed) for m in MODEL_CATALOG]
    # also show any other models the user already has
    catalog += [{"name": n, "label": n, "size_gb": None, "tag": "Installed",
                 "desc": "Already downloaded on this machine.", "installed": True}
                for n in installed if n not in names and "embed" not in n]
    return {"models": catalog, "active": STATE["model"]}


@app.post("/api/models/load")
async def load_model(req: LoadRequest):
    async def gen():
        t0 = time.time()
        model = req.model
        try:
            if not await oc.is_up():
                raise RuntimeError("Ollama is not running. Start it with: ollama serve")
            yield {"stage": "connect", "pct": 3, "message": "Connected to Ollama"}

            base = 8
            if model not in await oc.list_installed():
                async for p in oc.pull_stream(model):
                    pct = 0
                    if p.get("total"):
                        pct = p.get("completed", 0) / p["total"]
                    done_mb, total_mb = p.get("completed", 0) / 2**20, p.get("total", 0) / 2**20
                    msg = f"Downloading model · {done_mb:,.0f} / {total_mb:,.0f} MB" if total_mb else p.get("status", "")
                    yield {"stage": "download", "pct": round(5 + 55 * pct, 1), "message": msg}
                base = 60

            # free the GPU: only one model at a time on a 6 GB card
            for m in await oc.running():
                if m["name"] != model:
                    yield {"stage": "free", "pct": base, "message": f"Freeing VRAM · unloading {m['name']}"}
                    await oc.unload(m["name"])
            STATE["model"] = None

            task = asyncio.create_task(oc.load(model))
            tl = time.time()
            while not task.done():
                el = time.time() - tl
                pct = base + (90 - base) * (1 - math.exp(-el / 6))
                yield {"stage": "loading", "pct": round(pct, 1),
                       "message": f"Loading weights into GPU memory · {el:.1f}s"}
                await asyncio.sleep(0.4)
            task.result()

            yield {"stage": "warmup", "pct": 94, "message": "Warm-up inference"}
            await oc.chat_json(model, "Reply in JSON.", "Say ok.",
                               {"type": "object", "properties": {"ok": {"type": "string"}}})

            info = next((m for m in await oc.running() if m["name"] == model), {})
            vram = round(info.get("size_vram", 0) / 2**20)
            gpu_pct = round(100 * info.get("size_vram", 0) / max(info.get("size", 1), 1))
            STATE.update(model=model, load_seconds=round(time.time() - t0, 1))
            yield {"stage": "ready", "pct": 100, "message": "Model ready",
                   "vram_mb": vram, "gpu_pct": gpu_pct, "seconds": STATE["load_seconds"]}
        except Exception as e:  # report any failure to the UI instead of a broken stream
            yield {"stage": "error", "pct": 0, "message": str(e)}
    return ndjson(gen())


@app.post("/api/models/unload")
async def unload_model():
    if STATE["model"]:
        await oc.unload(STATE["model"])
    STATE.update(model=None, load_seconds=None)
    return {"ok": True}


# ------------------------------------------------------------------ audit
@app.get("/api/samples")
async def samples():
    return [{"name": re.sub(r"^\d+_", "", p.stem).replace("_", " ").title(), "filename": p.name, "code": p.read_text()}
            for p in sorted(SAMPLES_DIR.glob("*.py"))]


@app.post("/api/audit")
async def audit(req: AuditRequest):
    if not STATE["model"]:
        raise HTTPException(409, "No model loaded. Select and load a model first.")
    if not req.code.strip():
        raise HTTPException(400, "No code provided.")

    async def gen():
        try:
            async for event in run_audit(req.code, req.filename, STATE["model"]):
                yield event
        except Exception as e:
            yield {"type": "error", "message": str(e)}
    return ndjson(gen())


# ------------------------------------------------------------------ history
@app.get("/api/history")
async def history():
    return await asyncio.to_thread(storage.list_audits)


@app.get("/api/history/{audit_id}")
async def history_item(audit_id: int):
    a = await asyncio.to_thread(storage.get_audit, audit_id)
    if not a:
        raise HTTPException(404, "Audit not found")
    return a


@app.delete("/api/history/{audit_id}")
async def history_delete(audit_id: int):
    await asyncio.to_thread(storage.delete_audit, audit_id)
    return {"ok": True}


@app.get("/api/history/{audit_id}/report.pdf")
async def history_pdf(audit_id: int):
    a = await asyncio.to_thread(storage.get_audit, audit_id)
    if not a:
        raise HTTPException(404, "Audit not found")
    pdf = await asyncio.to_thread(build_pdf, a)
    name = a["filename"].rsplit(".", 1)[0]
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="codejudge-{name}-{audit_id}.pdf"'})


# Frontend (must be mounted last so /api routes win)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
