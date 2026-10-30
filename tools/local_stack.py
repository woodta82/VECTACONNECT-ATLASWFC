"""Local verification stack: a clean PostgreSQL database migrated with Alembic,
the FastAPI API (uvicorn), the worker process, the synthetic fixture source
site, the SIMULATED AI provider, and the frontend verification server.

    python tools/local_stack.py up   [--db atlas_stack] [--logs DIR] [--no-ai]
    python tools/local_stack.py down [--logs DIR]

Every process logs to DIR (default: ./stack-logs). Ports: API 8000, web 3000,
fixture site 8089, AI stub 8090. The web server is the verification bundle
(frontend/verify) unless STACK_WEB_CMD names another command, e.g. the
production Next server in CI. PostgreSQL connection from WFC_STACK_PG
(default "host=127.0.0.1 port=5433 user=atlas"). This is for local
verification and demonstration only; it never runs in production (the AI
stub and RETRIEVAL_ALLOW_PRIVATE_HOSTS are refused outside development/test).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PY = os.environ.get("STACK_PYTHON", sys.executable)
PG = dict(p.split("=", 1) for p in os.environ.get("WFC_STACK_PG", "host=127.0.0.1 port=5433 user=atlas").split())
PASSWORD = os.environ.get("STACK_PASSWORD", "Local-Verify-Pass-2026!")
USER = os.environ.get("STACK_USER", "ops@wfc.example")


def psql(db: str, sql: str) -> None:
    subprocess.run(["psql", "-X", "-q", "-h", PG["host"], "-p", PG["port"], "-U", PG["user"], "-d", db, "-c", sql], check=True)


def wait(url: str, timeout: float = 30) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:  # noqa: S310 - local
                if r.status < 500:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    raise SystemExit(f"timed out waiting for {url}")


def stack_env(db: str, no_ai: bool) -> dict[str, str]:
    url = f"postgresql://{PG['user']}@{PG['host']}:{PG['port']}/{db}"
    env = dict(os.environ, DATABASE_URL=url, ENVIRONMENT="development", LOGIN_USERNAME=USER, LOGIN_BOOTSTRAP_PASSWORD=PASSWORD,
               PUBLIC_ORIGIN="http://127.0.0.1:3000", BUILD_ID="local-stack", REPORTING_TIMEZONE="Asia/Dubai",
               RETRIEVAL_ALLOW_PRIVATE_HOSTS="127.0.0.1:8089", PYTHONPATH=str(BACKEND))
    if not no_ai:
        env.update(ANTHROPIC_API_KEY="local-stub-key-not-real", AI_MODEL="stub-model (simulated provider)", AI_PRICE_INPUT_PER_MTOK="3",
                   AI_PRICE_OUTPUT_PER_MTOK="15", AI_API_BASE_URL="http://127.0.0.1:8090",
                   # SIMULATED search connector: the fixture site's stand-in for the Brave Search API (a fixed index of fixture pages)
                   SEARCH_PROVIDER="brave", SEARCH_API_KEY="local-stub-search-key-not-real", SEARCH_API_BASE_URL="http://127.0.0.1:8089/search-api")
    # the automated journeys replay many users' clicks per minute from one address; deployments keep the default 300
    env["RATE_LIMIT_PER_MINUTE"] = "3000"
    return env


def spawn(name: str, cmd: list[str], env: dict[str, str], logs: Path) -> int:
    out = open(logs / f"{name}.log", "a")  # noqa: SIM115
    p = subprocess.Popen(cmd, cwd=BACKEND, env=dict(env, BACKEND="http://127.0.0.1:8000", PORT="3000"), stdout=out,
                         stderr=subprocess.STDOUT, start_new_session=True)
    return p.pid


def _busy_ports() -> list[int]:
    import socket
    busy = []
    for port in (8000, 3000, 8089, 8090):
        with socket.socket() as sk:
            sk.settimeout(0.3)
            if sk.connect_ex(("127.0.0.1", port)) == 0:
                busy.append(port)
    return busy


def up(args: argparse.Namespace) -> None:
    busy = _busy_ports()
    if busy:   # a stack left running would silently serve this run with old code and another database
        raise SystemExit(f"ports already in use: {busy} — stop the running stack first (tools/local_stack.py down)")
    logs = Path(args.logs).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    db = args.db
    psql("postgres", f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
    psql("postgres", f"CREATE DATABASE {db}")
    env = stack_env(db, args.no_ai)
    mig = subprocess.run([PY, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    (logs / "alembic.log").write_text(mig.stdout + mig.stderr)
    if mig.returncode:
        raise SystemExit(f"alembic failed: {mig.stderr[-2000:]}")
    procs = {
        "api": [PY, "-m", "uvicorn", "--factory", "app.main:app_factory", "--host", "127.0.0.1", "--port", "8000"],
        "worker": [PY, "-m", "app.worker_main"],
        "fixture_site": [PY, str(ROOT / "tools" / "fixture_site.py"), "--port", "8089"],
        # STACK_WEB_CMD serves the production Next build instead (CI: "cd ../frontend && npx next start -p 3000").
        "web": ["sh", "-c", os.environ["STACK_WEB_CMD"]] if os.environ.get("STACK_WEB_CMD")
               else ["node", str(ROOT / "frontend" / "verify" / "server.mjs")],
    }
    if not args.no_ai:
        procs["ai_stub"] = [PY, str(ROOT / "tools" / "fake_ai_provider.py"), "--port", "8090"]
    pids = {}
    for name, cmd in procs.items():
        (logs / f"{name}.log").write_text("")
        pids[name] = spawn(name, cmd, env, logs)
    (logs / "pids.json").write_text(json.dumps(pids))
    wait("http://127.0.0.1:8000/health/live")
    wait("http://127.0.0.1:3000/")
    wait("http://127.0.0.1:8089/tradewire/")
    print(json.dumps({"web": "http://127.0.0.1:3000", "api": "http://127.0.0.1:8000", "fixture_site": "http://127.0.0.1:8089",
                      "ai": "simulated stub on :8090" if not args.no_ai else "not connected", "username": USER, "logs": str(logs),
                      "database": db}, indent=2))


def restart(args: argparse.Namespace) -> None:
    """Stop one service (SIGTERM, like a container restart) and start it again with the same configuration.
    Used by the browser journeys to show that a queued job survives a worker restart."""
    logs = Path(args.logs).resolve()
    f = logs / "pids.json"
    pids = json.loads(f.read_text())
    name = args.service
    try:
        os.killpg(pids[name], signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            os.kill(pids[name], 0)
            time.sleep(0.2)
        except ProcessLookupError:
            break
    cmd = {"worker": [PY, "-m", "app.worker_main"],
           "api": [PY, "-m", "uvicorn", "--factory", "app.main:app_factory", "--host", "127.0.0.1", "--port", "8000"]}[name]
    pids[name] = spawn(name, cmd, stack_env(args.db, args.no_ai), logs)
    f.write_text(json.dumps(pids))
    print(f"restarted {name} (pid {pids[name]})")


def down(args: argparse.Namespace) -> None:
    f = Path(args.logs) / "pids.json"
    if not f.exists():
        return
    for name, pid in json.loads(f.read_text()).items():
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        print(f"stopped {name}")
    f.unlink()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["up", "down", "restart"])
    ap.add_argument("--service", default="worker", choices=["worker", "api"])
    ap.add_argument("--db", default="atlas_stack")
    ap.add_argument("--logs", default="stack-logs")
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args()
    {"up": up, "down": down, "restart": restart}[a.cmd](a)
