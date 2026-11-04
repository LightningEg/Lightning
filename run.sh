#!/usr/bin/env bash
# Lightning launcher for macOS / Linux
set -u
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
if [ ! -f .venv/.requirements-installed ] || [ requirements.txt -nt .venv/.requirements-installed ] || [ pyproject.toml -nt .venv/.requirements-installed ] ||
   ! .venv/bin/python -c 'import fastapi, uvicorn, jinja2, multipart, cryptography, sqlcipher3' >/dev/null 2>&1; then
    .venv/bin/python tools/install_source.py || exit 1
    touch .venv/.requirements-installed
fi
server_pid=""
interrupted=0
stop_server() {
    if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
        kill -TERM "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    server_pid=""
}
on_interrupt() {
    interrupted=1
}
trap on_interrupt INT
trap 'stop_server; exit 143' TERM

restart_prompt() {
    local reason="$1"
    printf '%s Type y then Enter to start Lightning again, or Ctrl+C to quit.\n' "$reason"
    while true; do
        if IFS= read -r answer; then
            case "$answer" in
                y|Y) return 0 ;;
                *) printf 'Type y then Enter to start Lightning again, or Ctrl+C to quit.\n' ;;
            esac
        else
            if [ "$interrupted" -eq 1 ]; then
                return 130
            fi
            printf 'No writable interactive input is available. Open Lightning from its desktop launcher or a normal terminal to restart it here.\n' >&2
            return 1
        fi
        if [ "$interrupted" -eq 1 ]; then
            return 130
        fi
    done
}

while true; do
    interrupted=0
    .venv/bin/python -m lightning "$@" &
    server_pid=$!
    if [ ! -t 0 ]; then
        wait "$server_pid"
        exit $?
    fi
    printf '\nLightning is running. Type y then Enter to restart it; press Ctrl+C to stop.\n'
    while kill -0 "$server_pid" 2>/dev/null; do
        if [ "$interrupted" -eq 1 ]; then
            stop_server
            break
        fi
        if IFS= read -r -t 1 answer; then
            case "$answer" in
                y|Y)
                    printf 'Restarting Lightning...\n'
                    stop_server
                    break
                    ;;
                *)
                    printf 'Type y then Enter to restart Lightning.\n'
                    ;;
            esac
        else
            read_status=$?
            if [ "$read_status" -eq 1 ]; then
                printf 'Interactive input is unavailable; leaving the server running without a restart prompt.\n' >&2
                wait "$server_pid"
                exit $?
            fi
        fi
    done
    if [ "$interrupted" -eq 1 ]; then
        if restart_prompt 'Lightning stopped.'; then
            continue
        else
            exit $?
        fi
    fi
    if [ -n "$server_pid" ]; then
        wait "$server_pid"
        status=$?
        server_pid=""
        if [ "$status" -ne 0 ]; then
            if restart_prompt "Lightning exited with status $status."; then
                continue
            else
                exit "$status"
            fi
        else
            exit 0
        fi
    fi
done
