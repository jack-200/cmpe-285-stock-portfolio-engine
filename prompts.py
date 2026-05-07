"""Versioned LLM prompts — bump PROMPT_VERSION when behavior changes."""

import json

PROMPT_VERSION = "2026.05.06-2"


def rationale_system_message() -> str:
    return (
        "You explain portfolio construction for a classroom demo. "
        "Reply with a single JSON object and no other text."
    )


def rationale_user_message(
    symbols: list[str],
    selected_strategies: list[str],
    lines: list[str],
) -> str:
    return (
        f"Selected investment strategy labels: {', '.join(selected_strategies)}\n\n"
        f"Portfolio symbols and names:\n{chr(10).join(lines)}\n\n"
        "For each symbol, write exactly one concise sentence (max 35 words) explaining "
        "why that holding illustrates the selected strategy or strategies. "
        "Educational tone only; do not recommend buying or selling.\n\n"
        f"Return only a JSON object whose keys are exactly: {json.dumps(symbols)} "
        "and whose values are strings (the sentences)."
    )


def rationale_json_repair_user_message(symbols: list[str], broken_output: str) -> str:
    sym_json = json.dumps(symbols)
    clipped = broken_output[:3500]
    return (
        "Your previous reply was not valid JSON or was missing keys. "
        f"Return ONLY a valid JSON object with exactly these keys: {sym_json}. "
        "Each value must be one concise sentence string. No markdown fences.\n\n"
        f"Broken output to fix:\n{clipped}"
    )


def chat_system_prompt(strategies_blob: str, ctx_blob: str) -> str:
    return (
        "You are InvestIQ Assistant for the Stock Portfolio Suggestion Engine (educational demo).\n"
        "You explain how the app works, what the five strategies mean, and how allocations are split.\n"
        "Strategy names map to fixed ticker lists (JSON below). The UI loads live prices via yfinance.\n"
        "Minimum investment in the app is $5000; users pick 1–2 strategies.\n"
        "Do not give personalized buy/sell recommendations or predict returns. "
        "If asked for advice, give general education only.\n"
        "Format replies with Markdown when it helps readability: short headings (##), **bold** key terms, "
        "and numbered or bulleted lists. Keep paragraphs concise.\n\n"
        f"Strategy → tickers:\n{strategies_blob}"
        f"{ctx_blob}"
    )
