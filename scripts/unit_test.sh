#!/usr/bin/env bash
# Automated runner for the 10 grader test cases in grader-test-cases-email.txt.
#
# Usage:
#   ./scripts/unit_test.sh              # auto-starts the server, runs tests, stops it
#   ./scripts/unit_test.sh --no-start   # assumes the server is already on $BASE_URL
#   ./scripts/unit_test.sh --help
#
# Env overrides:
#   BASE_URL  default http://127.0.0.1:8000
#
# Requires: curl, python3. The .venv must already exist (run ./scripts/start.sh
# once first if it does not — that installs requirements.txt into .venv).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
NO_START=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start) NO_START=true; shift;;
    -h|--help)
      sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
      exit 0;;
    *) echo "unknown flag: $1" >&2; exit 2;;
  esac
done

# ---------- pretty output ----------
if [[ -t 1 ]]; then
  G="\033[32m"; R="\033[31m"; Y="\033[33m"; B="\033[36m"; N="\033[0m"
else
  G=""; R=""; Y=""; B=""; N=""
fi
log()  { printf "%b\n" "$*"; }
hdr()  { log "\n${B}== $1 ==${N}"; }

PASS=0
FAIL=0
FAILED=()
pass() { PASS=$((PASS+1)); log "  ${G}PASS${N} $1"; }
fail() { FAIL=$((FAIL+1)); FAILED+=("$1"); log "  ${R}FAIL${N} $1 — $2"; }

command -v curl    >/dev/null 2>&1 || { log "${R}error: curl not found${N}";    exit 2; }
command -v python3 >/dev/null 2>&1 || { log "${R}error: python3 not found${N}"; exit 2; }

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t uts)"
BODY="$TMP/body.json"
ERR="$TMP/err.log"

# ---------- server bring-up ----------
SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    log "\nStopping server (pid=$SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start_server() {
  if curl -sf "$BASE_URL/api/health" >/dev/null 2>&1; then
    log "${Y}Server already responding at $BASE_URL — reusing.${N}"
    return 0
  fi
  if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    log "${R}No usable virtualenv at .venv/bin/python.${N}"
    log "Run ${B}./scripts/start.sh${N} once to provision .venv, then re-run this script,"
    log "or pass ${B}--no-start${N} after starting the server yourself."
    return 1
  fi
  log "Starting server: $ROOT/.venv/bin/python -m app.main"
  ( "$ROOT/.venv/bin/python" -m app.main >"$TMP/server.log" 2>&1 ) &
  SERVER_PID=$!
  log "Waiting for $BASE_URL/api/health (up to 60s) ..."
  for i in $(seq 1 60); do
    if curl -sf "$BASE_URL/api/health" >/dev/null 2>&1; then
      log "${G}Server up after ${i}s${N}"
      return 0
    fi
    sleep 1
  done
  log "${R}Server did not respond within 60s. Server log:${N}"
  tail -n 40 "$TMP/server.log" 2>/dev/null || true
  return 1
}

if [[ "$NO_START" == "false" ]]; then
  start_server || exit 1
else
  curl -sf "$BASE_URL/api/health" >/dev/null 2>&1 || {
    log "${R}--no-start was passed but $BASE_URL/api/health is not responding.${N}"
    exit 1
  }
fi

# ---------- helpers ----------
# Run a POST against /api/suggest with a JSON body; writes body to $BODY,
# echoes the HTTP status code on stdout.
post_suggest() {
  curl -sS -o "$BODY" -w "%{http_code}" -X POST "$BASE_URL/api/suggest" \
       -H "Content-Type: application/json" -d "$1" 2> "$ERR"
}
# Run a GET; same convention.
get_path() {
  curl -sS -o "$BODY" -w "%{http_code}" "$BASE_URL$1" 2> "$ERR"
}
# Parse a JSON file with a tiny inline Python snippet.
pyq() { python3 -c "$1" "$BODY"; }

# ================================================================
# Tests
# ================================================================

# TC-01: static UI served
hdr "TC-01 — Static UI served at /"
code=$(get_path /)
if [[ "$code" == "200" ]] && grep -qiE "InvestIQ|Stock Portfolio" "$BODY"; then
  pass "GET / returned 200 and HTML mentions InvestIQ / Stock Portfolio"
