"""SUBSTITUTE base images for verification environments that cannot pull from
Docker Hub (registries blocked). NOT for production.

The real images are built from backend/Dockerfile (python:3.12-slim + the
hash-locked requirements) and frontend/Dockerfile (node + `next build`). When
those base images cannot be pulled, this script assembles three minimal root
filesystems from the HOST's own binaries and imports them with
`docker import`, so the container build, startup, health checks, networking
and logs can still be exercised:

  atlas-substitute/python-runtime   host CPython + the packages the app imports
  atlas-substitute/postgres16       host PostgreSQL 16 server binaries
  atlas-substitute/node             host Node.js (serves the verification bundle)

Every ELF file's shared-library closure (ldd) is copied with it.

    python tools/docker_substitute/build_bases.py [--python /path/to/python]
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

SKIP_DIRS = {"__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data"}


def ldd(path: str) -> set[str]:
    try:
        out = subprocess.run(["ldd", path], capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return set()
    libs = set()
    for line in out.splitlines():
        parts = line.split("=>")
        target = (parts[1] if len(parts) > 1 else parts[0]).strip().split(" (")[0].strip()
        if target.startswith("/"):
            libs.add(target)
    return libs


def is_elf(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def walk(root: Path):
    if root.is_file() or root.is_symlink():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            yield Path(dirpath) / f


class Rootfs:
    def __init__(self) -> None:
        self.files: dict[str, Path] = {}
        self.extra: dict[str, tuple[bytes, int]] = {}

    def add(self, *paths: str) -> None:
        for p in paths:
            for f in walk(Path(p)):
                self.files[str(f)] = f
                if is_elf(f):
                    for lib in ldd(str(f)):
                        self.files[lib] = Path(lib)
                        real = os.path.realpath(lib)
                        self.files[real] = Path(real)

    def text(self, path: str, content: str, mode: int = 0o644) -> None:
        self.extra[path] = (content.encode(), mode)

    def tar(self) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            # Merged /usr (as on the host): /bin, /sbin, /lib, /lib64 are links into /usr.
            for top in ("bin", "sbin", "lib", "lib64"):
                ti = tarfile.TarInfo(top)
                ti.type, ti.linkname = tarfile.SYMTYPE, f"usr/{top}"
                t.addfile(ti)
            done: set[str] = set()
            for name in sorted(self.files):
                arc = name.lstrip("/")
                if arc.split("/", 1)[0] in ("bin", "sbin", "lib", "lib64"):
                    arc = "usr/" + arc
                if arc in done:
                    continue
                done.add(arc)
                try:
                    t.add(name, arcname=arc, recursive=False)
                except (FileNotFoundError, PermissionError):
                    pass
            for d in ("tmp", "var/tmp", "var/run/postgresql", "app", "var/lib/atlas/snapshots"):
                ti = tarfile.TarInfo(d)
                ti.type, ti.mode = tarfile.DIRTYPE, 0o1777
                t.addfile(ti)
            for name, (data, mode) in self.extra.items():
                ti = tarfile.TarInfo(name.lstrip("/"))
                ti.size, ti.mode = len(data), mode
                t.addfile(ti, io.BytesIO(data))
        return buf.getvalue()


def common(r: Rootfs) -> None:
    r.add("/bin/sh", "/usr/bin/dash", "/lib64/ld-linux-x86-64.so.2", "/etc/ssl/certs/ca-certificates.crt", "/usr/share/zoneinfo",
          "/etc/nsswitch.conf", "/usr/sbin/ldconfig", "/usr/sbin/ldconfig.real", "/etc/ld.so.cache")   # ctypes.util.find_library (psycopg -> libpq) uses ldconfig -p
    r.text("/etc/passwd", "root:x:0:0:root:/root:/bin/sh\natlas:x:999:999:atlas:/app:/bin/sh\npostgres:x:998:998::/var/lib/postgresql:/bin/sh\n")
    r.text("/etc/group", "root:x:0:\natlas:x:999:\npostgres:x:998:\n")
    r.text("/etc/hosts", "127.0.0.1 localhost\n")


def python_rootfs(py: str) -> Rootfs:
    r = Rootfs()
    common(r)
    code = ("import sys,json;print(json.dumps({'exe':sys.executable,'prefix':sys.base_prefix,'path':[p for p in sys.path if p]}))")
    import json
    info = json.loads(subprocess.run([py, "-c", code], capture_output=True, text=True, check=True).stdout)
    real = os.path.realpath(info["exe"])
    stdlib = Path(info["prefix"]) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    r.add(real)
    for entry in stdlib.iterdir():
        if entry.name not in ("site-packages",) and entry.name not in SKIP_DIRS:
            r.add(str(entry))
    # Packages the application imports (measured by importing the app's entry points).
    probe = ("import sys,importlib;mods=['app.main','app.worker_main','uvicorn','uvicorn.main','alembic.config','alembic.command',"
             "'alembic.ddl.postgresql','alembic.runtime.migration','psycopg','sqlalchemy.dialects.postgresql.psycopg','pypdf','openpyxl',"
             "'python_multipart','uvicorn.lifespan.on','uvicorn.protocols.http.h11_impl','uvicorn.loops.auto','uvicorn.protocols.websockets.auto',"
             "'logging.config'];[importlib.import_module(m) for m in mods];"
             "print('\\n'.join(sorted({getattr(m,'__file__','') or '' for m in sys.modules.values()})))")
    backend = Path(__file__).resolve().parents[2] / "backend"
    files = subprocess.run([py, "-c", probe], capture_output=True, text=True, check=True, cwd=backend,
                           env=dict(os.environ, ENVIRONMENT="test", PYTHONPATH=str(backend))).stdout.split()
    roots: set[str] = set()
    for f in files:
        if not f or str(backend) in f or f.startswith(str(stdlib) + "/") and "site-packages" not in f:
            continue
        for sp in info["path"]:
            if f.startswith(sp.rstrip("/") + "/") and sp != str(stdlib):
                top = f[len(sp.rstrip("/")) + 1:].split("/")[0]
                roots.add(sp.rstrip("/") + "/" + top)
                break
    for root in sorted(roots):
        r.add(root)
    # libpq for psycopg (ctypes-loaded, so ldd cannot see it)
    for cand in ("/usr/lib/x86_64-linux-gnu/libpq.so.5",):
        if Path(cand).exists():
            r.add(cand, os.path.realpath(cand))
    site_dirs = sorted({str(Path(x).parent) for x in roots})
    r.text("/usr/local/lib/atlas-substitute-pythonpath", ":".join(site_dirs) + "\n")
    r.text("/usr/local/bin/python", f"#!/bin/sh\nexport PYTHONPATH=\"/app:{':'.join(site_dirs)}\"\nexec {real} \"$@\"\n", 0o755)
    for tool, mod in (("uvicorn", "uvicorn"), ("alembic", "alembic.config")):
        r.text(f"/usr/local/bin/{tool}", f"#!/bin/sh\nexec /usr/local/bin/python -m {mod} \"$@\"\n", 0o755)
    return r


def postgres_rootfs() -> Rootfs:
    r = Rootfs()
    common(r)
    r.add("/usr/lib/postgresql/16", "/usr/share/postgresql/16", "/usr/bin/rm", "/usr/bin/cat", "/usr/bin/ls")
    r.text("/usr/local/bin/pg-entrypoint", """#!/bin/sh
