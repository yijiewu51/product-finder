import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
import threading
import asyncio
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Lazy imports — ML pipeline deps (sentence-transformers etc.) may not be installed
# on lightweight deployments. Only imported when the endpoint is actually called.
try:
    from pipeline import run as run_pipeline, _slug, DATA_DIR
    from pipeline_discovery import run as run_discovery, RESULTS_FILE
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    import os
    from pathlib import Path
    DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data")))
    RESULTS_FILE = DATA_DIR / "discovery" / "opportunities.json"
    run_pipeline = None
    run_discovery = None
    _slug = None

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict[str, dict] = {}


class AnalyzeRequest(BaseModel):
    query: str
    n_reviews: int = 200
    use_cache: bool = True


class DiscoverRequest(BaseModel):
    use_cache: bool = True


def _run_in_thread(job_id: str, target, **kwargs):
    progress_events = jobs[job_id]["progress"]

    def on_progress(phase: int, message: str):
        progress_events.append({"phase": phase, "message": message})

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(target(
            progress_callback=on_progress,
            verbose=False,
            **kwargs,
        ))
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["result"] = result
    except Exception as e:
        import traceback
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e) + "\n" + traceback.format_exc()
    finally:
        loop.close()


# ── Analyze a specific product ────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    if not _ML_AVAILABLE:
        return {"error": "ML pipeline not available on this deployment"}, 503

    cached = DATA_DIR / _slug(request.query) / "analysis.json"
    if request.use_cache and cached.exists():
        result = json.loads(cached.read_text())
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "complete",
            "progress": [{"phase": 0, "message": "Loaded from cache"}],
            "result": result,
            "error": None,
        }
        return {"job_id": job_id, "cached": True}

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "progress": [], "result": None, "error": None}
    thread = threading.Thread(
        target=_run_in_thread,
        args=(job_id, run_pipeline),
        kwargs={"query": request.query, "n_reviews": request.n_reviews, "use_cache": request.use_cache},
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "cached": False}


# ── Discover opportunities from real data ─────────────────────────────────────

@app.post("/api/discover")
async def discover(request: DiscoverRequest):
    if not _ML_AVAILABLE and not RESULTS_FILE.exists():
        return {"error": "ML pipeline not available on this deployment"}, 503

    if request.use_cache and RESULTS_FILE.exists():
        result = json.loads(RESULTS_FILE.read_text())
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "complete",
            "progress": [{"phase": 0, "message": "Loaded from cache"}],
            "result": result,
            "error": None,
        }
        return {"job_id": job_id, "cached": True}

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "progress": [], "result": None, "error": None}
    thread = threading.Thread(
        target=_run_in_thread,
        args=(job_id, run_discovery),
        kwargs={"use_cache": request.use_cache},
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "cached": False}


# ── Status + health ───────────────────────────────────────────────────────────

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        return {"status": "not_found"}
    return jobs[job_id]


@app.get("/api/results")
async def get_results():
    """Return cached discovery results instantly (no job needed)."""
    if RESULTS_FILE.exists():
        data = json.loads(RESULTS_FILE.read_text())
        mtime = int(RESULTS_FILE.stat().st_mtime)
        return {"found": True, "results": data, "updated_at": mtime}
    return {"found": False, "results": [], "updated_at": None}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
