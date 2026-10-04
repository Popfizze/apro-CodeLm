from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
UPLOADS = APP_DIR / "uploads"
PLAN_FILE = "L2C_PLAN_STR_{name}.pdf"
SHOP_DIR = "DA"
LOG_TAIL_LINES = 60
PIPELINE_TIMEOUT_S = 4 * 3600
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
HOST, PORT = "127.0.0.1", 8000

app = FastAPI(title="L2C - verification des dessins d'atelier", docs_url=None, redoc_url=None)
_busy = threading.Lock()


def _tail(text: str, n: int = LOG_TAIL_LINES) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def _save(upload: UploadFile, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=PIPELINE_TIMEOUT_S,
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _error(message: str, status_code: int = 200, project: str | None = None, log: str = "") -> JSONResponse:
    content: dict = {"ok": False}
    if project is not None:
        content["projet"] = project
    content.update(error=message, log_tail=log)
    return JSONResponse(content, status_code=status_code)


def _store_uploads(name: str, plan: UploadFile, files: list[UploadFile]) -> Path:
    target = UPLOADS / name
    if target.exists():
        shutil.rmtree(target)
    _save(plan, target / PLAN_FILE.format(name=name))
    for upload in files:
        _save(upload, target / SHOP_DIR / Path(upload.filename).name)
    return target


def _analyze(name: str, target: Path) -> JSONResponse:
    log = []
    project_arg = str(target.relative_to(ROOT))
    code, out = _run(
        [sys.executable, "-m", "l2c_verif", "run", "--project", project_arg, "--out", f"results/{name}"]
    )
    log.append(f"$ python -m l2c_verif run --project app/uploads/{name} --out results/{name}\n{out}")
    if code != 0:
        return _error(f"pipeline en échec (code {code})", project=name, log=_tail("\n".join(log)))
    code, out = _run([sys.executable, str(APP_DIR / "build_data.py")])
    log.append(f"$ python app/build_data.py\n{out}")
    if code != 0:
        return _error(f"build_data en échec (code {code})", project=name, log=_tail("\n".join(log)))
    return JSONResponse({"ok": True, "projet": name, "log_tail": _tail("\n".join(log))})


def _run_locked(name: str, plan: UploadFile, files: list[UploadFile]) -> JSONResponse:
    try:
        return _analyze(name, _store_uploads(name, plan, files))
    except subprocess.TimeoutExpired:
        return _error("délai dépassé", project=name)
    except Exception as exc:
        return _error(str(exc), status_code=500, project=name)
    finally:
        _busy.release()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/analyze")
def analyze(
    project: Annotated[str, Form()],
    plan: Annotated[UploadFile, File()],
    atelier: Annotated[list[UploadFile], File()],
) -> JSONResponse:
    name = project.strip()
    if not NAME_RE.match(name):
        return _error("nom de projet invalide (lettres, chiffres, - ou _)", status_code=400)
    files = [f for f in atelier if f.filename]
    if not plan.filename or not files:
        return _error("plan et dessins d'atelier requis", status_code=400)
    if not _busy.acquire(blocking=False):
        return _error("une analyse est déjà en cours", status_code=409)
    return _run_locked(name, plan, files)


app.mount("/", StaticFiles(directory=APP_DIR, html=True), name="static")


if __name__ == "__main__":
    print(f"L2C app: http://localhost:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
