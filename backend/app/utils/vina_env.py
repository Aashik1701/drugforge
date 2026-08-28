"""
vina_env — the single source of truth for locating the AutoDock Vina binary,
resolving the version that is actually installed, and probing whether it can
run on this host.

Used by:
  - jobs/workers/docking_worker.py  — per-job execution + fail-fast error text
  - jobs/workers/local_worker.py    — one preflight log line on worker startup
  - main.py                          — GET /health: `vina_available`, `vina_version`

There is deliberately NO mock or fallback here or anywhere downstream: if the
binary is missing, not executable, or the wrong architecture, callers surface
a failed job or a false `vina_available` — never a synthetic docking result.

The binary itself is acquired by `scripts/setup_vina.sh` (pinned version,
per-platform SHA256). Nothing in this module downloads anything.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# backend/app/utils/vina_env.py -> parents[2] == backend/
_BACKEND_DIR = Path(__file__).resolve().parents[2]

# The version `scripts/setup_vina.sh` pins. Kept here only as the *expected*
# value for reporting — the authoritative runtime version is whatever
# `vina --version` actually prints (see `probe_vina().version`).
EXPECTED_VINA_VERSION = "1.2.7"

SETUP_HINT = "run scripts/setup_vina.sh (see docs/development/local-worker.md)"

_VERSION_RE = re.compile(r"AutoDock Vina\s+v?([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)


def vina_bin_path() -> Path:
    """Resolved location of the Vina binary. `VINA_BIN` env overrides the default."""
    return Path(os.getenv("VINA_BIN", _BACKEND_DIR / "bin" / "vina"))


@dataclass(frozen=True)
class VinaProbe:
    """Outcome of a single preflight check against the Vina binary."""

    present: bool
    executable: bool
    arch_compatible: bool  # the binary actually executed on this host
    available: bool        # present AND executable AND arch_compatible AND version parsed
    path: str
    version: Optional[str]  # resolved from `vina --version`; None if it could not run
    error: Optional[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_version(path: Path, timeout: float = 10.0) -> tuple[Optional[str], Optional[str]]:
    """Return (version, error). `version` is None when the binary could not be run."""
    try:
        proc = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, "binary vanished between stat() and exec()"
    except OSError as exc:
        # e.g. "[Errno 8] Exec format error" — binary built for another architecture
        return None, f"cannot execute binary ({exc.__class__.__name__}: {exc})"
    except subprocess.TimeoutExpired:
        return None, f"`vina --version` did not return within {timeout:.0f}s"

    blob = (proc.stdout or "") + (proc.stderr or "")
    match = _VERSION_RE.search(blob)
    if match:
        return match.group(1), None
    if proc.returncode != 0:
        return None, f"`vina --version` exited {proc.returncode}: {blob.strip()[:200]}"
    return None, f"could not parse version from: {blob.strip()[:200]}"


def probe_vina() -> VinaProbe:
    """Full, uncached preflight: does a runnable, arch-compatible Vina exist?"""
    path = vina_bin_path()

    if not path.exists():
        return VinaProbe(
            present=False, executable=False, arch_compatible=False, available=False,
            path=str(path), version=None,
            error=f"Vina binary not found at {path}; {SETUP_HINT}",
        )

    if not os.access(path, os.X_OK):
        return VinaProbe(
            present=True, executable=False, arch_compatible=False, available=False,
            path=str(path), version=None,
            error=f"Vina binary at {path} is not executable (chmod +x); {SETUP_HINT}",
        )

    version, err = _run_version(path)
    if version is None:
        return VinaProbe(
            present=True, executable=True, arch_compatible=False, available=False,
            path=str(path), version=None,
            error=f"Vina binary at {path} did not run: {err}; {SETUP_HINT}",
        )

    return VinaProbe(
        present=True, executable=True, arch_compatible=True, available=True,
        path=str(path), version=version, error=None,
    )


# --- lightweight cache for hot paths (GET /health monitoring) ----------------
_CACHE_TTL = float(os.getenv("VINA_PROBE_CACHE_TTL_SECONDS", "30"))
_cache: dict[str, Any] = {"at": 0.0, "probe": None}


def probe_vina_cached() -> VinaProbe:
    """`probe_vina()` with a short TTL — safe to call on every /health request."""
    now = time.monotonic()
    cached: Optional[VinaProbe] = _cache["probe"]
    if cached is None or (now - _cache["at"]) > _CACHE_TTL:
        cached = probe_vina()
        _cache["probe"] = cached
        _cache["at"] = now
    return cached


def resolved_vina_version() -> Optional[str]:
    """The version string Vina reports, or None if it is not runnable."""
    return probe_vina_cached().version
