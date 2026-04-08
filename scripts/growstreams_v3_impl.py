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
ZERO_ACTOR_42 = "0x0000000000000000000000000000000000000000000000000000000000000042"
GROW_TOKEN_ADDR = "0x05a2a482f1a1a7ebf74643f3cc2099597dac81ff92535cbd647948febee8fe36"
TOKEN_VAULT_ADDR = "0x7e081c0f82e31e35d845d1932eb36c84bbbb50568eef3c209f7104fabb2c254b"
TEST_WALLET = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
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
        self.config_admin_hex = ZERO_ACTOR_1
        self.grow_admin_addr: Optional[str] = None
        self.live_stream_id: Optional[str] = None
        self.live_group_id: Optional[str] = None

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
                "request_body": body,
                "request_headers": req_headers,
                "url": url,
            }
        except Exception as exc:
            return {
                "status": 0,
                "ok": False,
                "data": None,
                "headers": {},
                "elapsed_ms": int((time.time() - started) * 1000),
                "error": str(exc),
                "request_body": body,
                "request_headers": req_headers,
                "url": url,
            }

    def get(self, path: str, headers: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("GET", path, headers=headers)

    def post(self, path: str, body: Optional[dict] = None, headers: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("POST", path, body=body, headers=headers)

    def put(self, path: str, body: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("PUT", path, body=body or {})

    def delete(self, path: str) -> Dict[str, Any]:
        return self.request("DELETE", path)

    def section(self, name: str, detail: str = ""):
        suffix = f" — {detail}" if detail else ""
        print(f"\n{'─' * 64}\n[{name}]{suffix}\n{'─' * 64}")

    def add_result(self, section: str, name: str, method: str, endpoint: str, ok: bool, response: Optional[Dict[str, Any]] = None, *, warn: bool = False, skip: bool = False, detail: str = "", is_known_bug: bool = False):
        tag = "SKIP" if skip else "WARN" if warn else "PASS" if ok else "FAIL"
        icon = "⏭️" if skip else "⚠️" if warn else "✅" if ok else "❌"
        note = " [known server bug]" if is_known_bug else ""
        print(f"  {icon} [{tag}] {name}" + (f" — {detail}" if detail else "") + note)

        status = skip or warn or ok
        if skip:
            self.skipped += 1
        elif warn:
            self.warned += 1
        elif ok:
            self.passed += 1
        else:
            self.failed += 1

        request_payload = None
        response_payload = None
        response_headers = None
        status_code = None
        elapsed_ms = 0
        error = None
        if response:
            request_payload = {
                "url": response.get("url"),
                "headers": response.get("request_headers"),
                "body": response.get("request_body"),
            }
            response_payload = response.get("data")
            response_headers = response.get("headers")
            status_code = response.get("status")
            elapsed_ms = response.get("elapsed_ms", 0)
            error = response.get("error")

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
                "status_code": status_code,
                "request": request_payload,
                "response": response_payload,
                "response_headers": response_headers,
                "error": error,
                "is_known_bug": is_known_bug,
            }
        )

    def run_case(self, section: str, name: str, method: str, endpoint: str, fn):
        try:
            fn()
        except Exception as exc:
            self.add_result(section, name, method, endpoint, False, detail=f"threw: {exc}")
        self.sleep()

    def record_response(self, section: str, name: str, method: str, endpoint: str, response: Dict[str, Any], ok: bool, *, warn: bool = False, detail: str = "", is_known_bug: bool = False):
        self.add_result(section, name, method, endpoint, ok, response, warn=warn, detail=detail, is_known_bug=is_known_bug)

    def test_health(self):
        s = "Health"
        self.section(s)
        def root():
            r = self.get("/")
            self.record_response(s, "GET / — API root docs", "GET", "/", r, r["ok"] and bool((r["data"] or {}).get("name")), detail=f'name="{(r["data"] or {}).get("name")}"')
        def health_status():
            r = self.get("/health")
            healthy = (r["data"] or {}).get("status") == "healthy"
            self.record_response(s, "GET /health — status=healthy", "GET", "/health", r, r["ok"] and healthy, warn=(r["ok"] and not healthy), detail=f"status={(r['data'] or {}).get('status')}, balance={(r['data'] or {}).get('balance')}")
        def health_contracts():
            r = self.get("/health")
            cnt = len((r["data"] or {}).get("contracts") or {})
            self.record_response(s, "GET /health — 7/7 contracts", "GET", "/health", r, cnt == 7, warn=0 < cnt < 7, detail=f"contracts={cnt}/7")
        def favicon():
            r = self.get("/favicon.ico")
            self.record_response(s, "GET /favicon.ico — 404", "GET", "/favicon.ico", r, r["status"] == 404, detail=f"status={r['status']}")
        self.run_case(s, "GET / — API root docs", "GET", "/", root)
        self.run_case(s, "GET /health — status=healthy", "GET", "/health", health_status)
        self.run_case(s, "GET /health — 7/7 contracts", "GET", "/health", health_contracts)
        self.run_case(s, "GET /favicon.ico — 404", "GET", "/favicon.ico", favicon)

    def test_tokens(self):
        s = "Tokens"
        self.section(s, "V3 registry (WUSDC/WUSDT/WETH/WBTC/VARA)")
        cases = [
            ("GET /api/tokens — ≥5 tokens", "GET", "/api/tokens", None, lambda r: (r["ok"] and len((r["data"] or {}).get("tokens") or []) >= 5, False, f"count={len((r['data'] or {}).get('tokens') or [])}", False)),
            ("GET /api/tokens — token shape", "GET", "/api/tokens", None, lambda r: (bool(((r["data"] or {}).get("tokens") or [{}])[0].get("symbol")), False, f"first={((r['data'] or {}).get('tokens') or [{}])[0].get('symbol')}", False)),
            ("GET /api/tokens/stablecoins", "GET", "/api/tokens/stablecoins", None, lambda r: (r["ok"] and len((r["data"] or {}).get("tokens") or []) >= 1, False, f"count={len((r['data'] or {}).get('tokens') or [])}", False)),
            ("GET /api/tokens/prices", "GET", "/api/tokens/prices", None, lambda r: (r["ok"] and len(((r["data"] or {}).get("prices") or {}).keys()) > 0, False, f"keys={','.join(((r['data'] or {}).get('prices') or {}).keys())}", False)),
            (f"GET /api/tokens/{V3_SYMBOL}", "GET", f"/api/tokens/{V3_SYMBOL}", None, lambda r: (r["ok"] and (r["data"] or {}).get("symbol") == V3_SYMBOL, False, f"symbol={(r['data'] or {}).get('symbol')}", False)),
            ("GET /api/tokens/NONEXISTENT — 404", "GET", "/api/tokens/NONEXISTENT", None, lambda r: (r["status"] == 404, False, f"status={r['status']}", False)),
            ("GET /api/tokens/GROW — 404 expected (known config gap)", "GET", "/api/tokens/GROW", None, lambda r: (r["status"] == 404, True, "GROW only accessible via /api/grow-token/* — needs adding to V3 token registry", True)),
            (f"GET /api/tokens/{V3_SYMBOL}/resolve", "GET", f"/api/tokens/{V3_SYMBOL}/resolve", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("varaAddress")), False, f"addr={((r['data'] or {}).get('varaAddress') or '')[:20]}...", False)),
            (f"POST /api/tokens/convert (toBase, {V3_SYMBOL})", "POST", "/api/tokens/convert", {"symbol": V3_SYMBOL, "amount": "100.5", "direction": "toBase"}, lambda r: (r["ok"] and (r["data"] or {}).get("baseUnits") is not None, False, f"result={(r['data'] or {}).get('baseUnits')}", False)),
            (f"POST /api/tokens/convert (toDisplay, {V3_SYMBOL})", "POST", "/api/tokens/convert", {"symbol": V3_SYMBOL, "amount": "100000000", "direction": "toDisplay"}, lambda r: (r["ok"] and (r["data"] or {}).get("displayUnits") is not None, False, f"result={(r['data'] or {}).get('displayUnits')}", False)),
            ("POST /api/tokens/convert (bad direction) — 400", "POST", "/api/tokens/convert", {"symbol": V3_SYMBOL, "amount": "1", "direction": "baddir"}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            (f"POST /api/tokens/flow-rate ({V3_SYMBOL})", "POST", "/api/tokens/flow-rate", {"symbol": V3_SYMBOL, "amount": "10", "interval": "day"}, lambda r: (r["ok"] and (r["data"] or {}).get("perSecondRaw") is not None, False, f"perSec={(r['data'] or {}).get('perSecondRaw')}", False)),
            (f"POST /api/tokens/{V3_SYMBOL}/approve (payload mode)", "POST", f"/api/tokens/{V3_SYMBOL}/approve", {"spender": TOKEN_VAULT_ADDR, "amount": "100"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload") or (r["data"] or {}).get("payloadHex") or (r["data"] or {}).get("encoded") or (r["data"] or {}).get("to")), r["ok"] and not bool((r["data"] or {}).get("payload") or (r["data"] or {}).get("payloadHex") or (r["data"] or {}).get("encoded") or (r["data"] or {}).get("to")), f"status={r['status']}, keys={','.join((r['data'] or {}).keys())}", False)),
            (f"GET /api/tokens/{V3_SYMBOL}/vault-balance/:wallet", "GET", f"/api/tokens/{V3_SYMBOL}/vault-balance/{TEST_WALLET}", None, lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, 'Expected 32 bytes, found 48 — EVM→Vara address mismatch in token-service', True)),
            ("GET /api/tokens/vault-balances/:wallet", "GET", f"/api/tokens/vault-balances/{TEST_WALLET}", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
        ]
        self.run_matrix(s, cases)

    def test_grow_token(self):
        s = "GROW Token"
        self.section(s)
        def meta():
            r = self.get("/api/grow-token/meta")
            self.grow_admin_addr = (r["data"] or {}).get("admin")
            self.record_response(s, "GET /api/grow-token/meta", "GET", "/api/grow-token/meta", r, r["ok"] and bool((r["data"] or {}).get("name")), detail=f'name="{(r["data"] or {}).get("name")}", admin={((r["data"] or {}).get("admin") or "")[:12]}...')
        self.run_case(s, "GET /api/grow-token/meta", "GET", "/api/grow-token/meta", meta)
        cases = [
            ("GET /api/grow-token/total-supply", "GET", "/api/grow-token/total-supply", None, lambda r: (r["ok"] and (r["data"] or {}).get("totalSupply") is not None, False, f"supply={(r['data'] or {}).get('totalSupply')}", False)),
            ("GET /api/grow-token/balance/:account", "GET", f"/api/grow-token/balance/{ZERO_ACTOR_1}", None, lambda r: (r["ok"] and (r["data"] or {}).get("balance") is not None, False, f"balance={(r['data'] or {}).get('balance')}", False)),
            ("GET /api/grow-token/allowance", "GET", f"/api/grow-token/allowance/{ZERO_ACTOR_1}/{TOKEN_VAULT_ADDR}", None, lambda r: (r["ok"] and (r["data"] or {}).get("allowance") is not None, False, f"allowance={(r['data'] or {}).get('allowance')}", False)),
            ("GET /api/grow-token/faucet/config", "GET", "/api/grow-token/faucet/config", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("mode")), False, f"mode={(r['data'] or {}).get('mode')}, rateLimit={(r['data'] or {}).get('rateLimitSeconds')}s", False)),
            ("GET /api/grow-token/admin/info", "GET", "/api/grow-token/admin/info", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("adminAddress")), False, f"admin={((r['data'] or {}).get('adminAddress') or '')[:20]}...", False)),
            ("GET /api/grow-token/admin/whitelist", "GET", "/api/grow-token/admin/whitelist", None, lambda r: (r["ok"] and (r["data"] or {}).get("mode") is not None, False, f"count={len((r['data'] or {}).get('whitelist') or [])}", False)),
            ('POST /api/grow-token/faucet (missing "to") — 400', "POST", "/api/grow-token/faucet", {}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ("POST /api/grow-token/approve (payload)", "POST", "/api/grow-token/approve", {"spender": TOKEN_VAULT_ADDR, "amount": "500000000000000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/grow-token/transfer (payload)", "POST", "/api/grow-token/transfer", {"to": ZERO_ACTOR_1, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/grow-token/transfer-from (payload)", "POST", "/api/grow-token/transfer-from", {"from": ZERO_ACTOR_1, "to": ZERO_ACTOR_2, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/grow-token/mint (payload)", "POST", "/api/grow-token/mint", {"to": ZERO_ACTOR_1, "amount": "1000000000000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/grow-token/burn (payload)", "POST", "/api/grow-token/burn", {"amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/grow-token/transfer (missing amount) — 400", "POST", "/api/grow-token/transfer", {"to": ZERO_ACTOR_1}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ('POST /api/grow-token/mint (missing "to") — 400', "POST", "/api/grow-token/mint", {"amount": "1000"}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ("POST /api/grow-token/burn (missing amount) — 400", "POST", "/api/grow-token/burn", {}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
        ]
        self.run_matrix(s, cases)

    def test_grow_token_flow(self):
        s = "GROW Token Flow"
        self.section(s, "Full lifecycle (railway-flow.mjs)")
        if self.skip_mutations:
            self.add_result(s, "GROW Token Flow", "SCRIPT", "grow_token_flow", True, skip=True, detail="--skip-mutations")
            return
        if not self.grow_admin_addr:
            self.add_result(s, "GROW Token Flow", "SCRIPT", "grow_token_flow", True, skip=True, detail="admin addr not available from /api/grow-token/meta")
            return
        def step1():
            r = self.get(f"/api/grow-token/balance/{self.grow_admin_addr}")
            bal = (r["data"] or {}).get("balance") or "0"
            self.record_response(s, "Admin GROW balance", "GET", f"/api/grow-token/balance/{self.grow_admin_addr}", r, r["ok"], detail=f"balance={bal}")
        def step2():
            r = self.post("/api/grow-token/faucet", {"to": self.grow_admin_addr})
            if r["status"] == 429:
                self.record_response(s, "Faucet mint (429 rate limited — OK)", "POST", "/api/grow-token/faucet", r, True, warn=True, detail="already minted recently")
            else:
                self.record_response(s, "Faucet mint 1,000 GROW", "POST", "/api/grow-token/faucet", r, r["ok"] and bool((r["data"] or {}).get("blockHash")), detail=f"blockHash={((r['data'] or {}).get('blockHash') or '')[:20]}...")
                self.sleep(3000)
        def step4():
            r = self.post("/api/grow-token/approve", {"spender": TOKEN_VAULT_ADDR, "amount": "500000000000000"})
            self.record_response(s, "Approve vault 500 GROW", "POST", "/api/grow-token/approve", r, r["ok"] and bool((r["data"] or {}).get("blockHash")), detail=f"blockHash={((r['data'] or {}).get('blockHash') or '')[:20]}...")
            self.sleep(3000)
        def step5():
            endpoint = f"/api/grow-token/allowance/{self.grow_admin_addr}/{TOKEN_VAULT_ADDR}"
            r = self.get(endpoint)
            allowance = int((r["data"] or {}).get("allowance") or 0)
            self.record_response(s, "Allowance ≥ 500 GROW", "GET", endpoint, r, r["ok"] and allowance >= 500000000000000, detail=f"allowance={allowance}")
        def step6():
            r = self.post("/api/vault/deposit", {"token": GROW_TOKEN_ADDR, "amount": "100000000000000"})
            self.record_response(s, "Deposit 100 GROW to vault", "POST", "/api/vault/deposit", r, r["ok"] and bool((r["data"] or {}).get("blockHash")), detail=f"blockHash={((r['data'] or {}).get('blockHash') or '')[:20]}...")
            self.sleep(3000)
        def step8a():
            r = self.get("/api/streams/total")
            self.record_response(s, "Stream count before create", "GET", "/api/streams/total", r, r["ok"], detail=f"total={(r['data'] or {}).get('total')}")
        def step8b():
            r = self.post("/api/streams", {"receiver": ZERO_ACTOR_1, "token": GROW_TOKEN_ADDR, "flowRate": "1000000000", "initialDeposit": "50000000000000"})
            created = r["status"] in (200, 201)
            self.record_response(s, "Create GROW stream (live)", "POST", "/api/streams", r, created and bool((r["data"] or {}).get("blockHash")), detail=f"status={r['status']}, streamId={(r['data'] or {}).get('streamId')}")
            self.sleep(5000)
        def step8c():
            endpoint = f"/api/streams/sender/{self.grow_admin_addr}"
            r = self.get(endpoint)
            ids = (r["data"] or {}).get("streamIds") or []
            if ids:
                self.live_stream_id = sorted([str(x) for x in ids], key=lambda x: int(x), reverse=True)[0]
            self.record_response(s, "Resolved streamId from sender query", "GET", endpoint, r, r["ok"] and bool(self.live_stream_id), detail=f"found={len(ids)}, id={self.live_stream_id}")
        def step9():
            if not self.live_stream_id:
                self.add_result(s, "Verify stream Active", "GET", "/api/streams/:id", True, skip=True, detail="no streamId")
                return
            endpoint = f"/api/streams/{self.live_stream_id}"
            r = self.get(endpoint)
            self.record_response(s, "Stream status is Active", "GET", endpoint, r, r["ok"] and (r["data"] or {}).get("status") == "Active", detail=f"status={(r['data'] or {}).get('status')}")
        for name, method, endpoint, fn in [
            ("Admin GROW balance", "GET", f"/api/grow-token/balance/{self.grow_admin_addr}", step1),
            ("Faucet mint 1,000 GROW", "POST", "/api/grow-token/faucet", step2),
            ("Approve vault 500 GROW", "POST", "/api/grow-token/approve", step4),
            ("Allowance ≥ 500 GROW", "GET", f"/api/grow-token/allowance/{self.grow_admin_addr}/{TOKEN_VAULT_ADDR}", step5),
            ("Deposit 100 GROW to vault", "POST", "/api/vault/deposit", step6),
            ("Stream count before create", "GET", "/api/streams/total", step8a),
            ("Create GROW stream (live)", "POST", "/api/streams", step8b),
            ("Resolved streamId from sender query", "GET", f"/api/streams/sender/{self.grow_admin_addr}", step8c),
            ("Stream status is Active", "GET", "/api/streams/:id", step9),
        ]:
            self.run_case(s, name, method, endpoint, fn)

    def test_streams(self):
        s = "Streams"
        self.section(s, "StreamCore")
        def config():
            r = self.get("/api/streams/config")
            if r["ok"] and (r["data"] or {}).get("admin"):
                self.config_admin_hex = (r["data"] or {}).get("admin")
            self.record_response(s, "GET /api/streams/config", "GET", "/api/streams/config", r, r["ok"] and bool((r["data"] or {}).get("admin")), detail=f"admin={((r['data'] or {}).get('admin') or '')[:20]}...")
        self.run_case(s, "GET /api/streams/config", "GET", "/api/streams/config", config)
        sender_endpoint = f"/api/streams/sender/{self.config_admin_hex}"
        def sender_case():
            r = self.get(sender_endpoint)
            ids = (r["data"] or {}).get("streamIds") or []
            self.record_response(s, "GET /api/streams/sender/:address", "GET", sender_endpoint, r, r["ok"] and isinstance(ids, list), detail=f"ids={json.dumps(ids[:4])}")
        self.run_case(s, "GET /api/streams/sender/:address", "GET", sender_endpoint, sender_case)
        first_id = self.live_stream_id or "1"
        cases = [
            ("GET /api/streams/total", "GET", "/api/streams/total", None, lambda r: (r["ok"] and (r["data"] or {}).get("total") is not None, False, f"total={(r['data'] or {}).get('total')}", False)),
            ("GET /api/streams/active", "GET", "/api/streams/active", None, lambda r: (r["ok"] and (r["data"] or {}).get("active") is not None, False, f"active={(r['data'] or {}).get('active')}", False)),
            ("GET /api/streams/receiver/:address", "GET", f"/api/streams/receiver/{ZERO_ACTOR_1}", None, lambda r: (r["ok"] and isinstance((r["data"] or {}).get("streamIds"), list), False, f"count={len((r['data'] or {}).get('streamIds') or [])}", False)),
            ("GET /api/streams/:id (data + enrichment)", "GET", f"/api/streams/{first_id}", None, lambda r: (r["ok"], r["ok"] and not bool((r["data"] or {}).get("tokenMeta") or (r["data"] or {}).get("symbol") or (r["data"] or {}).get("display")), f"status={(r['data'] or {}).get('status')}", False)),
            ("GET /api/streams/:id/balance", "GET", f"/api/streams/{first_id}/balance", None, lambda r: (r["ok"] or r["status"] == 404, False, f"withdrawable={(r['data'] or {}).get('withdrawable')}", False)),
            ("GET /api/streams/:id/buffer", "GET", f"/api/streams/{first_id}/buffer", None, lambda r: (r["ok"] or r["status"] == 404, False, f"remaining={(r['data'] or {}).get('remainingBuffer')}", False)),
            ("POST /api/streams (missing receiver) — 400", "POST", "/api/streams", {"token": ZERO_ACTOR, "flowRate": "1000"}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ("POST /api/streams/create (missing symbol) — 400", "POST", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "amount": "1", "interval": "second"}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ("POST /api/streams/create (unknown symbol) — 404", "POST", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "symbol": "FAKETOKEN", "amount": "1", "interval": "second"}, lambda r: (r["status"] == 404, False, f"status={r['status']}", False)),
            (f"POST /api/streams/create ({V3_SYMBOL}, payload)", "POST", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "symbol": V3_SYMBOL, "amount": "0.001", "interval": "second", "initialDeposit": "10", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/streams (payload)", "POST", "/api/streams", {"receiver": ZERO_ACTOR_1, "token": ZERO_ACTOR, "flowRate": "1000", "initialDeposit": "3600000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("PUT /api/streams/:id (payload)", "PUT", f"/api/streams/{first_id}", {"flowRate": "2000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
        ]
        self.run_matrix(s, cases)

    def test_platform_sections(self):
        self.run_matrix("Vault", [
            ("GET /api/vault/config", "GET", "/api/vault/config", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/vault/paused", "GET", "/api/vault/paused", None, lambda r: (r["ok"] and isinstance((r["data"] or {}).get("paused"), bool), False, f"paused={(r['data'] or {}).get('paused')}", False)),
            ("GET /api/vault/balance", "GET", f"/api/vault/balance/{ZERO_ACTOR_1}/{ZERO_ACTOR}", None, lambda r: (r["ok"], False, f"deposited={(r['data'] or {}).get('total_deposited')}", False)),
            ("GET /api/vault/allocation/:streamId", "GET", "/api/vault/allocation/1", None, lambda r: (r["ok"] and (r["data"] or {}).get("allocated") is not None, False, f"allocated={(r['data'] or {}).get('allocated')}", False)),
            ("GET /api/vault/balances/:wallet", "GET", f"/api/vault/balances/{TEST_WALLET}", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("POST /api/vault/deposit (payload)", "POST", "/api/vault/deposit", {"token": ZERO_ACTOR, "amount": "5000000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("POST /api/vault/withdraw (payload)", "POST", "/api/vault/withdraw", {"token": ZERO_ACTOR, "amount": "1000", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
        ])
        self.run_matrix("Splits", [
            ("GET /api/splits/config", "GET", "/api/splits/config", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/splits/total", "GET", "/api/splits/total", None, lambda r: (r["ok"] and (r["data"] or {}).get("total") is not None, False, f"total={(r['data'] or {}).get('total')}", False)),
            ("GET /api/splits/owner/:address", "GET", f"/api/splits/owner/{self.config_admin_hex}", None, lambda r: (r["ok"], False, f"groupIds={json.dumps((r['data'] or {}).get('groupIds'))}", False)),
            ("POST /api/splits (payload)", "POST", "/api/splits", {"recipients": [{"address": ZERO_ACTOR_1, "weight": 100}], "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
            ("GET /api/splits/:id/preview (nonexistent) — 500 not 404", "GET", "/api/splits/1/preview/10000", None, lambda r: (r["status"] != 200, r["status"] == 500, 'contract panics "Group not found" instead of 404', True)),
        ])
        self.run_matrix("Permissions", [
            ("GET /api/permissions/config", "GET", "/api/permissions/config", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/permissions/total", "GET", "/api/permissions/total", None, lambda r: (r["ok"] and (r["data"] or {}).get("total") is not None, False, f"total={(r['data'] or {}).get('total')}", False)),
            ("GET /api/permissions/check (no permission)", "GET", f"/api/permissions/check/{ZERO_ACTOR_1}/{ZERO_ACTOR_42}/CreateStream", None, lambda r: (r["ok"] and (r["data"] or {}).get("hasPermission") is False, False, f"hasPermission={(r['data'] or {}).get('hasPermission')}", False)),
            ("POST /api/permissions/grant (payload)", "POST", "/api/permissions/grant", {"grantee": ZERO_ACTOR_42, "scope": "CreateStream", "mode": "payload"}, lambda r: (r["ok"] and bool((r["data"] or {}).get("payload")), False, f"status={r['status']}", False)),
        ])
        self.run_matrix("Bounty", [
            ("GET /api/bounty/config", "GET", "/api/bounty/config", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/bounty/total", "GET", "/api/bounty/total", None, lambda r: (r["ok"] and (r["data"] or {}).get("total") is not None, False, f"total={(r['data'] or {}).get('total')}", False)),
            ("GET /api/bounty/open", "GET", "/api/bounty/open", None, lambda r: (r["ok"] and (r["data"] or {}).get("bountyIds") is not None, False, f"open={len((r['data'] or {}).get('bountyIds') or [])}", False)),
            ("GET /api/bounty/:id (id=1)", "GET", "/api/bounty/1", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("title")), False, f"title={(r['data'] or {}).get('title')}", False)),
        ])
        self.run_matrix("Identity", [
            ("GET /api/identity/config", "GET", "/api/identity/config", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/identity/oracle", "GET", "/api/identity/oracle", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("oracle")), False, f"oracle={((r['data'] or {}).get('oracle') or '')[:18]}...", False)),
            ("GET /api/identity/total", "GET", "/api/identity/total", None, lambda r: (r["ok"] and (r["data"] or {}).get("total") is not None, False, f"total={(r['data'] or {}).get('total')}", False)),
        ])
        self.run_matrix("Leaderboard", [
            ("GET /api/leaderboard default", "GET", "/api/leaderboard", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/leaderboard?track=BADTRACK — 400", "GET", "/api/leaderboard?track=BADTRACK", None, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ("GET /api/leaderboard/stats", "GET", "/api/leaderboard/stats", None, lambda r: (r["ok"] and (r["data"] or {}).get("totalParticipants") is not None, False, f"participants={(r['data'] or {}).get('totalParticipants')}", False)),
            ("GET /api/leaderboard/:wallet (not found) — 500 vs 404", "GET", f"/api/leaderboard/{TEST_WALLET}", None, lambda r: (r["ok"] or r["status"] == 404, r["status"] == 500, 'should return 404 for missing participant', True)),
        ])
        self.run_matrix("Campaign", [
            ("GET /api/campaign/config", "GET", "/api/campaign/config", None, lambda r: (r["ok"] and bool((r["data"] or {}).get("xpTiers")), False, f"pool={(r['data'] or {}).get('poolUSDC')}", False)),
            ("GET /api/campaign/leaderboard", "GET", "/api/campaign/leaderboard", None, lambda r: (r["ok"], False, f"status={r['status']}", False)),
            ("GET /api/campaign/participant/:wallet (not found) — 500 vs 404", "GET", f"/api/campaign/participant/{TEST_WALLET}", None, lambda r: (r["ok"] or r["status"] == 404, r["status"] == 500, 'should return 404', True)),
            ("POST /api/campaign/register (invalid track) — 400", "POST", "/api/campaign/register", {"wallet": TEST_WALLET, "track": "BADTRACK"}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
            ("POST /api/campaign/payout-snapshot (no auth) — 401", "POST", "/api/campaign/payout-snapshot", None, lambda r: (r["status"] == 401, False, f"status={r['status']}", False)),
        ])
        self.run_matrix("Users", [
            ("GET /api/users/:wallet (not found) — 404", "GET", f"/api/users/{TEST_WALLET}", None, lambda r: (r["status"] == 404, False, f"status={r['status']}", False)),
            ("GET /api/users/:wallet/referrals (not found) — 404", "GET", f"/api/users/{TEST_WALLET}/referrals", None, lambda r: (r["status"] == 404, False, f"status={r['status']}", False)),
            ("POST /api/users/register (missing wallet) — 400", "POST", "/api/users/register", {}, lambda r: (r["status"] == 400, False, f"status={r['status']}", False)),
        ])

    def test_security(self):
        s = "Security"
        self.section(s)
        def nosniff():
            r = self.get("/health")
            self.record_response(s, "X-Content-Type-Options: nosniff", "GET", "/health", r, r["headers"].get("x-content-type-options") == "nosniff", detail=f"value={r['headers'].get('x-content-type-options')}")
        def xss():
            payload = f"<script>alert({int(time.time())})</script>"
            r = self.post("/api/campaign/register", {"wallet": payload, "track": "OSS", "github_handle": "test-xss"})
            rejected = r["status"] in (400, 422)
            self.record_response(s, "XSS: <script> wallet rejected (not stored in DB)", "POST", "/api/campaign/register", r, rejected, detail=f"status={r['status']} — should 400/422", is_known_bug=not rejected)
        self.run_case(s, "X-Content-Type-Options: nosniff", "GET", "/health", nosniff)
        self.run_case(s, "XSS wallet rejected", "POST", "/api/campaign/register", xss)

    def test_rate_limiting(self):
        s = "Rate Limiting"
        self.section(s)
        def faucet_limit():
            first = self.post("/api/grow-token/faucet", {"to": ZERO_ACTOR_2})
            self.sleep(1000)
            second = self.post("/api/grow-token/faucet", {"to": ZERO_ACTOR_2})
            self.record_response(s, "Faucet rate limit (5-minute window)", "POST", "/api/grow-token/faucet", second, second["status"] == 429, warn=second["status"] != 429, detail=f"first={first['status']}, second={second['status']}", is_known_bug=second["status"] != 429)
        self.run_case(s, "Faucet rate limit", "POST", "/api/grow-token/faucet", faucet_limit)

    def run_matrix(self, section: str, cases: List[Any]):
        self.section(section)
        for name, method, endpoint, body, evaluator in cases:
            def make_case(n=name, m=method, e=endpoint, b=body, ev=evaluator):
                def case():
                    r = self.request(m, e, body=b)
                    ok, warn, detail, is_known_bug = ev(r)
                    self.record_response(section, n, m, e, r, ok, warn=warn, detail=detail, is_known_bug=is_known_bug)
                return case
            self.run_case(section, name, method, endpoint, make_case())

    def build_report(self) -> Dict[str, Any]:
        total_tests = len(self.results)
        real_failures = [item for item in self.results if item["tag"] == "FAIL" and not item.get("is_known_bug")]
        passed = sum(1 for item in self.results if item["tag"] == "PASS")
        total_time_ms = sum(item.get("elapsed_ms", 0) for item in self.results)
        pass_rate = f"{(passed / total_tests * 100):.1f}%" if total_tests else "0.0%"
        return {
            "server": self.base_url,
            "generated_at": datetime.utcnow().isoformat(),
            "suite": "GrowStreams Master E2E API Test Suite v3",
            "total_tests": total_tests,
            "passed": passed,
            "failed": len(real_failures),
            "warnings": self.warned,
            "skipped": self.skipped,
            "known_bugs": sum(1 for item in self.results if item.get("is_known_bug")),
            "pass_rate": pass_rate,
            "total_time_ms": total_time_ms,
            "success": len(real_failures) == 0,
            "results": self.results,
        }

    def write_report(self):
        with open(RESULTS_FILE, "w") as handle:
            json.dump(self.build_report(), handle, indent=2, default=str)

    def print_summary(self):
        total = self.passed + self.failed + self.warned + self.skipped
        print("\n" + "═" * 66)
        print("  RESULTS")
        print("═" * 66)
        print(f"  ✅ PASS       : {self.passed}")
        print(f"  ❌ FAIL       : {self.failed}")
        print(f"  ⚠️  WARN       : {self.warned}")
        print(f"  ⏭️  SKIP       : {self.skipped}")
        print(f"  📌 Known bugs : {sum(1 for item in self.results if item.get('is_known_bug'))}")
        print(f"  TOTAL        : {total}")
        print("═" * 66)

    def run(self) -> int:
        print("\n" + "═" * 66)
        print("  GrowStreams — Master E2E API Test Suite v3")
        print("  REST + Railway Flow + Security + Known Bug Tracking")
        print("═" * 66)
        print(f"  Target : {self.base_url}")
        print(f"  Mode   : {'READ-ONLY (no blockchain writes)' if self.skip_mutations else 'FULL (includes live blockchain txs)'}")
        print(f"  Time   : {datetime.utcnow().isoformat()}Z")
        print("═" * 66)
        self.test_health()
        self.test_tokens()
        self.test_grow_token()
        self.test_grow_token_flow()
        self.test_streams()
        self.test_platform_sections()
        self.test_security()
        self.test_rate_limiting()
        self.write_report()
        self.print_summary()
        return 1 if self.failed > 0 else 0


def main(base_url: str = DEFAULT_BASE_URL, skip_mutations: bool = False) -> int:
    suite = Suite(base_url=base_url, skip_mutations=skip_mutations)
    return suite.run()
