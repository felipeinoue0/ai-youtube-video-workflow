#!/bin/bash
# CRLF guard (#91) — deliberately the first executable statement, above
# `set -euo pipefail`. There is no blank line between here and the guard on
# purpose: an empty line in a CRLF copy is a bare `\r` command, and bash would
# report `$'\r': command not found` before the guard could say anything useful.
# Comment lines absorb it; use `#` on its own for a paragraph break, never an
# empty line.
#
# This script runs through bash from the bind mount, so bash parses the *host*
# working-tree bytes. A Windows checkout whose working tree predates the
# `.gitattributes` `* text=auto eol=lf` rule keeps stale CRLF bytes, and
# `git status` stays clean throughout, because git compares normalized content.
# Bash then reads `set -euo pipefail\r` and dies with `set: pipefail: invalid
# option name` — a message that names neither the cause nor a repair.
#
# The guard has to survive the CRLF it reports. Bash parses a whole compound
# command before executing it, so a plain multi-line `if` would fail to parse
# before its own check ever ran. Every line of this block therefore ends with
# the `# crlf-guard` comment tag, which absorbs the trailing `\r`.
if [[ -f "${BASH_SOURCE[0]}" ]] && grep -q $'\r$' "${BASH_SOURCE[0]}"; then # crlf-guard
    printf '%s\n' "[dev] ${BASH_SOURCE[0]##*/} has CRLF line endings, so bash cannot parse it — the sandbox would die with 'set: pipefail: invalid option name'." "      The bind mount serves the host checkout as-is. Re-check it out with LF endings (README.md -> Troubleshooting):" >&2 # crlf-guard
    printf '%s\n' "        git rm --cached -r . >/dev/null && git reset --hard" >&2; exit 1 # crlf-guard
fi # crlf-guard
set -euo pipefail

# Dev sandbox entrypoint. This project is a CLI with no dev server, so `dev-up`
# syncs the locked environment into the `.venv` volume and then keeps the
# container alive for the agents and `make dev-shell`.
#
# Usage: set the entrypoint to this script in docker-compose.yml

DEV_DIR="${DEV_DIR:-/workspace}"
SLEEP_ON_IDLE="${SLEEP_ON_IDLE:-true}"

# --- Passwd entry for the runtime user ---------------------------------------
if ! getent passwd "$(id -u)" >/dev/null; then
    if [[ "$(id -u)" -eq 0 ]]; then
        echo "[dev] UID 0 has no passwd entry — adding a fallback identity."
        printf 'sandbox:x:%s:%s:Sandbox User:/home/%s:/bin/bash\n' \
            "$(id -u)" "$(id -g)" "${DEV_USER:-devuser}" >> /etc/passwd
    else
        echo "[dev] WARNING: UID $(id -u) has no passwd entry." >&2
    fi
fi

# --- Start dev command if available, else sleep -------------------------------
if [ "${SLEEP_ON_IDLE}" = "true" ] && [ ! -f "${DEV_DIR}/.dev/start" ]; then
    echo "[dev] No code found; sleeping indefinitely for shell access..."
    exec sleep infinity
fi

echo "[dev] Syncing the locked Python environment (uv sync --locked)..."
cd "${DEV_DIR}" && uv sync --locked
echo "[dev] Ready: run the agents with make claude / opencode / codex, or make dev-shell."
exec sleep infinity
