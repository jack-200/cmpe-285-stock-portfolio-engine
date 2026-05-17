"""
This file handles saving and loading previous portfolio runs.
It reads from and writes to a simple 'history.json' file on your local drive
to act as our lightweight database.
"""

import os
import json
import datetime
import app.config


def save_to_history(portfolio_data: dict):
    """Saves a portfolio suggestion to a local JSON file."""
    history = []
    if os.path.exists(app.config.HISTORY_FILE):
        with open(app.config.HISTORY_FILE, "r") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    entry = {"timestamp": datetime.datetime.now().isoformat(), "data": portfolio_data}
    history.insert(0, entry)
    history = history[: app.config.MAX_HISTORY_ENTRIES]

    with open(app.config.HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)


def get_history():
    """Retrieves the last 10 portfolio suggestions."""
    if not os.path.exists(app.config.HISTORY_FILE):
        return []
    with open(app.config.HISTORY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []
