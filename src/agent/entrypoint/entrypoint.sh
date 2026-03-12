#!/bin/bash
set -e

echo "=== A2W Lucas Agent Starting ==="
echo "Target namespace: $TARGET_NAMESPACE"
echo "SQLite path: $SQLITE_PATH"

if [ -f ./.env.providers.local ]; then
    echo "Loading local provider env from .env.providers.local"
    set -a
    . ./.env.providers.local
    set +a
fi

# === SRE MODE ===
SRE_MODE="${SRE_MODE:-autonomous}"
echo "Lucas agent mode: $SRE_MODE"

LLM_BACKEND="${LLM_BACKEND:-claude-code}"
echo "LLM backend: $LLM_BACKEND"

# === AUTHENTICATION SETUP ===
AUTH_MODE="${AUTH_MODE:-api-key}"
echo "Auth mode: $AUTH_MODE"

if [ "$LLM_BACKEND" = "claude-code" ] && [ "$AUTH_MODE" = "credentials" ]; then
    if [ -f "$HOME/.claude/.credentials.json" ]; then
        echo "Using mounted credentials.json"
    elif [ -f /secrets/credentials.json ]; then
        echo "Copying credentials from /secrets/"
        mkdir -p "$HOME/.claude"
        cp /secrets/credentials.json "$HOME/.claude/.credentials.json"
    else
        echo "ERROR: AUTH_MODE=credentials but no credentials.json found"
        exit 1
    fi
elif [ "$LLM_BACKEND" = "claude-code" ] && [ "$AUTH_MODE" = "api-key" ]; then
    if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$LLM_API_KEY" ]; then
        echo "ERROR: AUTH_MODE=api-key but neither ANTHROPIC_API_KEY nor LLM_API_KEY is set"
        exit 1
    fi
    echo "Using API key authentication"
elif [ "$LLM_BACKEND" = "claude-code" ]; then
    echo "ERROR: Invalid AUTH_MODE: $AUTH_MODE (use 'api-key' or 'credentials')"
    exit 1
else
    echo "Using provider-neutral authentication via LLM_API_KEY / provider-specific env"
fi

exec python3 /app/cron_runner.py
