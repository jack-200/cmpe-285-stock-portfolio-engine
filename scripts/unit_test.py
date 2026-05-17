import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"


def log(msg, color=None):
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "bold": "\033[1m",
        "end": "\033[0m",
    }
    if color and color in colors:
        print(f"{colors[color]}{msg}{colors['end']}")
    else:
        print(msg)


def make_request(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"

    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, method=method, data=body_bytes)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            status = response.status
            resp_body = response.read().decode("utf-8")
            return status, resp_body
    except urllib.error.HTTPError as e:
        status = e.code
        resp_body = e.read().decode("utf-8")
        return status, resp_body
    except Exception as e:
        import traceback

        return 0, f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"


def run_tests():
    passes = 0
    fails = 0

    def report(name, condition, code, body, detail=""):
        nonlocal passes, fails
        if condition:
            log(f"  [PASS] {name} - {detail}", "green")
            passes += 1
        else:
            log(
                f"  [FAIL] {name} - HTTP {code}. Detail: {detail}. Response/Error: {body}",
                "red",
            )
            fails += 1

    # TC-01: Static UI Served
    log("\n== TC-01: Static UI served at / ==")
    code, body = make_request("/")
    report(
        "TC-01",
        code == 200 and ("InvestIQ" in body or "Stock Portfolio" in body),
        code,
        body,
        f"Status: {code}",
    )

    # TC-02: Health check
    log("\n== TC-02: /api/health ==")
    code, body = make_request("/api/health")
    ok, pv = False, ""
    if code == 200:
        try:
            d = json.loads(body)
            ok = d.get("ok") is True
            pv = d.get("prompt_version", "")
        except Exception:
            pass
    report(
        "TC-02",
        code == 200 and ok and pv != "",
        code,
        body,
        f"ok={ok}, prompt_version='{pv}'",
    )

    # TC-03: Happy path Index Investing
    log("\n== TC-03: Happy path $5000 + Index Investing ==")
    payload = {
        "amount": 5000,
        "strategies": ["Index Investing"],
        "risk_profile": "Moderate",
        "history_period": "5d",
    }
    code, body = make_request("/api/suggest", "POST", payload)
    valid_suggest = False
    details = ""
    if code == 200:
        try:
            d = json.loads(body)
            stocks = d.get("stocks", [])
            has_sec = len(d.get("sector_allocations", [])) > 0
            alloc_sum = sum(s.get("allocation_amount", 0) for s in stocks)
            valid_suggest = len(stocks) >= 1 and has_sec and abs(alloc_sum - 5000) < 0.1
            details = f"Stocks count: {len(stocks)}, Sector allocs: {has_sec}, Total alloc: ${alloc_sum:.2f}"
        except Exception as e:
            details = str(e)
    else:
        details = f"HTTP {code}. Body/Error: {body}"
    report("TC-03", code == 200 and valid_suggest, code, body, details)

    # TC-04: Two strategies
    log("\n== TC-04: Two strategies (Growth + Index) sum to amount ==")
    payload = {
        "amount": 10000,
        "strategies": ["Growth Investing", "Index Investing"],
        "risk_profile": "Moderate",
        "history_period": "5d",
    }
    code, body = make_request("/api/suggest", "POST", payload)
    valid_tc4 = False
    details = ""
    if code == 200:
        try:
            d = json.loads(body)
            stocks = d.get("stocks", [])
            syms = [s.get("symbol") for s in stocks]
            alloc_sum = sum(s.get("allocation_amount", 0) for s in stocks)
            unique = len(syms) == len(set(syms))
            valid_tc4 = unique and abs(alloc_sum - 10000) < 0.1
            details = f"Allocations sum: ${alloc_sum:.2f}, Unique tickers: {unique} ({', '.join(syms)})"
        except Exception as e:
            details = str(e)
    else:
        details = f"HTTP {code}. Body/Error: {body}"
    report("TC-04", code == 200 and valid_tc4, code, body, details)

    # TC-05: Enforce strategy counts (0 and 3 rejected)
    log("\n== TC-05: Strategy count validations (0 and 3 -> 422) ==")
    c0, b0 = make_request(
        "/api/suggest",
        "POST",
        {
            "amount": 5000,
            "strategies": [],
            "risk_profile": "Moderate",
            "history_period": "5d",
        },
    )
    c3, b3 = make_request(
        "/api/suggest",
        "POST",
        {
            "amount": 5000,
            "strategies": ["Index Investing", "Growth Investing", "Value Investing"],
            "risk_profile": "Moderate",
            "history_period": "5d",
        },
    )
    report(
        "TC-05",
        c0 == 422 and c3 == 422,
        f"{c0}/{c3}",
        f"0 strats: {b0}\n3 strats: {b3}",
        f"0 strats: {c0}, 3 strats: {c3}",
    )

    # TC-06: Amount below minimum
    log("\n== TC-06: Amount below $5000 rejected (-> 422) ==")
    c6, b6 = make_request(
        "/api/suggest",
        "POST",
        {
            "amount": 4999,
            "strategies": ["Index Investing"],
            "risk_profile": "Moderate",
            "history_period": "5d",
        },
    )
    has_amount_msg = "amount" in b6.lower() or "ge" in b6.lower()
    report(
        "TC-06",
        c6 == 422 and has_amount_msg,
        c6,
        b6,
        f"Status: {c6}, Body: {b6.strip()[:100]}",
    )

    # TC-07: Invalid strategy name
    log("\n== TC-07: Invalid strategy name rejected (-> 400) ==")
    c7, b7 = make_request(
        "/api/suggest",
        "POST",
        {
            "amount": 5000,
            "strategies": ["Not A Real Strategy"],
            "risk_profile": "Moderate",
            "history_period": "5d",
        },
    )
    report(
        "TC-07",
        c7 == 400 and "invalid strategy" in b7.lower(),
        c7,
        b7,
        f"Status: {c7}, Body: {b7.strip()[:100]}",
    )

    # TC-08: Risk profile tilts
    log("\n== TC-08: Risk profile tilts allocations (Conservative vs Aggressive) ==")
    c_code, c_body = make_request(
        "/api/suggest",
        "POST",
        {
            "amount": 10000,
            "strategies": ["Index Investing"],
            "risk_profile": "Conservative",
            "history_period": "5d",
        },
    )
    a_code, a_body = make_request(
        "/api/suggest",
        "POST",
        {
            "amount": 10000,
            "strategies": ["Index Investing"],
            "risk_profile": "Aggressive",
            "history_period": "5d",
        },
    )
    shifted = False
    details = ""
    if c_code == 200 and a_code == 200:
        try:
            c_stocks = json.loads(c_body).get("stocks", [])
            a_stocks = json.loads(a_body).get("stocks", [])
            c_map = {s["symbol"]: s["allocation_amount"] for s in c_stocks}
            a_map = {s["symbol"]: s["allocation_amount"] for s in a_stocks}
            diffs = []
            for k in set(c_map) & set(a_map):
                diff = abs(c_map[k] - a_map[k])
                diffs.append(f"{k}: ${c_map[k]:.2f} vs ${a_map[k]:.2f}")
                if diff > 1.0:
                    shifted = True
            details = "; ".join(diffs)
        except Exception as e:
            details = str(e)
    else:
        details = f"HTTP Conservative: {c_code} (Body: {c_body}), Aggressive: {a_code} (Body: {a_body})"
    report(
        "TC-08",
        shifted,
        f"{c_code}/{a_code}",
        f"Conservative: {c_body}\nAggressive: {a_body}",
        details,
    )

    # TC-09: Trend periods
    log("\n== TC-09: Trend periods monotonic lengths (5d <= 1mo <= 1y) ==")

    def get_len(per):
        code, body = make_request(
            "/api/suggest",
            "POST",
            {
                "amount": 5000,
                "strategies": ["Index Investing"],
                "risk_profile": "Moderate",
                "history_period": per,
            },
        )
        if code == 200:
            return len(json.loads(body).get("weekly_history", []))
        return -1

    l5 = get_len("5d")
    lm = get_len("1mo")
    ly = get_len("1y")
    monotonic = l5 >= 1 and lm >= l5 and ly >= lm
    report(
        "TC-09",
        monotonic,
        200 if monotonic else 0,
        f"5d={l5}, 1mo={lm}, 1y={ly}",
        f"Lengths - 5d: {l5}, 1mo: {lm}, 1y: {ly} (Monotonic: {monotonic})",
    )

    # TC-10: History persists prior runs
    log(
        "\n== TC-10: /api/history persists suggestions and exposes sector_allocations =="
    )
    c10, b10 = make_request("/api/history")
    has_hist = False
    details = ""
    if c10 == 200:
        try:
            h = json.loads(b10)
            has_hist = len(h) >= 1
            has_sector = "sector_allocations" in h[0].get("data", {})
            details = f"History length: {len(h)}, Exposes sector allocations in latest: {has_sector}"
            has_hist = has_hist and has_sector
        except Exception as e:
            details = str(e)
    else:
        details = f"HTTP {c10}. Body/Error: {b10}"
    report("TC-10", has_hist, c10, b10, details)

    log("\n==========================", "bold")
    log(f"Passed: {passes} / 10", "green" if passes == 10 else "yellow")
    log(f"Failed: {fails} / 10", "red" if fails > 0 else "green")
    log("==========================\n", "bold")

    return fails == 0


def main():
    log("Spinning up backend server in background: python -m app.main ...", "blue")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    log("Waiting up to 10 seconds for server to be responsive...", "blue")
    server_ok = False
    for i in range(20):
        time.sleep(0.5)
        code, _ = make_request("/api/health")
        if code == 200:
            log(f"Server is alive after {0.5 * (i + 1)} seconds!", "green")
            server_ok = True
            break

    if not server_ok:
        log("Error: Server did not respond. Printing stderr:", "red")
        proc.terminate()
        stdout, stderr = proc.communicate()
        print(stderr.decode("utf-8"))
        sys.exit(1)

    success = False
    try:
        success = run_tests()
    finally:
        log("Shutting down background server...", "blue")
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

        if not success:
            log("\n=== SERVER STDOUT ===", "yellow")
            print(stdout.decode("utf-8"))
            log("=== SERVER STDERR ===", "red")
            print(stderr.decode("utf-8"))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
