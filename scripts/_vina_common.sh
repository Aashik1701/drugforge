# shellcheck shell=bash
# ---------------------------------------------------------------------------
# _vina_common.sh — shared constants + helpers for setup_vina.sh / verify_vina.sh
#
# Sourced, never executed directly. The pinned version and the per-platform
# SHA256 checksums live HERE and ONLY here, so the two scripts can never
# disagree about what a "correct" binary is.
# ---------------------------------------------------------------------------

# --- THE PIN -------------------------------------------------------------------
# One specific AutoDock Vina release. Do NOT change this to "latest" or resolve
# it at runtime: the whole point is that everyone reproducing this repo's
# docking benchmark gets byte-for-byte the same binary.
#
# Release: https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7
VINA_VERSION="1.2.7"
VINA_RELEASE_BASE="https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v${VINA_VERSION}"

# --- Per-platform release asset + its SHA256 --------------------------------
# Checksums computed from the official GitHub release assets (verified by
# re-download). Sizes are recorded in scripts/README-vina.md.
#
#   platform key   ->   "<asset filename> <sha256>"
#
# Supported: linux-x86_64, macos-x86_64, macos-arm64  (per the docking spec).
# NOT supported on purpose: linux-aarch64, windows, 32-bit. See vina_asset_line().
_vina_asset_line() {
	case "$1" in
	linux-x86_64)
		echo "vina_${VINA_VERSION}_linux_x86_64 f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644"
		;;
	macos-x86_64)
		echo "vina_${VINA_VERSION}_mac_x86_64 9f44ccbb163223613283a75d0be53235d9e63f4da08292cb7196144f9838b7f9"
		;;
	macos-arm64)
		echo "vina_${VINA_VERSION}_mac_aarch64 823c2bbacf26d72183861322345f0a89736aca66c8e81054c66f93af5ad623f1"
		;;
	*)
		return 1
		;;
	esac
}

# Upstream v1.2.7 ALSO ships an official, checksummed linux_aarch64 build. It is
# intentionally not in the supported set above (the spec named linux-aarch64 as
# the "unsupported platform" example). If you need it, add this line to the
# case above — the checksum is already verified:
#
#   linux-aarch64)
#       echo "vina_${VINA_VERSION}_linux_aarch64 d30c18a7d5f6f8ea9146e1cbc0aa7ade0bbb105b54ece08b4e5a7fa53edb6c62" ;;

# --- Repo layout -----------------------------------------------------------
# This file lives at <repo>/scripts/_vina_common.sh
_VINA_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${_VINA_COMMON_DIR}/.." && pwd)"
VINA_BIN_DEFAULT="${REPO_ROOT}/backend/bin/vina"

# VINA_BIN env override is honoured so this matches backend/app/utils/vina_env.py
vina_bin_path() {
	echo "${VINA_BIN:-$VINA_BIN_DEFAULT}"
}

# --- Platform detection --------------------------------------------------------
# Emits one of: linux-x86_64 | macos-x86_64 | macos-arm64 | <raw "os-arch">
detect_platform() {
	local os arch
	os="$(uname -s)"
	arch="$(uname -m)"

	case "$os" in
	Linux) os="linux" ;;
	Darwin) os="macos" ;;
	*) os="$(echo "$os" | tr '[:upper:]' '[:lower:]')" ;;
	esac

	case "$arch" in
	x86_64 | amd64) arch="x86_64" ;;
	arm64 | aarch64)
		# normalise: macOS reports arm64, Linux reports aarch64
		if [ "$os" = "macos" ]; then arch="arm64"; else arch="aarch64"; fi
		;;
	esac

	echo "${os}-${arch}"
}

# --- SHA256 helper (portable across Linux/macOS) ------------------------------
sha256_of() {
	local file="$1"
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$file" | awk '{print $1}'
	elif command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$file" | awk '{print $1}'
	else
		echo "ERROR: neither sha256sum nor shasum found on PATH" >&2
		return 127
	fi
}

# --- pretty output -----------------------------------------------------------
_c_red() { printf '\033[31m%s\033[0m' "$*"; }
_c_grn() { printf '\033[32m%s\033[0m' "$*"; }
_c_ylw() { printf '\033[33m%s\033[0m' "$*"; }
say() { printf '%s\n' "$*"; }
err() { printf '%s %s\n' "$(_c_red '✗')" "$*" >&2; }
ok() { printf '%s %s\n' "$(_c_grn '✓')" "$*"; }
warn() { printf '%s %s\n' "$(_c_ylw '!')" "$*" >&2; }

# Print the "this platform is not supported" message and the actionable fix.
unsupported_platform_msg() {
	local platform="$1"
	err "Unsupported platform: ${platform}"
	{
		say ""
		say "scripts/setup_vina.sh ships pinned, checksum-verified AutoDock Vina"
		say "${VINA_VERSION} for exactly these platforms:"
		say "    linux-x86_64    (asset: vina_${VINA_VERSION}_linux_x86_64)"
		say "    macos-x86_64    (asset: vina_${VINA_VERSION}_mac_x86_64)"
		say "    macos-arm64     (asset: vina_${VINA_VERSION}_mac_aarch64)"
		say ""
		case "$platform" in
		linux-aarch64)
			say "Upstream DOES publish an official vina_${VINA_VERSION}_linux_aarch64"
			say "build. To use it, add this line to _vina_asset_line() in"
			say "scripts/_vina_common.sh (checksum already verified):"
			say ""
			say "    linux-aarch64)"
			say "        echo \"vina_${VINA_VERSION}_linux_aarch64 d30c18a7d5f6f8ea9146e1cbc0aa7ade0bbb105b54ece08b4e5a7fa53edb6c62\" ;;"
			say ""
			say "Otherwise run this repo's docker setup with --platform=linux/amd64,"
			say "or build Vina from source: https://github.com/ccsb-scripps/AutoDock-Vina"
			;;
		*)
			say "Get a build from https://github.com/ccsb-scripps/AutoDock-Vina/releases"
			say "or build from source, then point VINA_BIN at it."
			;;
		esac
	} >&2
}
