#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_vina.sh — reproducibly install ONE pinned AutoDock Vina build.
#
#   scripts/setup_vina.sh            download + verify + install backend/bin/vina
#   scripts/setup_vina.sh --verify   only check the installed binary (no download)
#   scripts/setup_vina.sh --force    re-download even if a valid binary exists
#   scripts/setup_vina.sh --help
#
# Guarantees:
#   * Pinned version (see _vina_common.sh: VINA_VERSION) — never "latest".
#   * SHA256 of the downloaded asset is checked against a hardcoded per-platform
#     digest. Any mismatch aborts loudly and removes the bad file.
#   * Idempotent: a correct, already-verified binary => exit 0, no re-download.
#   * Unsupported platform (e.g. linux-aarch64) => actionable error, no wrong
#     asset is ever fetched.
#
# The binary is NOT committed to git (large third-party artifact, own licence).
# Run this once on every fresh checkout / container.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_vina_common.sh
. "${SCRIPT_DIR}/_vina_common.sh"

usage() {
	sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

MODE="install"
for arg in "${@:-}"; do
	case "$arg" in
	--verify) MODE="verify" ;;
	--force) MODE="force" ;;
	-h | --help)
		usage
		exit 0
		;;
	"") ;;
	*)
		err "Unknown argument: $arg"
		usage
		exit 2
		;;
	esac
done

PLATFORM="$(detect_platform)"
VINA_BIN_PATH="$(vina_bin_path)"

# --verify just shells out to verify_vina.sh and mirrors its exit code.
if [ "$MODE" = "verify" ]; then
	exec "${SCRIPT_DIR}/verify_vina.sh"
fi

# --- Resolve the asset + expected checksum for this platform ---------------
if ! ASSET_LINE="$(_vina_asset_line "$PLATFORM")"; then
	unsupported_platform_msg "$PLATFORM"
	exit 1
fi
ASSET_NAME="${ASSET_LINE%% *}"
EXPECTED_SHA="${ASSET_LINE##* }"
ASSET_URL="${VINA_RELEASE_BASE}/${ASSET_NAME}"

say "Platform     : ${PLATFORM}"
say "Vina version : ${VINA_VERSION}  (pinned)"
say "Release asset: ${ASSET_NAME}"
say "Expected sha : ${EXPECTED_SHA}"
say "Install path : ${VINA_BIN_PATH}"
say ""

# --- Idempotency: correct binary already in place? ------------------------
if [ "$MODE" != "force" ] && [ -f "$VINA_BIN_PATH" ]; then
	CURRENT_SHA="$(sha256_of "$VINA_BIN_PATH")"
	if [ "$CURRENT_SHA" = "$EXPECTED_SHA" ]; then
		chmod +x "$VINA_BIN_PATH" 2>/dev/null || true
		ok "Vina ${VINA_VERSION} already installed and verified — nothing to do."
		say "  (run with --force to re-download, or --verify to also run the binary)"
		exit 0
	fi
	warn "Existing ${VINA_BIN_PATH} has sha ${CURRENT_SHA}"
	warn "which does NOT match the pinned ${PLATFORM} digest — replacing it."
fi

# --- Download to a temp file, verify, THEN move into place ----------------
mkdir -p "$(dirname "$VINA_BIN_PATH")"
TMP_FILE="$(mktemp "${VINA_BIN_PATH}.XXXXXX.download")"
cleanup() { rm -f "$TMP_FILE"; }
trap cleanup EXIT

say "Downloading ${ASSET_URL} ..."
if command -v curl >/dev/null 2>&1; then
	curl -fsSL --retry 3 --retry-delay 2 -o "$TMP_FILE" "$ASSET_URL"
elif command -v wget >/dev/null 2>&1; then
	wget -q -O "$TMP_FILE" "$ASSET_URL"
else
	err "Need either curl or wget to download the Vina binary."
	exit 1
fi

DOWNLOAD_SHA="$(sha256_of "$TMP_FILE")"
if [ "$DOWNLOAD_SHA" != "$EXPECTED_SHA" ]; then
	err "SHA256 MISMATCH — refusing to install."
	err "  expected: ${EXPECTED_SHA}"
	err "  got     : ${DOWNLOAD_SHA}"
	err "  url     : ${ASSET_URL}"
	err "The download was corrupted, MITM'd, or upstream re-published the asset."
	err "Nothing was written to ${VINA_BIN_PATH}."
	exit 1
fi
ok "SHA256 verified: ${DOWNLOAD_SHA}"

chmod +x "$TMP_FILE"
mv -f "$TMP_FILE" "$VINA_BIN_PATH"
trap - EXIT

# --- Prove the freshly installed binary actually runs on this host --------
if VERSION_OUT="$("$VINA_BIN_PATH" --version 2>&1)"; then
	ok "Installed: ${VINA_BIN_PATH}"
	say "  ${VERSION_OUT%%$'\n'*}"
else
	err "Binary installed but '${VINA_BIN_PATH} --version' failed:"
	err "  ${VERSION_OUT}"
	err "This usually means an architecture mismatch. Removing it."
	rm -f "$VINA_BIN_PATH"
	exit 1
fi

say ""
ok "Done. Verify anytime with: scripts/verify_vina.sh"