else
  fail "TC-01" "code=$code (first 120 chars: $(head -c 120 "$BODY"))"
fi

# TC-02: /api/health
hdr "TC-02 — /api/health"
code=$(get_path /api/health)
if [[ "$code" == "200" ]]; then
  ok=$(pyq 'import json,sys; print(json.load(open(sys.argv[1])).get("ok"))')
  pv=$(pyq 'import json,sys; print(json.load(open(sys.argv[1])).get("prompt_version",""))')
  if [[ "$ok" == "True" && -n "$pv" ]]; then
    pass "ok=True prompt_version=$pv"
  else
    fail "TC-02" "ok=$ok prompt_version=$pv"
  fi
else
  fail "TC-02" "GET /api/health -> $code"
fi

# TC-03: happy path 5000 + Index Investing
hdr "TC-03 — Happy path \$5000 + Index Investing + Moderate + 5d"
code=$(post_suggest '{"amount":5000,"strategies":["Index Investing"],"risk_profile":"Moderate","history_period":"5d"}')
if [[ "$code" == "200" ]]; then
  n=$(pyq 'import json,sys; d=json.load(open(sys.argv[1])); print(len(d.get("stocks",[])))')
  syms=$(pyq 'import json,sys; d=json.load(open(sys.argv[1])); print(",".join(s["symbol"] for s in d.get("stocks",[])))')
  totalv=$(pyq 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("total_value",0))')
  has_sectors=$(pyq 'import json,sys; d=json.load(open(sys.argv[1])); print("YES" if d.get("sector_allocations") else "NO")')
  if [[ "$n" -ge 1 && "$has_sectors" == "YES" ]]; then
    pass "stocks=$n ($syms) total=$totalv sector_allocations present"
  else
    fail "TC-03" "stocks=$n has_sectors=$has_sectors"
  fi
else
  fail "TC-03" "expected 200 got $code (body: $(head -c 160 "$BODY"))"
fi

