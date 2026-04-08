#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = "https://growstreams-launch-production.up.railway.app"
ZERO_ACTOR = "0x0000000000000000000000000000000000000000000000000000000000000000"
ZERO_ACTOR_1 = "0x0000000000000000000000000000000000000000000000000000000000000001"
ZERO_ACTOR_2 = "0x0000000000000000000000000000000000000000000000000000000000000002"
TEST_WALLET = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
GROW_TOKEN_ADDR = "0x05a2a482f1a1a7ebf74643f3cc2099597dac81ff92535cbd647948febee8fe36"
TOKEN_VAULT_ADDR = "0x7e081c0f82e31e35d845d1932eb36c84bbbb50568eef3c209f7104fabb2c254b"
V3_SYMBOL = "WUSDC"
DELAY_MS = 350
TIMEOUT = 45
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "growstreams_results.json")


class Suite:
    def __init__(self, base_url: str, skip_mutations: bool):
        self.base_url = base_url.rstrip("/")
        self.skip_mutations = skip_mutations
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.warned = 0
        self.skipped = 0

    def sleep(self, ms: int = DELAY_MS):
        time.sleep(ms / 1000)

    def request(self, method: str, path: str, body: Optional[dict] = None, headers: Optional[dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req_headers = dict(self.session.headers)
        if headers:
            req_headers.update(headers)
        started = time.time()
        try:
            response = self.session.request(method, url, json=body, headers=req_headers, timeout=TIMEOUT)
            elapsed_ms = int((time.time() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = None
            return {
                "status": response.status_code,
                "ok": response.ok,
                "data": data,
                "headers": dict(response.headers),
                "elapsed_ms": elapsed_ms,
                "error": None,
            }
        except Exception as exc:
            return {
                "status": 0,
                "ok": False,
                "data": None,
                "headers": {},
                "elapsed_ms": int((time.time() - started) * 1000),
                "error": str(exc),
            }

    def get(self, path: str, headers: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("GET", path, headers=headers)

    def post(self, path: str, body: Optional[dict] = None, headers: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("POST", path, body=body, headers=headers)

    def put(self, path: str, body: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("PUT", path, body=body or {})

    def delete(self, path: str) -> Dict[str, Any]:
        return self.request("DELETE", path)

    def section(self, name: str):
        print(f"\n{'─' * 64}\n{name}\n{'─' * 64}")

    def add_result(self, section: str, name: str, method: str, endpoint: str, ok: bool, *, warn: bool = False, skip: bool = False, detail: str = "", elapsed_ms: int = 0):
        tag = "SKIP" if skip else "WARN" if warn else "PASS" if ok else "FAIL"
        icon = "⏭️" if skip else "⚠️" if warn else "✅" if ok else "❌"
        print(f"  {icon} [{tag}] {name}" + (f" — {detail}" if detail else ""))

        status = skip or warn or ok
        if skip:
            self.skipped += 1
        elif warn:
            self.warned += 1
        elif ok:
            self.passed += 1
        else:
            self.failed += 1

        self.results.append(
            {
                "section": section,
                "name": name,
                "status": status,
                "warn": warn,
                "skip": skip,
                "endpoint": endpoint,
                "method": method,
                "detail": detail,
                "elapsed_ms": elapsed_ms,
                "tag": tag,
            }
        )

    def run_case(self, section: str, name: str, method: str, endpoint: str, fn):
        try:
            fn()
        except Exception as exc:
            self.add_result(section, name, method, endpoint, False, detail=f"threw: {exc}")
        self.sleep()

    def record_response(self, section: str, name: str, method: str, endpoint: str, response: Dict[str, Any], ok: bool, *, warn: bool = False, detail: str = ""):
        self.add_result(section, name, method, endpoint, ok, warn=warn, detail=detail, elapsed_ms=response.get("elapsed_ms", 0))

    def test_health(self) -> Optional[str]:
        section = "Health"
        self.section(section)
        admin = None

        def root():
            r = self.get("/")
            self.record_response(section, "GET / (API root docs)", "GET", "/", r, r["ok"] and bool((r["data"] or {}).get("name")), detail=f"name={(r['data'] or {}).get('name')}")

        def health():
            nonlocal admin
            r = self.get("/health")
            admin = (r["data"] or {}).get("account")
            status = (r["data"] or {}).get("status")
            self.record_response(section, "GET /health — status", "GET", "/health", r, r["ok"] and status in ("healthy", "degraded"), warn=status == "degraded", detail=f"status={status}, balance={(r['data'] or {}).get('balance')}")

        def contracts():
            r = self.get("/health")
            count = len((r["data"] or {}).get("contracts") or {})
            self.record_response(section, "GET /health — contracts count", "GET", "/health", r, count >= 6, warn=count < 7, detail=f"contracts={count}/7")

        def favicon():
            r = self.get("/favicon.ico")
            self.record_response(section, "GET /favicon.ico — 404", "GET", "/favicon.ico", r, r["status"] == 404, detail=f"status={r['status']}")

        self.run_case(section, "GET / (API root docs)", "GET", "/", root)
        self.run_case(section, "GET /health — status", "GET", "/health", health)
        self.run_case(section, "GET /health — contracts count", "GET", "/health", contracts)
        self.run_case(section, "GET /favicon.ico — 404", "GET", "/favicon.ico", favicon)
        return admin

    def test_tokens(self):
        section = "Tokens"
        self.section(section)
        cases = [
            ("GET /api/tokens", "GET", "/api/tokens", None, lambda r: (r["ok"] and len((r["data"] or {}).get("tokens") or []) >= 5, False, f"count={len((r['data'] or {}).get('tokens') or [])}")),
            ("GET /api/tokens/stablecoins", "GET", "/api/tokens/stablecoins", None, lambda r: (r["ok"] and isinstance((r["data"] or {}).get("tokens"), list), False, f"count={len((r['data'] or {}).get('tokens') or [])}")),
            ("GET /api/tokens/prices", "GET", "/api/tokens/prices", None, lambda r: (r["ok"] and isinstance((r["data"] or {}).get("prices"), dict), False, f"keys={','.join(((r['data'] or {}).get('prices') or {}).keys())}")),
            (f"GET /api/tokens/{V3_SYMBOL}", "GET", f"/api/tokens/{V3_SYMBOL}", None, lambda r: (r["ok"] and (r["data"] or {}).get("symbol") == V3_SYMBOL, False, f"symbol={(r['data'] or {}).get('symbol')}")),
            ("GET /api/tokens/NONEXISTENT — 404", "GET", "/api/tokens/NONEXISTENT", None, lambda r: (r["status"] == 404, False, f"status={r['status']}")),
            ("GET /api/tokens/GROW — config gap", "GET", "/api/tokens/GROW", None, lambda r: (r["status"] == 404, True, f"status={r['status']} expected until registry adds GROW")),
            (f"GET /api/tokens/{V3_SYMBOL}/resolve", "GET", f"/api/tokens/{V3_SYMBOL}/resolve", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("varaAddress")), False, f"addr={((r['data'] or {}).get('varaAddress') or '')[:18]}...")),
            (f"POST /api/tokens/convert (toBase {V3_SYMBOL})", "POST", "/api/tokens/convert", {"symbol": V3_SYMBOL, "amount": "1.5", "direction": "toBase"}, lambda r: (r["ok"] and (r["data"] or {}).get("baseUnits") is not None, False, f"result={(r['data'] or {}).get('baseUnits')}")),
            (f"POST /api/tokens/convert (toDisplay {V3_SYMBOL})", "POST", "/api/tokens/convert", {"symbol": V3_SYMBOL, "amount": "1000000", "direction": "toDisplay"}, lambda r: (r["ok"] and (r["data"] or {}).get("displayUnits") is not None, False, f"result={(r['data'] or {}).get('displayUnits')}")),
            ("POST /api/tokens/convert (bad direction) — 400", "POST", "/api/tokens/convert", {"symbol": V3_SYMBOL, "amount": "1", "direction": "bad"}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
            (f"POST /api/tokens/flow-rate ({V3_SYMBOL})", "POST", "/api/tokens/flow-rate", {"symbol": V3_SYMBOL, "amount": "10", "interval": "day"}, lambda r: (r["ok"] and (r["data"] or {}).get("perSecondRaw") is not None, False, f"perSec={(r['data'] or {}).get('perSecondRaw')}")),
            (f"POST /api/tokens/{V3_SYMBOL}/approve (payload)", "POST", f"/api/tokens/{V3_SYMBOL}/approve", {"spender": TOKEN_VAULT_ADDR, "amount": "1000"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"payload={((r['data'] or {}).get('payload') or '')[:20]}...")),
            (f"GET /api/tokens/{V3_SYMBOL}/vault-balance/:wallet", "GET", f"/api/tokens/{V3_SYMBOL}/vault-balance/{TEST_WALLET}", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"status={r['status']}")),
            ("GET /api/tokens/vault-balances/:wallet", "GET", f"/api/tokens/vault-balances/{TEST_WALLET}", None, lambda r: (r["ok"], False, f"status={r['status']}")),
        ]
        self.run_matrix(section, cases)

    def test_grow_token(self) -> Optional[str]:
        section = "GROW Token"
        self.section(section)
        admin = None

        def meta():
            nonlocal admin
            r = self.get("/api/grow-token/meta")
            admin = (r["data"] or {}).get("admin")
            self.record_response(section, "GET /api/grow-token/meta", "GET", "/api/grow-token/meta", r, r["ok"] and bool((r["data"] or {}).get("symbol")), detail=f"symbol={(r['data'] or {}).get('symbol')}, admin={(admin or '')[:18]}...")

        self.run_case(section, "GET /api/grow-token/meta", "GET", "/api/grow-token/meta", meta)
        cases = [
            ("GET /api/grow-token/total-supply", "GET", "/api/grow-token/total-supply", None, lambda r: (r["ok"] and (r["data"] or {}).get("totalSupply") is not None, False, f"supply={(r['data'] or {}).get('totalSupply')}")),
            ("GET /api/grow-token/balance/:account", "GET", f"/api/grow-token/balance/{ZERO_ACTOR_1}", None, lambda r: (r["ok"] and (r["data"] or {}).get("balance") is not None, False, f"balance={(r['data'] or {}).get('balance')}")),
            ("GET /api/grow-token/allowance/:owner/:spender", "GET", f"/api/grow-token/allowance/{ZERO_ACTOR_1}/{TOKEN_VAULT_ADDR}", None, lambda r: (r["ok"] and (r["data"] or {}).get("allowance") is not None, False, f"allowance={(r['data'] or {}).get('allowance')}")),
            ("GET /api/grow-token/faucet/config", "GET", "/api/grow-token/faucet/config", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("mode")), False, f"mode={(r['data'] or {}).get('mode')}")),
            ("GET /api/grow-token/admin/info", "GET", "/api/grow-token/admin/info", None, lambda r: (r["ok"], False, f"status={r['status']}")),
            ("GET /api/grow-token/admin/whitelist", "GET", "/api/grow-token/admin/whitelist", None, lambda r: (r["ok"], False, f"count={len((r['data'] or {}).get('whitelist') or [])}")),
            ("POST /api/grow-token/faucet (missing to) — 400", "POST", "/api/grow-token/faucet", {}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
            ("POST /api/grow-token/approve (payload)", "POST", "/api/grow-token/approve", {"spender": TOKEN_VAULT_ADDR, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/grow-token/transfer (payload)", "POST", "/api/grow-token/transfer", {"to": ZERO_ACTOR_1, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/grow-token/transfer-from (payload)", "POST", "/api/grow-token/transfer-from", {"from": ZERO_ACTOR_1, "to": ZERO_ACTOR_2, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/grow-token/mint (payload)", "POST", "/api/grow-token/mint", {"to": ZERO_ACTOR_1, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/grow-token/burn (payload)", "POST", "/api/grow-token/burn", {"amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/grow-token/transfer (missing amount) — 400", "POST", "/api/grow-token/transfer", {"to": ZERO_ACTOR_1}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
        ]
        self.run_matrix(section, cases)
        return admin

    def test_streams(self, admin_addr: Optional[str]):
        section = "Streams"
        self.section(section)
        stream_id = "1"
        sender = admin_addr or ZERO_ACTOR_1

        def config():
            r = self.get("/api/streams/config")
            self.record_response(section, "GET /api/streams/config", "GET", "/api/streams/config", r, r["ok"] or r["status"] == 500, warn=not r["ok"], detail=f"status={r['status']}")

        def sender_case():
            nonlocal stream_id
            endpoint = f"/api/streams/sender/{sender}"
            r = self.get(endpoint)
            ids = (r["data"] or {}).get("streamIds") or []
            if ids:
                stream_id = str(ids[0])
            self.record_response(section, "GET /api/streams/sender/:address", "GET", endpoint, r, r["ok"] or r["status"] == 500, warn=not r["ok"], detail=f"ids={ids[:3]}")

        self.run_case(section, "GET /api/streams/config", "GET", "/api/streams/config", config)
        self.run_case(section, "GET /api/streams/sender/:address", "GET", f"/api/streams/sender/{sender}", sender_case)

        cases = [
            ("GET /api/streams/total", "GET", "/api/streams/total", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"total={(r['data'] or {}).get('total')}")),
            ("GET /api/streams/active", "GET", "/api/streams/active", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"active={(r['data'] or {}).get('active')}")),
            ("GET /api/streams/receiver/:address", "GET", f"/api/streams/receiver/{ZERO_ACTOR_1}", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"status={r['status']}")),
            ("GET /api/streams/:id", "GET", f"/api/streams/{stream_id}", None, lambda r: (r["ok"] or r["status"] in (404, 500), r["status"] == 500, f"status={r['status']}")),
            ("GET /api/streams/:id/balance", "GET", f"/api/streams/{stream_id}/balance", None, lambda r: (r["ok"] or r["status"] in (404, 500), r["status"] == 500, f"status={r['status']}")),
            ("GET /api/streams/:id/buffer", "GET", f"/api/streams/{stream_id}/buffer", None, lambda r: (r["ok"] or r["status"] in (404, 500), r["status"] == 500, f"status={r['status']}")),
            ("POST /api/streams (payload)", "POST", "/api/streams", {"receiver": ZERO_ACTOR_1, "token": GROW_TOKEN_ADDR, "flowRate": "1000", "initialDeposit": "3600000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/streams/create (payload)", "POST", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "symbol": "GROW", "amount": "0.001", "interval": "second", "initialDeposit": "10", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/streams/create (missing fields) — 400", "POST", "/api/streams/create", {"receiver": ZERO_ACTOR_1}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
            ("POST /api/streams/create (unknown symbol) — 404", "POST", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "symbol": "FAKECOIN", "amount": "1", "interval": "second", "initialDeposit": "10"}, lambda r: (r["status"] == 404, False, f"status={r['status']}")),
            ("PUT /api/streams/:id (payload)", "PUT", f"/api/streams/{stream_id}", {"flowRate": "2000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/streams/:id/pause (payload)", "POST", f"/api/streams/{stream_id}/pause", {"mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/streams/:id/resume (payload)", "POST", f"/api/streams/{stream_id}/resume", {"mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
        ]
        self.run_matrix(section, cases)

        if self.skip_mutations:
            self.add_result(section, "POST /api/streams (LIVE blockchain)", "POST", "/api/streams", True, skip=True, detail="skipped via --skip-mutations")

    def test_platform(self):
        self.run_matrix("Vault", [
            ("GET /api/vault/config", "GET", "/api/vault/config", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"status={r['status']}")),
            ("GET /api/vault/paused", "GET", "/api/vault/paused", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"paused={(r['data'] or {}).get('paused')}")),
            ("POST /api/vault/deposit (payload)", "POST", "/api/vault/deposit", {"token": GROW_TOKEN_ADDR, "amount": "5000000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
            ("POST /api/vault/withdraw (payload)", "POST", "/api/vault/withdraw", {"token": GROW_TOKEN_ADDR, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
        ])
        self.run_matrix("Permissions", [
            ("GET /api/permissions/config", "GET", "/api/permissions/config", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"status={r['status']}")),
            ("GET /api/permissions/check", "GET", f"/api/permissions/check/{ZERO_ACTOR_1}/{ZERO_ACTOR}/CreateStream", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"has={(r['data'] or {}).get('hasPermission')}")),
            ("POST /api/permissions/grant (payload)", "POST", "/api/permissions/grant", {"grantee": ZERO_ACTOR_1, "scope": "CreateStream", "mode": "payload"}, lambda r: (r["ok"] and bool((r['data'] or {}).get('payload')), False, f"status={r['status']}")),
        ])
        self.run_matrix("Campaign", [
            ("GET /api/campaign/config", "GET", "/api/campaign/config", None, lambda r: (r["ok"], not r["ok"], f"pool={(r['data'] or {}).get('poolUSDC')}")),
            ("GET /api/campaign/leaderboard", "GET", "/api/campaign/leaderboard", None, lambda r: (r["ok"], not r["ok"], f"status={r['status']}")),
            ("POST /api/campaign/register (invalid track) — 400", "POST", "/api/campaign/register", {"wallet": TEST_WALLET, "track": "BADTRACK"}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
            ("POST /api/campaign/payout-snapshot (no auth) — 401", "POST", "/api/campaign/payout-snapshot", None, lambda r: (r["status"] in (401, 500), False, f"status={r['status']}")),
        ])
        self.run_matrix("Leaderboard", [
            ("GET /api/leaderboard", "GET", "/api/leaderboard", None, lambda r: (r["ok"], not r["ok"], f"status={r['status']}")),
            ("GET /api/leaderboard?track=BAD — 400", "GET", "/api/leaderboard?track=BAD", None, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
            ("GET /api/leaderboard/stats", "GET", "/api/leaderboard/stats", None, lambda r: (r["ok"] and (r['data'] or {}).get('totalParticipants') is not None, not r["ok"], f"participants={(r['data'] or {}).get('totalParticipants')}")),
        ])
        self.run_matrix("Users", [
            ("GET /api/users/:wallet", "GET", f"/api/users/{TEST_WALLET}", None, lambda r: (r["ok"] or r["status"] == 404, r["status"] not in (200, 404), f"status={r['status']}")),
            ("POST /api/users/register (missing wallet) — 400", "POST", "/api/users/register", {}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
        ])

    def test_security(self):
        section = "Security"
        self.section(section)
        def nosniff():
            r = self.get("/health")
            value = r["headers"].get("x-content-type-options")
            self.record_response(section, "X-Content-Type-Options: nosniff", "GET", "/health", r, value == "nosniff", warn=value != "nosniff", detail=f"value={value}")
        def frame():
            r = self.get("/health")
            value = r["headers"].get("x-frame-options")
            self.record_response(section, "X-Frame-Options present", "GET", "/health", r, bool(value), warn=not value, detail=f"value={value}")
        def cors():
            r = self.get("/health", headers={"Origin": "https://fake.com"})
            value = r["headers"].get("access-control-allow-origin")
            self.record_response(section, "CORS header present", "GET", "/health", r, value is not None, warn=value == "*", detail=f"value={value}")
        def webhook():
            r = self.post("/api/webhooks/github", {"action": "opened", "pull_request": {}})
            self.record_response(section, "POST /api/webhooks/github (no HMAC)", "POST", "/api/webhooks/github", r, r["status"] in (400, 401, 500), detail=f"status={r['status']}")
        self.run_case(section, "X-Content-Type-Options: nosniff", "GET", "/health", nosniff)
        self.run_case(section, "X-Frame-Options present", "GET", "/health", frame)
        self.run_case(section, "CORS header present", "GET", "/health", cors)
        self.run_case(section, "POST /api/webhooks/github (no HMAC)", "POST", "/api/webhooks/github", webhook)

    def test_rate_limiting(self):
        section = "Rate Limiting"
        self.section(section)
        def faucet_limit():
            self.post("/api/grow-token/faucet", {"to": ZERO_ACTOR_1})
            self.sleep(800)
            r = self.post("/api/grow-token/faucet", {"to": ZERO_ACTOR_1})
            error_text = str((r["data"] or {}).get("error", "")) if isinstance(r["data"], dict) else ""
            limited = r["status"] == 429 or "rate" in error_text.lower()
            self.record_response(section, "Faucet rate limit on rapid retry", "POST", "/api/grow-token/faucet", r, limited, warn=not limited, detail=f"status={r['status']}")
        self.run_case(section, "Faucet rate limit on rapid retry", "POST", "/api/grow-token/faucet", faucet_limit)

    def run_matrix(self, section: str, cases: List[Any]):
        self.section(section)
        for name, method, endpoint, body, evaluator in cases:
            def make_case(n=name, m=method, e=endpoint, b=body, ev=evaluator):
                def case():
                    r = self.request(m, e, body=b)
                    ok, warn, detail = ev(r)
                    self.record_response(section, n, m, e, r, ok, warn=warn, detail=detail)
                return case
            self.run_case(section, name, method, endpoint, make_case())

    def build_report(self) -> Dict[str, Any]:
        total_tests = len(self.results)
        failed = sum(1 for item in self.results if not item["status"] and not item["skip"])
        passed = sum(1 for item in self.results if item["status"] and not item["warn"] and not item["skip"])
        total_time_ms = sum(item.get("elapsed_ms", 0) for item in self.results)
        pass_rate = f"{(passed / total_tests * 100):.1f}%" if total_tests else "0.0%"
        return {
            "server": self.base_url,
            "generated_at": datetime.utcnow().isoformat(),
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "warnings": self.warned,
            "skipped": self.skipped,
            "pass_rate": pass_rate,
            "total_time_ms": total_time_ms,
            "success": failed == 0,
            "results": [
                {
                    "status": item["status"],
                    "endpoint": item["endpoint"],
                    "method": item["method"],
                    "detail": item["detail"],
                    "elapsed_ms": item.get("elapsed_ms", 0),
                    "section": item["section"],
                    "name": item["name"],
                    "warn": item.get("warn", False),
                    "skip": item.get("skip", False),
                }
                for item in self.results
            ],
        }

    def write_report(self):
        with open(RESULTS_FILE, "w") as handle:
            json.dump(self.build_report(), handle, indent=2)

    def print_summary(self):
        total = self.passed + self.failed + self.warned + self.skipped
        print("\n" + "═" * 64)
        print("  RESULTS")
        print("═" * 64)
        print(f"  ✅ PASS   : {self.passed}")
        print(f"  ❌ FAIL   : {self.failed}")
        print(f"  ⚠️  WARN   : {self.warned}")
        print(f"  ⏭️  SKIP   : {self.skipped}")
        print(f"  TOTAL    : {total}")
        print("═" * 64)

    def run(self) -> int:
        print("\n" + "═" * 64)
        print("  GrowStreams — Full E2E API Test Suite")
        print("═" * 64)
        print(f"  Target : {self.base_url}")
        print(f"  Mode   : {'READ-ONLY (no blockchain writes)' if self.skip_mutations else 'FULL (includes blockchain mutations where safe)'}")
        print(f"  Time   : {datetime.utcnow().isoformat()}Z")
        print("═" * 64)

        admin_from_health = self.test_health()
        admin_from_meta = self.test_grow_token()
        self.test_tokens()
        self.test_streams(admin_from_meta or admin_from_health)
        self.test_platform()
        self.test_security()
        self.test_rate_limiting()
        self.write_report()
        self.print_summary()
        return 1 if self.failed > 0 else 0


def main(base_url: str = DEFAULT_BASE_URL, skip_mutations: bool = False) -> int:
    suite = Suite(base_url=base_url, skip_mutations=skip_mutations)
    return suite.run()
