# Stock Portfolio Suggestion Engine

A Python-based application that generates stock portfolio recommendations using real-time market data and various investment strategies.

[**Live UI Demo**](https://jack-200.github.io/cmpe-285-stock-portfolio-engine-test/)  
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
- **Tools & Management**: uv, Antigravity AI, VS Code, GitHub

## Getting Started

1. Start the application: `uv run main.py`
2. Access the dashboard: `http://localhost:8000`
