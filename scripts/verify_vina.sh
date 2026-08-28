#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# verify_vina.sh — is backend/bin/vina the pinned build, and does it run here?
#
#   scripts/verify_vina.sh
#
# Exit codes:
#   0  present, executable, SHA256 matches the pin, runs, reports the pinned version
#   3  present but SHA256 does NOT match the pinned per-platform digest
#   4  present but the binary will not execute here (wrong architecture / broken)
#   5  present but reports an unexpected version string
#   1  missing, not executable, or platform unsupported
#
# Prints the version AutoDock Vina reports on success.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_vina_common.sh
. "${SCRIPT_DIR}/_vina_common.sh"

PLATFORM="$(detect_platform)"
VINA_BIN_PATH="$(vina_bin_path)"

say "Platform     : ${PLATFORM}"
say "Checking     : ${VINA_BIN_PATH}"
say "Pinned Vina  : ${VINA_VERSION}"
say ""

# --- Platform must be one we have a pin for ------------------------------
if ! ASSET_LINE="$(_vina_asset_line "$PLATFORM")"; then
	unsupported_platform_msg "$PLATFORM"
	exit 1
fi
EXPECTED_SHA="${ASSET_LINE##* }"

# --- Presence + executable bit -----------------------------------------
if [ ! -f "$VINA_BIN_PATH" ]; then
	err "Not found: ${VINA_BIN_PATH}"
	err "Fix: run  scripts/setup_vina.sh"
	exit 1
fi
if [ ! -x "$VINA_BIN_PATH" ]; then
	err "Not executable: ${VINA_BIN_PATH}"
	err "Fix: chmod +x '${VINA_BIN_PATH}'  (or re-run scripts/setup_vina.sh)"
	exit 1
fi

# --- Checksum must match the pin (this also proves it's the right arch) ---
ACTUAL_SHA="$(sha256_of "$VINA_BIN_PATH")"
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
	err "SHA256 mismatch — this is NOT the pinned ${PLATFORM} build."
	err "  expected: ${EXPECTED_SHA}"
	err "  got     : ${ACTUAL_SHA}"
	err "Fix: scripts/setup_vina.sh --force"
	exit 3
fi
ok "SHA256 matches the pinned ${PLATFORM} digest"

# --- It must actually execute on this host ----------------------------
if ! VERSION_OUT="$("$VINA_BIN_PATH" --version 2>&1)"; then
	err "Binary will not run here:"
	printf '%s\n' "$VERSION_OUT" | sed 's/^/    /' >&2
	err "Likely an architecture mismatch between the binary and this host."
	err "Fix: scripts/setup_vina.sh --force"
	exit 4
fi

REPORTED_LINE="$(printf '%s\n' "$VERSION_OUT" | grep -i 'AutoDock Vina' | head -n1)"
say "Reports      : ${REPORTED_LINE:-<no 'AutoDock Vina' line in --version output>}"

if ! printf '%s' "$REPORTED_LINE" | grep -q "$VINA_VERSION"; then
	err "Version string does not contain the pinned '${VINA_VERSION}'."
	err "Fix: scripts/setup_vina.sh --force"
	exit 5
fi

say ""
ok "Vina ${VINA_VERSION} is installed, verified, and runnable on ${PLATFORM}."
