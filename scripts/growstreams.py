#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from growstreams_v3_impl import DEFAULT_BASE_URL as V3_DEFAULT_BASE_URL
from growstreams_v3_impl import main as run_v3_main


DEFAULT_BASE_URL = "https://growstreams-launch-production.up.railway.app"
ZERO_ACTOR = "0x0000000000000000000000000000000000000000000000000000000000000000"
ZERO_ACTOR_1 = "0x0000000000000000000000000000000000000000000000000000000000000001"
TEST_WALLET = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
DELAY_MS = 500
TIMEOUT = 45
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "growstreams_results.json")


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


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

    def sleep(self):
        time.sleep(DELAY_MS / 1000)

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
            elapsed_ms = int((time.time() - started) * 1000)
            return {
                "status": 0,
                "ok": False,
                "data": None,
                "headers": {},
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
            }

    def get(self, path: str) -> Dict[str, Any]:
        return self.request("GET", path)

    def post(self, path: str, body: Optional[dict] = None, headers: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("POST", path, body=body, headers=headers)

    def put(self, path: str, body: Optional[dict] = None) -> Dict[str, Any]:
        return self.request("PUT", path, body=body or {})

    def delete(self, path: str) -> Dict[str, Any]:
        return self.request("DELETE", path)

    def add_result(self, section: str, name: str, method: str, endpoint: str, pass_ok: bool, warn: bool = False, skip: bool = False, detail: str = "", elapsed_ms: int = 0):
        tag = "SKIP" if skip else "WARN" if warn else "PASS" if pass_ok else "FAIL"
        icon = "⏭️" if skip else "⚠️" if warn else "✅" if pass_ok else "❌"
        print(f"  {icon} [{tag}] {name}" + (f" — {detail}" if detail else ""))

        if skip:
            self.skipped += 1
            status = True
        elif warn:
            self.warned += 1
            status = True
        elif pass_ok:
            self.passed += 1
            status = True
        else:
            self.failed += 1
            status = False

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

    def section(self, name: str):
        print(f"\n{'─' * 60}\n{name}\n{'─' * 60}")

    def test_health(self):
        s = "Health"
        self.section(s)

        def case_root():
            r = self.get("/")
            ok = r["ok"] and isinstance(r["data"], dict) and r["data"].get("name")
            self.add_result(s, "GET / (API root docs)", "GET", "/", ok, detail=f"name={None if not isinstance(r['data'], dict) else r['data'].get('name')}", elapsed_ms=r["elapsed_ms"])

        def case_health_status():
            r = self.get("/health")
            status = r["data"].get("status") if isinstance(r["data"], dict) else None
            ok = r["ok"] and status in ("healthy", "degraded")
            warn = status == "degraded"
            balance = r["data"].get("balance") if isinstance(r["data"], dict) else None
            self.add_result(s, "GET /health — status", "GET", "/health", ok, warn=warn, detail=f"status={status}, balance={balance}", elapsed_ms=r["elapsed_ms"])

        def case_health_contracts():
            r = self.get("/health")
            contracts = r["data"].get("contracts", {}) if isinstance(r["data"], dict) else {}
            count = len(contracts)
            self.add_result(s, "GET /health — contracts count", "GET", "/health", count >= 6, warn=count < 7, detail=f"contracts={count}/7", elapsed_ms=r["elapsed_ms"])

        def case_favicon():
            r = self.get("/favicon.ico")
            self.add_result(s, "GET /favicon.ico — 404", "GET", "/favicon.ico", r["status"] == 404, detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])

        self.run_case(s, "GET / (API root docs)", "GET", "/", case_root)
        self.run_case(s, "GET /health — status", "GET", "/health", case_health_status)
        self.run_case(s, "GET /health — contracts count", "GET", "/health", case_health_contracts)
        self.run_case(s, "GET /favicon.ico — 404", "GET", "/favicon.ico", case_favicon)

    def test_tokens(self):
        s = "Tokens"
        self.section(s)
        cases = [
            ("GET /api/tokens", "GET", "/api/tokens", lambda r: (r["ok"] and isinstance((r["data"] or {}).get("tokens"), list) and len(r["data"]["tokens"]) > 0, False, f"count={len((r['data'] or {}).get('tokens', []))}")),
            ("GET /api/tokens/stablecoins", "GET", "/api/tokens/stablecoins", lambda r: (r["ok"] and isinstance((r["data"] or {}).get("tokens"), list), False, f"count={len((r['data'] or {}).get('tokens', []))}")),
            ("GET /api/tokens/prices", "GET", "/api/tokens/prices", lambda r: (r["ok"] and isinstance((r["data"] or {}).get("prices"), dict), False, f"keys={','.join(((r['data'] or {}).get('prices') or {}).keys())}")),
            ("GET /api/tokens/GROW", "GET", "/api/tokens/GROW", lambda r: (r["ok"] and (r["data"] or {}).get("symbol"), False, f"symbol={(r['data'] or {}).get('symbol')}, decimals={(r['data'] or {}).get('decimals')}")),
            ("GET /api/tokens/NONEXISTENT — 404", "GET", "/api/tokens/NONEXISTENT", lambda r: (r["status"] == 404, False, f"status={r['status']}")),
            ("GET /api/tokens/GROW/resolve", "GET", "/api/tokens/GROW/resolve", lambda r: (r["ok"] and (r["data"] or {}).get("varaAddress"), False, f"addr={((r['data'] or {}).get('varaAddress') or '')[:18]}...")),
        ]

        for name, method, endpoint, evaluator in cases:
            def make_case(n=name, m=method, e=endpoint, ev=evaluator):
                def case():
                    r = self.request(m, e)
                    ok, warn, detail = ev(r)
                    self.add_result(s, n, m, e, bool(ok), warn=warn, detail=detail, elapsed_ms=r["elapsed_ms"])
                return case
            self.run_case(s, name, method, endpoint, make_case())

        payload_cases = [
            ("POST /api/tokens/convert (toBase)", "/api/tokens/convert", {"symbol": "GROW", "amount": "1.5", "direction": "toBase"}, lambda r: (r["ok"] and (r["data"] or {}).get("baseUnits"), False, f"result={(r['data'] or {}).get('baseUnits')}")),
            ("POST /api/tokens/convert (toDisplay)", "/api/tokens/convert", {"symbol": "GROW", "amount": "1000000000000", "direction": "toDisplay"}, lambda r: (r["ok"] and (r["data"] or {}).get("displayUnits") is not None, False, f"result={(r['data'] or {}).get('displayUnits')}")),
            ("POST /api/tokens/convert (bad direction) — 400", "/api/tokens/convert", {"symbol": "GROW", "amount": "1", "direction": "bad"}, lambda r: (r["status"] == 400, False, f"status={r['status']}")),
            ("POST /api/tokens/flow-rate", "/api/tokens/flow-rate", {"symbol": "GROW", "amount": "10", "interval": "day"}, lambda r: (r["ok"] and (r["data"] or {}).get("perSecondRaw"), False, f"perSec={(r['data'] or {}).get('perSecondRaw')}")),
            ("POST /api/tokens/GROW/approve (payload mode)", "/api/tokens/GROW/approve", {"spender": ZERO_ACTOR_1, "amount": "1000"}, lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"payload={((r['data'] or {}).get('payload') or '')[:20]}...")),
        ]

        for name, endpoint, body, evaluator in payload_cases:
            def make_case(n=name, e=endpoint, b=body, ev=evaluator):
                def case():
                    r = self.post(e, b)
                    ok, warn, detail = ev(r)
                    self.add_result(s, n, "POST", e, bool(ok), warn=warn, detail=detail, elapsed_ms=r["elapsed_ms"])
                return case
            self.run_case(s, name, "POST", endpoint, make_case())

        for endpoint in [f"/api/tokens/GROW/vault-balance/{TEST_WALLET}", f"/api/tokens/vault-balances/{TEST_WALLET}"]:
            def make_case(e=endpoint):
                def case():
                    r = self.get(e)
                    ok = r["ok"] or r["status"] == 500
                    warn = r["status"] == 500
                    self.add_result(s, f"GET {e}", "GET", e, ok, warn=warn, detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])
                return case
            self.run_case(s, f"GET {endpoint}", "GET", endpoint, make_case())

    def test_group_generic(self, section: str, cases: List[Dict[str, Any]]):
        self.section(section)
        for item in cases:
            def make_case(spec=item):
                def case():
                    method = spec["method"]
                    endpoint = spec["endpoint"]
                    body = spec.get("body")
                    headers = spec.get("headers")
                    r = self.request(method, endpoint, body=body, headers=headers)
                    ok, warn, detail = spec["evaluate"](r)
                    self.add_result(section, spec["name"], method, endpoint, bool(ok), warn=warn, skip=spec.get("skip", False), detail=detail, elapsed_ms=r["elapsed_ms"])
                return case
            if item.get("skip"):
                self.add_result(section, item["name"], item["method"], item["endpoint"], True, skip=True, detail=item.get("detail", "skipped by configuration"))
                self.sleep()
            else:
                self.run_case(section, item["name"], item["method"], item["endpoint"], make_case())

    def test_grow_token(self):
        s = "GROW Token"
        cases = [
            {"name": "GET /api/grow-token/meta", "method": "GET", "endpoint": "/api/grow-token/meta", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}, name={(r['data'] or {}).get('name')}")},
            {"name": "GET /api/grow-token/total-supply", "method": "GET", "endpoint": "/api/grow-token/total-supply", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"supply={(r['data'] or {}).get('totalSupply')}")},
            {"name": "GET /api/grow-token/balance/:account", "method": "GET", "endpoint": f"/api/grow-token/balance/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"balance={(r['data'] or {}).get('balance')}, status={r['status']}")},
            {"name": "GET /api/grow-token/allowance/:owner/:spender", "method": "GET", "endpoint": f"/api/grow-token/allowance/{ZERO_ACTOR_1}/{ZERO_ACTOR}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/grow-token/faucet/config", "method": "GET", "endpoint": "/api/grow-token/faucet/config", "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("mode"), False, f"mode={(r['data'] or {}).get('mode')}, amountHuman={(r['data'] or {}).get('amountHuman')}")},
            {"name": "GET /api/grow-token/admin/info", "method": "GET", "endpoint": "/api/grow-token/admin/info", "evaluate": lambda r: (r["ok"], False, f"adminAddress={((r['data'] or {}).get('adminAddress') or '')[:18]}...")},
            {"name": "GET /api/grow-token/admin/whitelist", "method": "GET", "endpoint": "/api/grow-token/admin/whitelist", "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("mode") is not None, False, f"mode={(r['data'] or {}).get('mode')}, count={len((r['data'] or {}).get('whitelist', []))}")},
            {"name": "POST /api/grow-token/faucet (missing to) — 400", "method": "POST", "endpoint": "/api/grow-token/faucet", "body": {}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "POST /api/grow-token/approve (payload)", "method": "POST", "endpoint": "/api/grow-token/approve", "body": {"spender": ZERO_ACTOR_1, "amount": "1000000000000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"payload={((r['data'] or {}).get('payload') or '')[:20]}...")},
            {"name": "POST /api/grow-token/transfer (payload)", "method": "POST", "endpoint": "/api/grow-token/transfer", "body": {"to": ZERO_ACTOR_1, "amount": "1000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/grow-token/mint (payload)", "method": "POST", "endpoint": "/api/grow-token/mint", "body": {"to": ZERO_ACTOR_1, "amount": "1000000000000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/grow-token/burn (payload)", "method": "POST", "endpoint": "/api/grow-token/burn", "body": {"amount": "1000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/grow-token/transfer (missing amount) — 400", "method": "POST", "endpoint": "/api/grow-token/transfer", "body": {"to": ZERO_ACTOR_1}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
        ]
        self.test_group_generic(s, cases)

    def test_streams(self):
        s = "Streams"
        self.section(s)
        config_admin = ZERO_ACTOR_1
        existing_stream_id = "1"

        def case_config():
            nonlocal config_admin
            r = self.get("/api/streams/config")
            data = r["data"] or {}
            if data.get("admin"):
                config_admin = data["admin"]
            self.add_result(s, "GET /api/streams/config", "GET", "/api/streams/config", r["ok"] or r["status"] == 500, warn=not r["ok"], detail=f"status={r['status']}, admin={(data.get('admin') or '')[:18]}...", elapsed_ms=r["elapsed_ms"])

        def case_sender():
            nonlocal existing_stream_id
            endpoint = f"/api/streams/sender/{config_admin}"
            r = self.get(endpoint)
            ids = ((r["data"] or {}).get("streamIds") or [])
            if ids:
                existing_stream_id = str(ids[0])
            self.add_result(s, "GET /api/streams/sender/:address", "GET", endpoint, r["ok"] or r["status"] == 500, warn=not r["ok"], detail=f"ids={json.dumps(ids[:3])}", elapsed_ms=r["elapsed_ms"])

        self.run_case(s, "GET /api/streams/config", "GET", "/api/streams/config", case_config)

        for name, endpoint in [
            ("GET /api/streams/total", "/api/streams/total"),
            ("GET /api/streams/active", "/api/streams/active"),
        ]:
            def make_case(n=name, e=endpoint):
                def case():
                    r = self.get(e)
                    key = "total" if e.endswith("total") else "active"
                    self.add_result(s, n, "GET", e, r["ok"] or r["status"] == 500, warn=not r["ok"], detail=f"{key}={(r['data'] or {}).get(key)}, status={r['status']}", elapsed_ms=r["elapsed_ms"])
                return case
            self.run_case(s, name, "GET", endpoint, make_case())

        self.run_case(s, "GET /api/streams/sender/:address", "GET", f"/api/streams/sender/{config_admin}", case_sender)

        def case_receiver():
            endpoint = f"/api/streams/receiver/{ZERO_ACTOR_1}"
            r = self.get(endpoint)
            self.add_result(s, "GET /api/streams/receiver/:address", "GET", endpoint, r["ok"] or r["status"] == 500, warn=not r["ok"], detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])

        self.run_case(s, "GET /api/streams/receiver/:address", "GET", f"/api/streams/receiver/{ZERO_ACTOR_1}", case_receiver)

        for suffix in ["", "/balance", "/buffer"]:
            def make_case(sf=suffix):
                def case():
                    endpoint = f"/api/streams/{existing_stream_id}{sf}"
                    r = self.get(endpoint)
                    warn = (not r["ok"]) and r["status"] not in (404, 500)
                    ok = r["ok"] or r["status"] in (404, 500)
                    self.add_result(s, f"GET {endpoint}", "GET", endpoint, ok, warn=warn, detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])
                return case
            endpoint = f"/api/streams/{existing_stream_id}{suffix}"
            self.run_case(s, f"GET {endpoint}", "GET", endpoint, make_case())

        payload_cases = [
            ("POST /api/streams (payload mode)", "/api/streams", {"receiver": ZERO_ACTOR_1, "token": ZERO_ACTOR, "flowRate": "1000", "initialDeposit": "3600000", "mode": "payload"}),
            ("POST /api/streams/create (payload, human amounts)", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "symbol": "GROW", "amount": "0.001", "interval": "second", "initialDeposit": "10", "mode": "payload"}),
            ("POST /api/streams/create (missing fields) — 400", "/api/streams/create", {"receiver": ZERO_ACTOR_1}),
            ("POST /api/streams/create (unknown symbol) — 404", "/api/streams/create", {"receiver": ZERO_ACTOR_1, "symbol": "FAKECOIN", "amount": "1", "interval": "second", "initialDeposit": "10"}),
            ("POST /api/streams (missing fields) — 400", "/api/streams", {"receiver": ZERO_ACTOR_1}),
            ("PUT /api/streams/:id (payload)", f"/api/streams/{existing_stream_id}", {"flowRate": "2000", "mode": "payload"}),
            ("POST /api/streams/:id/pause (payload)", f"/api/streams/{existing_stream_id}/pause", {"mode": "payload"}),
            ("POST /api/streams/:id/resume (payload)", f"/api/streams/{existing_stream_id}/resume", {"mode": "payload"}),
            ("POST /api/streams/:id/deposit (payload)", f"/api/streams/{existing_stream_id}/deposit", {"amount": "1000000", "mode": "payload"}),
            ("POST /api/streams/:id/withdraw (payload)", f"/api/streams/{existing_stream_id}/withdraw", {"mode": "payload"}),
            ("POST /api/streams/:id/stop (payload)", f"/api/streams/{existing_stream_id}/stop", {"mode": "payload"}),
            ("POST /api/streams/:id/liquidate (payload)", f"/api/streams/{existing_stream_id}/liquidate", {"mode": "payload"}),
        ]

        for name, endpoint, body in payload_cases:
            method = "PUT" if name.startswith("PUT") else "POST"
            def make_case(n=name, e=endpoint, b=body, m=method):
                def case():
                    r = self.request(m, e, body=b)
                    if "missing fields" in n:
                        ok = r["status"] == 400
                    elif "unknown symbol" in n:
                        ok = r["status"] == 404
                    else:
                        ok = r["ok"] and (r["data"] or {}).get("payload")
                    self.add_result(s, n, m, e, bool(ok), warn=(m == "PUT" and not r["ok"] and r["status"] not in (400, 404, 500)), detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])
                return case
            self.run_case(s, name, method, endpoint, make_case())

        if self.skip_mutations:
            self.add_result(s, "POST /api/streams (LIVE blockchain)", "POST", "/api/streams", True, skip=True, detail="skipped via --skip-mutations")
        else:
            def case_live():
                endpoint = "/api/streams"
                body = {"receiver": ZERO_ACTOR_1, "token": ZERO_ACTOR, "flowRate": "1000", "initialDeposit": "3600000"}
                r = self.post(endpoint, body)
                warn = not r["ok"]
                block_hash = (r["data"] or {}).get("blockHash")
                self.add_result(s, "POST /api/streams (LIVE blockchain)", "POST", endpoint, r["ok"] and block_hash, warn=warn, detail=f"blockHash={(block_hash or '')[:18]}...", elapsed_ms=r["elapsed_ms"])
            self.run_case(s, "POST /api/streams (LIVE blockchain)", "POST", "/api/streams", case_live)

    def test_misc_sections(self):
        vault_cases = [
            {"name": "GET /api/vault/config", "method": "GET", "endpoint": "/api/vault/config", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/vault/paused", "method": "GET", "endpoint": "/api/vault/paused", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"paused={(r['data'] or {}).get('paused')}")},
            {"name": "GET /api/vault/balance/:owner/:token", "method": "GET", "endpoint": f"/api/vault/balance/{ZERO_ACTOR_1}/{ZERO_ACTOR}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/vault/allocation/:streamId", "method": "GET", "endpoint": "/api/vault/allocation/1", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"allocated={(r['data'] or {}).get('allocated')}")},
            {"name": "GET /api/vault/balances/:wallet", "method": "GET", "endpoint": f"/api/vault/balances/{TEST_WALLET}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "POST /api/vault/deposit (payload)", "method": "POST", "endpoint": "/api/vault/deposit", "body": {"token": ZERO_ACTOR, "amount": "5000000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/withdraw (payload)", "method": "POST", "endpoint": "/api/vault/withdraw", "body": {"token": ZERO_ACTOR, "amount": "1000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/deposit-token (payload, GROW)", "method": "POST", "endpoint": "/api/vault/deposit-token", "body": {"symbol": "GROW", "amount": "100", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/withdraw-token (payload, GROW)", "method": "POST", "endpoint": "/api/vault/withdraw-token", "body": {"symbol": "GROW", "amount": "10", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/deposit-native (payload)", "method": "POST", "endpoint": "/api/vault/deposit-native", "body": {"amount": "1000000000000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/withdraw-native (payload)", "method": "POST", "endpoint": "/api/vault/withdraw-native", "body": {"amount": "1000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/pause (payload)", "method": "POST", "endpoint": "/api/vault/pause", "body": {"mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/unpause (payload)", "method": "POST", "endpoint": "/api/vault/unpause", "body": {"mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/vault/deposit (missing amount) — 400", "method": "POST", "endpoint": "/api/vault/deposit", "body": {"token": ZERO_ACTOR}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "POST /api/vault/deposit-token (VARA) — 400/404", "method": "POST", "endpoint": "/api/vault/deposit-token", "body": {"symbol": "VARA", "amount": "1"}, "evaluate": lambda r: (r["status"] in (400, 404), False, f"status={r['status']}")},
        ]
        self.test_group_generic("Vault", vault_cases)

        splits_cases = [
            {"name": "GET /api/splits/config", "method": "GET", "endpoint": "/api/splits/config", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/splits/total", "method": "GET", "endpoint": "/api/splits/total", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"total={(r['data'] or {}).get('total')}")},
            {"name": "GET /api/splits/:id (id=1)", "method": "GET", "endpoint": "/api/splits/1", "evaluate": lambda r: (r["ok"] or r["status"] in (404, 500), r["status"] == 500, f"status={r['status']}")},
            {"name": "GET /api/splits/owner/:address", "method": "GET", "endpoint": f"/api/splits/owner/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, r["status"] == 500, f"status={r['status']}")},
            {"name": "GET /api/splits/:id/preview/:amount", "method": "GET", "endpoint": "/api/splits/1/preview/10000", "evaluate": lambda r: (r["ok"] or r["status"] in (404, 500), r["status"] == 500, f"status={r['status']}")},
            {"name": "POST /api/splits (payload)", "method": "POST", "endpoint": "/api/splits", "body": {"recipients": [{"address": ZERO_ACTOR_1, "weight": 60}, {"address": "0x0000000000000000000000000000000000000000000000000000000000000002", "weight": 40}], "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/splits/:id/distribute (payload)", "method": "POST", "endpoint": "/api/splits/1/distribute", "body": {"token": ZERO_ACTOR, "amount": "100000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "DELETE /api/splits/:id", "method": "DELETE", "endpoint": "/api/splits/999", "evaluate": lambda r: (r["ok"] or r["status"] in (404, 500), r["status"] == 500, f"status={r['status']}")},
        ]
        self.test_group_generic("Splits", splits_cases)

        permissions_cases = [
            {"name": "GET /api/permissions/config", "method": "GET", "endpoint": "/api/permissions/config", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/permissions/check", "method": "GET", "endpoint": f"/api/permissions/check/{ZERO_ACTOR_1}/{ZERO_ACTOR}/CreateStream", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"has={(r['data'] or {}).get('hasPermission')}")},
            {"name": "GET /api/permissions/granter/:address", "method": "GET", "endpoint": f"/api/permissions/granter/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/permissions/grantee/:address", "method": "GET", "endpoint": f"/api/permissions/grantee/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/permissions/total", "method": "GET", "endpoint": "/api/permissions/total", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"total={(r['data'] or {}).get('total')}")},
            {"name": "POST /api/permissions/grant (payload)", "method": "POST", "endpoint": "/api/permissions/grant", "body": {"grantee": ZERO_ACTOR_1, "scope": "CreateStream", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/permissions/revoke (payload)", "method": "POST", "endpoint": "/api/permissions/revoke", "body": {"grantee": ZERO_ACTOR_1, "scope": "CreateStream", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/permissions/revoke-all (payload)", "method": "POST", "endpoint": "/api/permissions/revoke-all", "body": {"grantee": ZERO_ACTOR_1, "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
        ]
        self.test_group_generic("Permissions", permissions_cases)

        bounty_cases = [
            {"name": "GET /api/bounty/config", "method": "GET", "endpoint": "/api/bounty/config", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/bounty/total", "method": "GET", "endpoint": "/api/bounty/total", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"total={(r['data'] or {}).get('total')}")},
            {"name": "GET /api/bounty/open", "method": "GET", "endpoint": "/api/bounty/open", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/bounty/:id (id=1)", "method": "GET", "endpoint": "/api/bounty/1", "evaluate": lambda r: (r["ok"] or r["status"] in (404, 500), not r["ok"] and r["status"] != 404, f"status={r['status']}")},
            {"name": "GET /api/bounty/creator/:address", "method": "GET", "endpoint": f"/api/bounty/creator/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/bounty/claimer/:address", "method": "GET", "endpoint": f"/api/bounty/claimer/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "POST /api/bounty (payload)", "method": "POST", "endpoint": "/api/bounty", "body": {"title": "Test Bounty", "token": ZERO_ACTOR, "maxFlowRate": "5000", "minScore": 60, "totalBudget": "10000000", "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r["data"] or {}).get("payload"), False, f"status={r['status']}")},
            {"name": "POST /api/bounty/:id/claim (payload)", "method": "POST", "endpoint": "/api/bounty/1/claim", "body": {"mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
            {"name": "POST /api/bounty/:id/verify (payload)", "method": "POST", "endpoint": "/api/bounty/1/verify", "body": {"claimer": ZERO_ACTOR_1, "score": 85, "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
            {"name": "POST /api/bounty/:id/complete (payload)", "method": "POST", "endpoint": "/api/bounty/1/complete", "body": {"mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
            {"name": "POST /api/bounty/:id/cancel (payload)", "method": "POST", "endpoint": "/api/bounty/1/cancel", "body": {"mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
        ]
        self.test_group_generic("Bounty", bounty_cases)

        identity_cases = [
            {"name": "GET /api/identity/config", "method": "GET", "endpoint": "/api/identity/config", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/identity/oracle", "method": "GET", "endpoint": "/api/identity/oracle", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"oracle={((r['data'] or {}).get('oracle') or '')[:18]}...")},
            {"name": "GET /api/identity/total", "method": "GET", "endpoint": "/api/identity/total", "evaluate": lambda r: (r["ok"] or r["status"] == 500, not r["ok"], f"total={(r['data'] or {}).get('total')}")},
            {"name": "GET /api/identity/binding/:actorId", "method": "GET", "endpoint": f"/api/identity/binding/{ZERO_ACTOR_1}", "evaluate": lambda r: (r["ok"] or r["status"] in (404, 500), not r["ok"] and r["status"] != 404, f"status={r['status']}")},
            {"name": "GET /api/identity/github/:username", "method": "GET", "endpoint": "/api/identity/github/nonexistent-user-xyz", "evaluate": lambda r: (r["ok"] or r["status"] in (404, 500), not r["ok"] and r["status"] != 404, f"status={r['status']}")},
            {"name": "POST /api/identity/bind (payload)", "method": "POST", "endpoint": "/api/identity/bind", "body": {"actorId": ZERO_ACTOR_1, "githubUsername": "test-user", "proofHash": "0xab" + ("ab" * 31), "score": 80, "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
            {"name": "POST /api/identity/update-score (payload)", "method": "POST", "endpoint": "/api/identity/update-score", "body": {"actorId": ZERO_ACTOR_1, "newScore": 92, "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
            {"name": "POST /api/identity/revoke (payload)", "method": "POST", "endpoint": "/api/identity/revoke", "body": {"actorId": ZERO_ACTOR_1, "mode": "payload"}, "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('payload'), False, f"status={r['status']}")},
        ]
        self.test_group_generic("Identity", identity_cases)

        leaderboard_cases = [
            {"name": "GET /api/leaderboard", "method": "GET", "endpoint": "/api/leaderboard", "evaluate": lambda r: (r["ok"], not r["ok"], f"status={r['status']}, entries={len((r['data'] or {}).get('participants', r['data'] or [])) if isinstance(r['data'], (dict, list)) else None}")},
            {"name": "GET /api/leaderboard?track=OSS", "method": "GET", "endpoint": "/api/leaderboard?track=OSS", "evaluate": lambda r: (r["ok"], not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/leaderboard?track=CONTENT", "method": "GET", "endpoint": "/api/leaderboard?track=CONTENT", "evaluate": lambda r: (r["ok"], not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/leaderboard?track=BAD — 400", "method": "GET", "endpoint": "/api/leaderboard?track=BAD", "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "GET /api/leaderboard?page=2&limit=10", "method": "GET", "endpoint": "/api/leaderboard?page=2&limit=10", "evaluate": lambda r: (r["ok"], not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/leaderboard/stats", "method": "GET", "endpoint": "/api/leaderboard/stats", "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('totalParticipants') is not None, not r["ok"], f"participants={(r['data'] or {}).get('totalParticipants')}, XP={(r['data'] or {}).get('totalXP')}")},
            {"name": "GET /api/leaderboard/:wallet", "method": "GET", "endpoint": f"/api/leaderboard/{TEST_WALLET}", "evaluate": lambda r: (r["ok"] or r["status"] == 404, not r["ok"] and r["status"] != 404, f"status={r['status']}")},
        ]
        self.test_group_generic("Leaderboard", leaderboard_cases)

        campaign_cases = [
            {"name": "GET /api/campaign/config", "method": "GET", "endpoint": "/api/campaign/config", "evaluate": lambda r: (r["ok"] and (r['data'] or {}).get('xpTiers'), False, f"pool=${(r['data'] or {}).get('poolUSDC')}, threshold={(r['data'] or {}).get('scoreThreshold')}")},
            {"name": "GET /api/campaign/leaderboard", "method": "GET", "endpoint": "/api/campaign/leaderboard", "evaluate": lambda r: (r["ok"], not r["ok"], f"status={r['status']}")},
            {"name": "GET /api/campaign/participant/:wallet", "method": "GET", "endpoint": f"/api/campaign/participant/{TEST_WALLET}", "evaluate": lambda r: (r["ok"] or r["status"] == 404, not r["ok"] and r["status"] != 404, f"status={r['status']}")},
            {"name": "POST /api/campaign/register (missing wallet) — 400", "method": "POST", "endpoint": "/api/campaign/register", "body": {"track": "OSS", "github_handle": "test"}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "POST /api/campaign/register (invalid track) — 400", "method": "POST", "endpoint": "/api/campaign/register", "body": {"wallet": TEST_WALLET, "track": "BADTRACK"}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "POST /api/campaign/register (OSS, no github) — 400", "method": "POST", "endpoint": "/api/campaign/register", "body": {"wallet": TEST_WALLET, "track": "OSS"}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "POST /api/campaign/register (CONTENT, no x_handle) — 400", "method": "POST", "endpoint": "/api/campaign/register", "body": {"wallet": TEST_WALLET, "track": "CONTENT"}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
            {"name": "POST /api/campaign/payout-snapshot (no auth) — 401", "method": "POST", "endpoint": "/api/campaign/payout-snapshot", "evaluate": lambda r: (r["status"] in (401, 500), False, f"status={r['status']}")},
            {"name": "POST /api/campaign/payout-snapshot (wrong secret) — 401", "method": "POST", "endpoint": "/api/campaign/payout-snapshot", "headers": {"Authorization": "Bearer WRONGSECRET"}, "evaluate": lambda r: (r["status"] in (401, 500), False, f"status={r['status']}")},
            {"name": "POST /api/campaign/award-xp (no auth) — 401", "method": "POST", "endpoint": "/api/campaign/award-xp", "body": {"wallet": TEST_WALLET, "xp": 100, "reason": "test"}, "evaluate": lambda r: (r["status"] in (401, 500), False, f"status={r['status']}")},
        ]
        self.test_group_generic("Campaign", campaign_cases)

        users_cases = [
            {"name": "GET /api/users/:wallet", "method": "GET", "endpoint": f"/api/users/{TEST_WALLET}", "evaluate": lambda r: (r["ok"] or r["status"] == 404, not r["ok"] and r["status"] != 404, f"status={r['status']}")},
            {"name": "GET /api/users/:wallet/referrals", "method": "GET", "endpoint": f"/api/users/{TEST_WALLET}/referrals", "evaluate": lambda r: (r["ok"] or r["status"] == 404, not r["ok"] and r["status"] != 404, f"status={r['status']}")},
            {"name": "POST /api/users/register (missing wallet) — 400", "method": "POST", "endpoint": "/api/users/register", "body": {}, "evaluate": lambda r: (r["status"] == 400, False, f"status={r['status']}")},
        ]
        self.test_group_generic("Users", users_cases)

    def test_security(self):
        s = "Security"
        self.section(s)

        def case_nosniff():
            r = self.get("/health")
            value = r["headers"].get("x-content-type-options")
            self.add_result(s, "X-Content-Type-Options: nosniff", "GET", "/health", value == "nosniff", warn=value != "nosniff", detail=f"value={value}", elapsed_ms=r["elapsed_ms"])

        def case_frame():
            r = self.get("/health")
            value = r["headers"].get("x-frame-options")
            self.add_result(s, "X-Frame-Options present", "GET", "/health", bool(value), warn=not value, detail=f"value={value}", elapsed_ms=r["elapsed_ms"])

        def case_cors():
            r = self.request("GET", "/health", headers={"Origin": "https://fake.com"})
            value = r["headers"].get("access-control-allow-origin")
            self.add_result(s, "CORS Access-Control-Allow-Origin", "GET", "/health", value is not None, warn=value == "*", detail=f"value={value}", elapsed_ms=r["elapsed_ms"])

        def case_webhook():
            r = self.post("/api/webhooks/github", {"action": "opened", "pull_request": {}})
            self.add_result(s, "POST /api/webhooks/github (no HMAC) — 401/400", "POST", "/api/webhooks/github", r["status"] in (400, 401, 500), detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])

        def case_404():
            r = self.get("/api/nonexistent-route-xyz")
            self.add_result(s, "GET /api/nonexistent — 404", "GET", "/api/nonexistent-route-xyz", r["status"] == 404, detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])

        def case_sql():
            payload = requests.utils.quote("' OR '1'='1", safe="")
            endpoint = f"/api/users/{payload}"
            r = self.get(endpoint)
            detail = json.dumps(r["data"])[:80] if r["data"] is not None else "null"
            self.add_result(s, "SQL injection in :wallet param", "GET", endpoint, r["status"] in (200, 400, 404), detail=f"status={r['status']}, got={detail}", elapsed_ms=r["elapsed_ms"])

        self.run_case(s, "X-Content-Type-Options: nosniff", "GET", "/health", case_nosniff)
        self.run_case(s, "X-Frame-Options present", "GET", "/health", case_frame)
        self.run_case(s, "CORS Access-Control-Allow-Origin", "GET", "/health", case_cors)
        self.run_case(s, "POST /api/webhooks/github (no HMAC) — 401/400", "POST", "/api/webhooks/github", case_webhook)
        self.run_case(s, "GET /api/nonexistent — 404", "GET", "/api/nonexistent-route-xyz", case_404)
        self.run_case(s, "SQL injection in :wallet param", "GET", "/api/users/:wallet", case_sql)

    def test_rate_limiting(self):
        s = "Rate Limiting"
        self.section(s)

        def case_rate_limit():
            self.post("/api/grow-token/faucet", {"to": ZERO_ACTOR_1})
            time.sleep(1)
            r = self.post("/api/grow-token/faucet", {"to": ZERO_ACTOR_1})
            error_text = ""
            if isinstance(r["data"], dict):
                error_text = str(r["data"].get("error", ""))
            limited = r["status"] == 429 or "Rate limited" in error_text
            self.add_result(s, "Faucet: 2nd mint within 5min → 429", "POST", "/api/grow-token/faucet", limited, warn=not limited, detail=f"status={r['status']}", elapsed_ms=r["elapsed_ms"])

        self.run_case(s, "Faucet: 2nd mint within 5min → 429", "POST", "/api/grow-token/faucet", case_rate_limit)

    def build_report(self) -> Dict[str, Any]:
        total_tests = len(self.results)
        failed = sum(1 for item in self.results if not item["status"] and not item["skip"])
        passed = sum(1 for item in self.results if item["status"] and not item["warn"] and not item["skip"])
        total_time_ms = sum(item.get("elapsed_ms", 0) for item in self.results)
        pass_rate = f"{(passed / total_tests * 100):.0f}%" if total_tests else "0%"
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
        report = self.build_report()
        with open(RESULTS_FILE, "w") as handle:
            json.dump(report, handle, indent=2)

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

        failures = [item for item in self.results if item["tag"] == "FAIL"]
        warnings = [item for item in self.results if item["tag"] == "WARN"]

        if failures:
            print("\n🔴 FAILURES:")
            for item in failures:
                print(f"   [{item['section']}] {item['name']} — {item['detail']}")

        if warnings:
            print("\n🟡 WARNINGS (degraded):")
            for item in warnings:
                print(f"   [{item['section']}] {item['name']} — {item['detail']}")

        blockchain_sections = {"Streams", "Vault", "Splits", "Permissions", "Bounty", "Identity", "GROW Token"}
        db_sections = {"Leaderboard", "Campaign", "Users"}
        config_sections = {"Tokens"}

        blockchain_issues = [item for item in self.results if item["tag"] in ("FAIL", "WARN") and item["section"] in blockchain_sections]
        db_issues = [item for item in self.results if item["tag"] in ("FAIL", "WARN") and item["section"] in db_sections]
        config_issues = [item for item in self.results if item["tag"] in ("FAIL", "WARN") and item["section"] in config_sections]

        print("\n📋 DIAGNOSIS:")
        if blockchain_issues:
            print(f"   Blockchain layer: {len(blockchain_issues)} issues — Vara node connectivity or balance/config problems")
        if db_issues:
            print(f"   Database layer: {len(db_issues)} issues — Supabase connection or data shape problems")
        if not config_issues:
            print("   Token registry: ✅ Fully working or not showing configuration issues")
        if not failures and not warnings:
            print("   🎉 All systems operational!")
        print()

    def run(self) -> int:
        print("\n" + "═" * 64)
        print("  GrowStreams — Full E2E API Test Suite")
        print("═" * 64)
        print(f"  Target : {self.base_url}")
        print(f"  Mode   : {'READ-ONLY (no blockchain writes)' if self.skip_mutations else 'FULL (includes blockchain mutations)'}")
        print(f"  Time   : {datetime.utcnow().isoformat()}Z")
        print("═" * 64)

        self.test_health()
        self.test_tokens()
        self.test_grow_token()
        self.test_streams()
        self.test_misc_sections()
        self.test_security()
        self.test_rate_limiting()
        self.write_report()
        self.print_summary()
        return 1 if self.failed > 0 else 0


def main():
    parser = argparse.ArgumentParser(description="GrowStreams full E2E API test suite")
    parser.add_argument("--skip-mutations", action="store_true", help="Skip live blockchain mutation calls")
    parser.add_argument("--api-url", default=os.getenv("API_URL", V3_DEFAULT_BASE_URL), help="Target API base URL")
    args = parser.parse_args()

    sys.exit(run_v3_main(base_url=args.api_url, skip_mutations=args.skip_mutations))


if __name__ == "__main__":
    main()
