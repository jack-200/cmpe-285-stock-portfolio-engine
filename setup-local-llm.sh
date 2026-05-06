#!/usr/bin/env bash
# One-time (or occasional) setup: install Ollama if missing, then pull LLM_MODEL.
# Usage:
#   ./setup-local-llm.sh           # install when needed + pull model
#   ./setup-local-llm.sh --pull-only   # only ollama pull (Ollama must exist)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

MODEL="${LLM_MODEL:-llama3.2}"
PULL_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --pull-only) PULL_ONLY=true ;;
  esac
done

install_ollama() {
  local uname_s
  uname_s="$(uname -s)"
  case "$uname_s" in
    Linux)
      echo "Installing Ollama via official script (network required) ..."
      curl -fsSL https://ollama.com/install.sh | sh
      ;;
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        echo "Installing Ollama via Homebrew ..."
        brew install ollama
      else
        echo "error: Homebrew not found. Install from https://brew.sh or use https://ollama.com/download" >&2
        exit 1
      fi
      ;;
    *)
      echo "error: automatic install is not defined for $uname_s. Use https://ollama.com/download" >&2
      exit 1
      ;;
  esac
}

if [[ "$PULL_ONLY" != true ]]; then
  if command -v ollama >/dev/null 2>&1; then
    echo "Ollama already on PATH: $(command -v ollama)"
  else
    install_ollama
  fi
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "error: ollama command not found. Install from https://ollama.com or run this script without --pull-only." >&2
  exit 1
fi

echo "Pulling model '$MODEL' (change with LLM_MODEL in .env). First pull can take several minutes."
ollama pull "$MODEL"
echo "Done. Start the app with ./start.sh"
echo "If requests to Ollama fail, ensure the daemon is running (often automatic after install; otherwise run: ollama serve)."