# SUBSTITUTE postgres entrypoint: initialise once, then run in the foreground.
set -e
D=/var/lib/postgresql/data
if [ ! -s "$D/PG_VERSION" ]; then
  echo "$POSTGRES_PASSWORD" > /tmp/pwfile
  /usr/lib/postgresql/16/bin/initdb -D "$D" -U "$POSTGRES_USER" --pwfile=/tmp/pwfile -A scram-sha-256 -E UTF8 --locale=C
  rm /tmp/pwfile
  echo "listen_addresses='*'" >> "$D/postgresql.conf"
  echo "host all all 0.0.0.0/0 scram-sha-256" >> "$D/pg_hba.conf"
  /usr/lib/postgresql/16/bin/pg_ctl -D "$D" -o "-c listen_addresses=''" -w start
  PGPASSWORD="$POSTGRES_PASSWORD" /usr/lib/postgresql/16/bin/psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \\"$POSTGRES_DB\\""
  /usr/lib/postgresql/16/bin/pg_ctl -D "$D" -m fast -w stop
fi
exec /usr/lib/postgresql/16/bin/postgres -D "$D"
""", 0o755)
    return r


def node_rootfs() -> Rootfs:
    r = Rootfs()
    common(r)
    node = subprocess.run(["sh", "-c", "command -v node"], capture_output=True, text=True).stdout.strip()
    r.add(os.path.realpath(node))
    r.text("/usr/local/bin/node", f"#!/bin/sh\nexec {os.path.realpath(node)} \"$@\"\n", 0o755)
    return r


def docker_import(tag: str, rootfs: Rootfs) -> None:
    data = rootfs.tar()
    subprocess.run(["docker", "import", "-m", "SUBSTITUTE base assembled from host binaries (registries unreachable); not for production",
                    "-", tag], input=data, check=True)
    print(f"{tag}: {len(rootfs.files)} files, {len(data) / 1e6:.0f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    docker_import("atlas-substitute/python-runtime:local", python_rootfs(a.python))
    docker_import("atlas-substitute/postgres16:local", postgres_rootfs())
    docker_import("atlas-substitute/node:local", node_rootfs())
