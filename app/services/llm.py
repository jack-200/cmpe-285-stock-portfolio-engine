"""
This service manages our AI logic.
It connects to either a local Ollama instance or cloud OpenAI
to generate rationale text ("Why this pick?") and power the InvestIQ chat.
"""

import os
import json
import re
import typing
import openai
import app.prompts
import app.config
import app.schemas


def openai_client_and_model(
    kind: app.schemas.LLMKind,
) -> typing.Optional[typing.Tuple[typing.Any, str]]:
    """Return (OpenAI client, model_id), or None if LLM is disabled."""
    resolved = resolve_llm_endpoint(kind)
    if not resolved:
        return None
    api_key, base_url, model, timeout_s = resolved
    client_kw: typing.Dict[str, typing.Any] = {
        "api_key": api_key,
        "timeout": timeout_s,
    }
    if base_url:
        client_kw["base_url"] = base_url
    return openai.OpenAI(**client_kw), model


def _ollama_openai_base_url(host: str) -> str:
    h = host.strip().rstrip("/")
    if h.endswith("/v1"):
        return h
    return f"{h}/v1"


def resolve_llm_endpoint(
    kind: app.schemas.LLMKind,
) -> typing.Optional[typing.Tuple[str, typing.Optional[str], str, float]]:
    """Return (api_key, base_url_or_none, model_id, timeout_seconds), or None if LLM disabled."""
    raw = (
        (os.environ.get("LLM_BACKEND") or app.config.DEFAULT_LLM_BACKEND)
        .strip()
        .lower()
    )
    if raw in ("none", "off", "0", "false", "disabled"):
        return None

    timeout_r = float(
        os.environ.get(
            "LLM_TIMEOUT_RATIONALES_S", str(app.config.DEFAULT_TIMEOUT_RATIONALES_S)
        )
    )
    timeout_c = float(
        os.environ.get("LLM_TIMEOUT_CHAT_S", str(app.config.DEFAULT_TIMEOUT_CHAT_S))
    )
    timeout_s = timeout_r if kind == "rationale" else timeout_c

    if raw in ("ollama", "local"):
        host = (
            os.environ.get("OLLAMA_HOST", app.config.DEFAULT_OLLAMA_HOST).strip()
            or app.config.DEFAULT_OLLAMA_HOST
        )
        base = _ollama_openai_base_url(host)
        if kind == "rationale":
            model = (
                os.environ.get("LLM_MODEL_RATIONALES")
                or os.environ.get("LLM_MODEL")
                or app.config.DEFAULT_OLLAMA_MODEL
            ).strip() or app.config.DEFAULT_OLLAMA_MODEL
        else:
            model = (
                os.environ.get("LLM_MODEL_CHAT")
                or os.environ.get("LLM_MODEL")
                or app.config.DEFAULT_OLLAMA_MODEL
            ).strip() or app.config.DEFAULT_OLLAMA_MODEL
        key = (
            os.environ.get("OPENAI_API_KEY", app.config.OLLAMA_DUMMY_API_KEY).strip()
            or app.config.OLLAMA_DUMMY_API_KEY
        )
        return (key, base, model, timeout_s)

    if raw == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
        if kind == "rationale":
            model = (
                os.environ.get("LLM_MODEL_RATIONALES")
                or os.environ.get("LLM_MODEL")
                or app.config.DEFAULT_OPENAI_MODEL
            ).strip() or app.config.DEFAULT_OPENAI_MODEL
        else:
            model = (
                os.environ.get("LLM_MODEL_CHAT")
                or os.environ.get("LLM_MODEL")
                or app.config.DEFAULT_OPENAI_MODEL
            ).strip() or app.config.DEFAULT_OPENAI_MODEL
        return (key, base, model, timeout_s)

    return None


def llm_rationales_configured() -> bool:
    return resolve_llm_endpoint("rationale") is not None


def _parse_json_object_from_llm(text: str) -> typing.Dict[str, typing.Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw)
    return json.loads(raw)


def _rationale_map_from_llm_text(
    content: str, symbols: typing.List[str]
) -> typing.Dict[str, str]:
    parsed = _parse_json_object_from_llm(content)
    out: typing.Dict[str, str] = {}
    for sym in symbols:
        val = parsed.get(sym)
        if isinstance(val, str) and val.strip():
            out[sym] = val.strip()
    return out


def fetch_selection_rationales_llm(
    symbols: typing.List[str],
    selected_strategies: typing.List[str],
    names_by_symbol: typing.Dict[str, str],
) -> typing.Dict[str, str]:
    """One batched call; keys must match symbols. Uses Ollama (default) or OpenAI-compatible APIs."""
    cm = openai_client_and_model("rationale")
    if not cm:
        return {}
    client, model = cm

    lines = [f"- {sym} ({names_by_symbol.get(sym, sym)})" for sym in symbols]
    user_msg = app.prompts.rationale_user_message(symbols, selected_strategies, lines)

    params: typing.Dict[str, typing.Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": app.prompts.rationale_system_message()},
            {"role": "user", "content": user_msg},
        ],
        "temperature": app.config.LLM_RATIONALE_TEMPERATURE,
    }

    content = ""
    try:
        completion = client.chat.completions.create(
            **params, response_format={"type": "json_object"}
        )
        content = (completion.choices[0].message.content or "").strip()
    except Exception:
        try:
            completion = client.chat.completions.create(**params)
            content = (completion.choices[0].message.content or "").strip()
        except Exception:
            return {}

    out: typing.Dict[str, str] = {}
    try:
        out = _rationale_map_from_llm_text(content, symbols)
    except (json.JSONDecodeError, TypeError, ValueError):
        out = {}

    if len(out) >= len(symbols):
        return out

    try:
        repair_msg = app.prompts.rationale_json_repair_user_message(symbols, content)
        completion2 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": app.prompts.rationale_system_message()},
                {"role": "user", "content": repair_msg},
            ],
            temperature=app.config.LLM_REPAIR_TEMPERATURE,
        )
        content2 = (completion2.choices[0].message.content or "").strip()
        out = _rationale_map_from_llm_text(content2, symbols)
    except Exception:
        pass

    return out


