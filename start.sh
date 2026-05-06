#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"
REQ="$ROOT/requirements.txt"
DEPS_STAMP="$VENV/.deps-installed"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required but was not found in PATH" >&2
  exit 1
fi

if [[ ! -f "$REQ" ]]; then
  echo "error: missing $REQ" >&2
  exit 1
fi

need_install=false
if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment in .venv ..."
  python3 -m venv "$VENV"
  need_install=true
elif [[ ! -f "$DEPS_STAMP" ]] || [[ "$REQ" -nt "$DEPS_STAMP" ]]; then
  need_install=true
fi

if [[ "$need_install" == true ]]; then
  echo "Installing dependencies from requirements.txt (Python OpenAI client talks to local Ollama or cloud APIs) ..."
  "$PIP" install --upgrade pip
  "$PIP" install -r "$REQ"
  touch "$DEPS_STAMP"
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

echo "Starting Stock Portfolio Engine..."
echo "Dashboard: http://localhost:8000"

LLM_BACKEND="${LLM_BACKEND:-ollama}"
case "$(echo "$LLM_BACKEND" | tr '[:upper:]' '[:lower:]')" in
  none|off|false|0|disabled)
    echo "LLM rationales: off (LLM_BACKEND=$LLM_BACKEND) — using built-in text only."
    ;;
  openai)
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
      echo "LLM rationales: LLM_BACKEND=openai but OPENAI_API_KEY is empty — using built-in text."
    else
      echo "LLM rationales: OpenAI (model ${LLM_MODEL:-gpt-4o-mini})${OPENAI_BASE_URL:+ — $OPENAI_BASE_URL}"
    fi
    ;;
  ollama|local|"")
    _OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
    _OLLAMA_MODEL="${LLM_MODEL:-llama3.2}"
    echo "LLM rationales: Ollama at $_OLLAMA_HOST (model $_OLLAMA_MODEL)."
    if ! command -v ollama >/dev/null 2>&1; then
      echo "  No ollama CLI found — run ./setup-local-llm.sh once (installs Ollama on Linux/macOS and pulls $_OLLAMA_MODEL), or install manually from https://ollama.com"
    fi
    ;;
  *)
    echo "LLM rationales: unknown LLM_BACKEND=$LLM_BACKEND — using built-in text."
    ;;
esac
exec "$PYTHON" "$ROOT/main.py"