# TC-04: two strategies, allocations sum to amount, no dup symbols
hdr "TC-04 — Two strategies (Growth + Index), allocations sum to amount"
code=$(post_suggest '{"amount":10000,"strategies":["Growth Investing","Index Investing"],"risk_profile":"Moderate","history_period":"5d"}')
if [[ "$code" == "200" ]]; then
  result=$(pyq '
import json,sys
d=json.load(open(sys.argv[1]))
stocks=d.get("stocks",[])
syms=[s["symbol"] for s in stocks]
total_alloc=round(sum(s["allocation_amount"] for s in stocks),2)
print(f"{total_alloc}|{len(syms)}|{len(set(syms))}")
')
  ta="${result%%|*}"; rest="${result#*|}"; nsyms="${rest%%|*}"; nuniq="${rest#*|}"
  if [[ "$nsyms" == "$nuniq" ]] && python3 -c "import sys; sys.exit(0 if 9990 <= $ta <= 10010 else 1)"; then
    pass "alloc sum=$ta, $nsyms unique tickers"
  else
    fail "TC-04" "alloc_sum=$ta n=$nsyms unique=$nuniq"
  fi
else
  fail "TC-04" "expected 200 got $code"
fi

# TC-05: server enforces strategy count (0 and 3 both rejected with 422)
hdr "TC-05 — Server validates strategy count (0 and 3 -> 422)"
code0=$(post_suggest '{"amount":5000,"strategies":[],"risk_profile":"Moderate","history_period":"5d"}')
code3=$(post_suggest '{"amount":5000,"strategies":["Index Investing","Growth Investing","Value Investing"],"risk_profile":"Moderate","history_period":"5d"}')
if [[ "$code0" == "422" && "$code3" == "422" ]]; then
  pass "0 strategies -> 422, 3 strategies -> 422"
else
  fail "TC-05" "0->$code0 3->$code3 (expected 422/422)"
fi

# TC-06: amount below minimum
hdr "TC-06 — Amount below \$5000 minimum rejected"
code=$(post_suggest '{"amount":4999,"strategies":["Index Investing"],"risk_profile":"Moderate","history_period":"5d"}')
if [[ "$code" == "422" ]] && grep -qi "amount" "$BODY"; then
  pass "422 with amount-related detail"
else
  fail "TC-06" "code=$code body=$(head -c 160 "$BODY")"
fi

# TC-07: invalid strategy name
hdr "TC-07 — Invalid strategy name rejected"
code=$(post_suggest '{"amount":5000,"strategies":["Not A Real Strategy"],"risk_profile":"Moderate","history_period":"5d"}')
if [[ "$code" == "400" ]] && grep -qi "Invalid strategy" "$BODY"; then
  pass "400 with 'Invalid strategy' detail"
else
  fail "TC-07" "code=$code body=$(head -c 160 "$BODY")"
fi

# TC-08: risk profile tilts allocations (Conservative vs Aggressive, Index only)
hdr "TC-08 — Risk profile tilts allocations (Conservative vs Aggressive)"
curl -sS -X POST "$BASE_URL/api/suggest" -H "Content-Type: application/json" \
     -d '{"amount":10000,"strategies":["Index Investing"],"risk_profile":"Conservative","history_period":"5d"}' \
     -o "$TMP/c.json" 2>/dev/null
curl -sS -X POST "$BASE_URL/api/suggest" -H "Content-Type: application/json" \
     -d '{"amount":10000,"strategies":["Index Investing"],"risk_profile":"Aggressive","history_period":"5d"}' \
     -o "$TMP/a.json" 2>/dev/null
shift_info=$(python3 - <<'PY' "$TMP/c.json" "$TMP/a.json"
import json, sys
c = json.load(open(sys.argv[1]))
a = json.load(open(sys.argv[2]))
mc = {s["symbol"]: round(s["allocation_amount"], 2) for s in c.get("stocks", [])}
ma = {s["symbol"]: round(s["allocation_amount"], 2) for s in a.get("stocks", [])}
common = sorted(set(mc) & set(ma))
diffs = [(k, mc[k], ma[k]) for k in common if abs(mc[k] - ma[k]) > 1.0]
print(f"{len(diffs)}|{','.join(k for k,_,_ in diffs)}")
PY
)
ndiffs="${shift_info%%|*}"
who="${shift_info#*|}"
if [[ "$ndiffs" -ge 1 ]]; then
  pass "$ndiffs ticker(s) moved >\$1 between profiles: $who"
else
  fail "TC-08" "no meaningful weight shift between Conservative and Aggressive"
fi

# TC-09: trend period toggles return monotonically more points
hdr "TC-09 — Trend period 5d <= 1mo <= 1y by history length"
get_n() {
  curl -sS -X POST "$BASE_URL/api/suggest" -H "Content-Type: application/json" \
       -d "{\"amount\":5000,\"strategies\":[\"Index Investing\"],\"risk_profile\":\"Moderate\",\"history_period\":\"$1\"}" \
    | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('weekly_history',[])))"
}
n5=$(get_n 5d)
n1m=$(get_n 1mo)
n1y=$(get_n 1y)
if [[ "$n5" -ge 1 && "$n1m" -ge "$n5" && "$n1y" -ge "$n1m" ]]; then
  pass "history lengths 5d=$n5 <= 1mo=$n1m <= 1y=$n1y"
else
  fail "TC-09" "lengths 5d=$n5 1mo=$n1m 1y=$n1y are not monotonically non-decreasing"
fi

# TC-10: /api/history persists prior runs and includes sector_allocations
hdr "TC-10 — /api/history persists runs and exposes sector_allocations"
code=$(get_path /api/history)
if [[ "$code" == "200" ]]; then
  n=$(pyq 'import json,sys; print(len(json.load(open(sys.argv[1]))))')
  has=$(pyq 'import json,sys; h=json.load(open(sys.argv[1])); d=(h[0] if h else {}).get("data",{}); print("YES" if "sector_allocations" in d else "NO")')
  if [[ "$n" -ge 1 && "$has" == "YES" ]]; then
    pass "history has $n entries; latest exposes sector_allocations"
  else
    fail "TC-10" "n=$n has_sector=$has"
  fi
else
  fail "TC-10" "GET /api/history -> $code"
fi

# ================================================================
# Summary
# ================================================================
log "\n${B}==========================${N}"
log "Summary: ${G}${PASS} passed${N}, ${R}${FAIL} failed${N}, base=$BASE_URL"
log "${B}==========================${N}"
if [[ $FAIL -ne 0 ]]; then
  log "Failed cases:"
  for t in "${FAILED[@]}"; do log "  - $t"; done
  exit 1
fi
exit 0