def fallback_selection_rationale_for_symbol(
    symbol: str, selected_strategies: typing.List[str]
) -> str:
    """Static fallback when LLM output is missing."""
    parts: typing.List[str] = []
    seen: typing.Set[str] = set()
    for strategy in selected_strategies:
        blurb = app.config.STOCK_SELECTION_RATIONALE.get(strategy, {}).get(symbol)
        if blurb and blurb not in seen:
            seen.add(blurb)
            parts.append(blurb)
    return " ".join(parts)


def build_selection_rationales(
    symbols: typing.List[str],
    selected_strategies: typing.List[str],
    names_by_symbol: typing.Dict[str, str],
) -> typing.Tuple[typing.Dict[str, str], typing.Dict[str, app.schemas.RationaleSource]]:
    llm_part: typing.Dict[str, str] = {}
    if llm_rationales_configured():
        try:
            llm_part = fetch_selection_rationales_llm(
                symbols, selected_strategies, names_by_symbol
            )
        except Exception:
            llm_part = {}

    merged: typing.Dict[str, str] = {}
    sources: typing.Dict[str, app.schemas.RationaleSource] = {}
    for sym in symbols:
        text = llm_part.get(sym, "").strip()
        if text:
            merged[sym] = text
            sources[sym] = "llm"
        else:
            merged[sym] = fallback_selection_rationale_for_symbol(
                sym, selected_strategies
            )
            sources[sym] = "fallback"
    return merged, sources


def rationale_origin_from_sources(
    sources: typing.Dict[str, app.schemas.RationaleSource],
) -> app.schemas.RationaleOrigin:
    vals = [sources[s] for s in sorted(sources)]
    if not vals:
        return "fallback"
    llm_n = sum(1 for v in vals if v == "llm")
    if llm_n == len(vals):
        return "all_llm"
    if llm_n > 0:
        return "partial_llm"
    return "fallback"


def active_llm_meta() -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
    """(backend_label, model_id) when LLM path is enabled, else (None, None)."""
    resolved = resolve_llm_endpoint("rationale")
    if not resolved:
        return None, None
    _key, _base, model, _timeout = resolved
    raw = (
        (os.environ.get("LLM_BACKEND") or app.config.DEFAULT_LLM_BACKEND)
        .strip()
        .lower()
    )
    if raw in ("ollama", "local"):
        return "ollama", model
    if raw == "openai":
        return "openai", model
    return None, model


def _chat_system_and_messages(
    request: app.schemas.ChatRequest,
) -> typing.Tuple[str, typing.List[typing.Dict[str, str]]]:
    strategies_blob = json.dumps(app.config.STRATEGIES, indent=2)
    ctx_blob = ""
    if request.portfolio_context is not None:
        ctx_blob = (
            "\n\nOptional snapshot of the user’s latest portfolio result in the UI:\n"
            + request.portfolio_context.model_dump_json(indent=2)
        )
    system_prompt = app.prompts.chat_system_prompt(strategies_blob, ctx_blob)
    api_messages: typing.List[typing.Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    for msg in request.messages:
        api_messages.append({"role": msg.role, "content": msg.content})
    return system_prompt, api_messages


def chat_reply(request: app.schemas.ChatRequest) -> app.schemas.ChatResponse:
    """Assistant for strategies, app behavior, and optional last-portfolio snapshot."""
    cm = openai_client_and_model("chat")
    if not cm:
        return app.schemas.ChatResponse(
            reply=(
                "Chat needs an LLM. Configure LLM_BACKEND (ollama or openai) and run "
                "./scripts/setup-local-llm.sh or set OPENAI_API_KEY — see .env.example."
            ),
            llm_available=False,
            ok=False,
        )

    client, model = cm
    _, api_messages = _chat_system_and_messages(request)

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=app.config.CHAT_TEMPERATURE,
        )
        text = completion.choices[0].message.content
        reply = (text or "").strip()
        if not reply:
            reply = "(Empty response from model.)"
        return app.schemas.ChatResponse(reply=reply, llm_available=True, ok=True)
    except Exception as e:
        return app.schemas.ChatResponse(
            reply=f"Model error: {str(e)[:400]}",
            llm_available=True,
            ok=False,
        )


def chat_reply_stream(body: app.schemas.ChatRequest) -> typing.Iterator[str]:
    """SSE chunks: `data: {"t":"..."}\\n\\n` or errors / `[DONE]`."""
    cm = openai_client_and_model("chat")
    if not cm:
        yield f"data: {json.dumps({'error': 'no_llm'})}\n\n"
        return

    client, model = cm
    _, api_messages = _chat_system_and_messages(body)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=app.config.CHAT_TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'t': delta})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': 'stream', 'message': str(e)[:400]})}\n\n"
