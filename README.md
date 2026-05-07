# Stock Portfolio Suggestion Engine

A Python-based application that generates stock portfolio recommendations using real-time market data and various investment strategies.

[**Live UI Demo**](https://jack-200.github.io/cmpe-285-stock-portfolio-engine/)  
_(Note: This is a static UI preview. Real-time data fetching and portfolio generation require running the backend locally.)_

## Table of Contents

- [Team Members](#team-members)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)

## Team Members

- **Jack Liang** ([jack.liang@sjsu.edu](mailto:jack.liang@sjsu.edu))
- **Jiajian Liu** ([jiajian.liu@sjsu.edu](mailto:jiajian.liu@sjsu.edu))
- **Jeffrey Gu** ([jeffrey.gu@sjsu.edu](mailto:jeffrey.gu@sjsu.edu))
- **Sean Patrick Konaka** ([seanpatrick.konaka@sjsu.edu](mailto:seanpatrick.konaka@sjsu.edu))

## Features

- **Investment Strategies**: Ethical, Growth, Index, Quality, and Value investing.
- **Real-time Data**: Live stock prices and historical trends via `yfinance`.
- **Dynamic Allocation**: Automated fund distribution based on selected strategies.
- **Modern UI**: Interactive glassmorphism dashboard.

## Tech Stack

- **Backend**: Python (FastAPI, Uvicorn, yfinance, Pandas, Pydantic)
- **Frontend**: HTML5, CSS3, JavaScript (Chart.js)
- **Tools & Management**: uv, **`scripts/start.sh`** / **`scripts/setup-local-llm.sh`**, Antigravity AI, VS Code, GitHub

## Getting Started

### Prerequisites

- **Python 3.12+** (matches `main.py` metadata).
- **Optional:** [Ollama](https://ollama.com) for local LLM features (portfolio “why this pick” blurbs and InvestIQ chat). Cloud OpenAI works too; see `.env.example`.

### Shell scripts

| Script | Purpose |
|--------|---------|
| **`./scripts/setup-local-llm.sh`** | One-time (or occasional) **Ollama** setup: installs Ollama on **Linux** (official installer) or **macOS** (Homebrew if present), then runs `ollama pull` for `LLM_MODEL` (default `llama3.2`). Reads `.env` when present. Use `./scripts/setup-local-llm.sh --pull-only` if Ollama is already installed and you only need to pull/update the model. |
| **`./scripts/start.sh`** | Creates **`.venv`** when missing, installs **`requirements.txt`** when the venv is new or requirements changed, **sources `.env`** if it exists, prints LLM/Ollama hints, then runs **`python main.py`** so the app serves **`http://localhost:8000`**. |

Make scripts executable once if needed: `chmod +x scripts/setup-local-llm.sh scripts/start.sh`.

### Recommended flow

1. Copy **`cp .env.example .env`** and adjust variables (`LLM_BACKEND`, `OLLAMA_HOST`, `LLM_MODEL`, optional separate chat/rationale models—see `.env.example`).
2. **Optional:** run **`./scripts/setup-local-llm.sh`** so Ollama and your model are ready locally.
3. Run **`./scripts/start.sh`** and open **`http://localhost:8000`** in a browser.

### Without the scripts

You can still use **`uv run main.py`** (dependencies come from the PEP 723 block in `main.py`) or create a venv manually, **`pip install -r requirements.txt`**, **`python main.py`**. Environment variables for the LLM are not loaded automatically unless you export them or use **`scripts/start.sh`** / your shell profile.
