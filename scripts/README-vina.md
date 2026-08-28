# Pinned AutoDock Vina — acquisition & verification

`backend/bin/vina` is **not** in git (large third-party binary, own licence).
It is acquired per-checkout / per-container by `scripts/setup_vina.sh`.

## The pin

| | |
|---|---|
| Version | **1.2.7** |
| Release | <https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7> |
| Published | 2025-02-26 |

The version is hardcoded in `scripts/_vina_common.sh` (`VINA_VERSION`). It is
never resolved to "latest" at runtime — every reproduction of this repo's
docking benchmark gets byte-for-byte the same binary.

## Per-platform release assets + SHA256

Checksums were computed from the official GitHub release assets and confirmed
by re-download.

| Platform key | Release asset | Size (bytes) | SHA256 |
|---|---|---:|---|
| `linux-x86_64` | `vina_1.2.7_linux_x86_64` | 4056088 | `f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644` |
| `macos-x86_64` | `vina_1.2.7_mac_x86_64` | 1215392 | `9f44ccbb163223613283a75d0be53235d9e63f4da08292cb7196144f9838b7f9` |
| `macos-arm64` | `vina_1.2.7_mac_aarch64` | 1171704 | `823c2bbacf26d72183861322345f0a89736aca66c8e81054c66f93af5ad623f1` |

### Not in the supported set (on purpose)

| Platform | Asset | Size (bytes) | SHA256 | Note |
|---|---|---:|---|---|
| `linux-aarch64` | `vina_1.2.7_linux_aarch64` | 4414616 | `d30c18a7d5f6f8ea9146e1cbc0aa7ade0bbb105b54ece08b4e5a7fa53edb6c62` | Upstream ships it; add a case line to `_vina_asset_line()` to enable. The docking spec named linux-aarch64 as the "unsupported platform" example, so it is opt-in. |
| Windows | `vina_1.2.7_win.exe` | 1233920 | — | Not a deployment target for this project. |

Both Linux assets are **statically linked** ELF binaries (no glibc / shared
library version constraints), which is why they run unmodified in
`python:3.11-slim`.

## Usage

```bash
scripts/setup_vina.sh            # download + checksum-verify + install (idempotent)
scripts/setup_vina.sh --verify   # verify only, no download
scripts/setup_vina.sh --force    # re-download even if a valid binary exists
scripts/verify_vina.sh           # exit 0 iff present, verified, and runnable here
```

`verify_vina.sh` exit codes: `0` ok · `3` checksum mismatch · `4` won't execute
(wrong arch) · `5` unexpected version · `1` missing / not executable / platform
unsupported.

## Refreshing the pin (deliberate upgrades only)

1. Pick the new release tag.
2. Download each asset, compute `sha256sum`.
3. Update `VINA_VERSION` and the digests in `scripts/_vina_common.sh`, and this
   table.
4. Update `EXPECTED_VINA_VERSION` in `backend/app/utils/vina_env.py`.
5. Re-run the determinism proof (`docs/development/local-worker.md`) — affinities
   **will** change between Vina versions; that is expected and is exactly why
   the version is recorded in every job.
