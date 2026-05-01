#!/bin/sh
set -eu

CHAT_CODE_ROOT="${SWITCH_CHAT_CODE_ROOT:-/tmp/switch-chat-code}"
mkdir -p "$CHAT_CODE_ROOT"
chown switch:switch "$CHAT_CODE_ROOT" 2>/dev/null || chmod 1777 "$CHAT_CODE_ROOT"

DOCKER_SOCKET="${SWITCH_DOCKER_SOCKET:-/var/run/docker.sock}"
if [ -S "$DOCKER_SOCKET" ] && [ -n "${SWITCH_DOCKER_GID:-}" ]; then
  DOCKER_GROUP="$(getent group "$SWITCH_DOCKER_GID" | cut -d: -f1 || true)"
  if [ -z "$DOCKER_GROUP" ]; then
    DOCKER_GROUP="switch-docker"
    addgroup --system --gid "$SWITCH_DOCKER_GID" "$DOCKER_GROUP" >/dev/null 2>&1 || true
  fi
  adduser switch "$DOCKER_GROUP" >/dev/null 2>&1 || true
fi

exec runuser -u switch -- "$@"
