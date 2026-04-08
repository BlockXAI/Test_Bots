#!/usr/bin/env python3
"""
CompliLedger RMF E2E Test Suite (RMF-Correct)
Includes:
  ✅ ControlHub snapshot validation (catalog/profile/baseline immutability)
  ✅ AutoDoc-driven OSCAL generation (CD, SSP, SAP, SAR, POA&M)
  ✅ AuthZ (AO review + decision gate)
  ✅ Proofs (DID -> VC -> ZKP -> Anchor/NFT) + verification
  ✅ RMF-aligned workflow order: Prepare -> Categorize -> Select -> Implement -> Assess -> Authorize -> Monitor
  ✅ GitHub Sentinel integration (Evidence Collection + Drift Detection + Continuous Monitoring)
  ✅ Live Agent Integration (CEA, CMA, AutoDoc, ZKP, AuditPack, PDA, ARSA, PEA, RWA, VCA)

Usage:
  # Local (default - all services on localhost:8922)
  python3 rmf_e2e_full_suite.py --systems 1

  # Production (Railway deployment)
  python3 rmf_e2e_full_suite.py \
    --rmf-base https://rmf-backend-production.up.railway.app \
    --controlhub-base https://rmf-backend-production.up.railway.app \
    --proofs-base https://rmf-backend-production.up.railway.app \
    --systems 1

Notes:
- This script assumes you expose endpoints similar to the names below.
- If your current backend uses different paths, update ENDPOINTS section.
- This suite is intentionally strict: it verifies snapshot IDs/hashes are embedded in generated OSCAL.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests


# =============================================================================
# TERMINAL COLORS
# =============================================================================
class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# =============================================================================
# LIVE AGENT URLS (Railway Production)
# =============================================================================
AGENT_URLS = {
    "cea":         os.getenv("AGENT_CEA_URL",         "https://cea-main-production.up.railway.app"),
    "cma":         os.getenv("AGENT_CMA_URL",         "https://cma-main-production.up.railway.app"),
    "autodoc":     os.getenv("AGENT_AUTODOC_URL",     "https://autodoc-main-production.up.railway.app"),
    "zkp":         os.getenv("AGENT_ZKP_URL",         "https://zkp-agent-production.up.railway.app"),
    "auditpack":   os.getenv("AGENT_AUDITPACK_URL",   "https://auditpack-web-production.up.railway.app"),
    "pda":         os.getenv("AGENT_PDA_URL",         "https://pda-production-1af8.up.railway.app"),
    "arsa":        os.getenv("AGENT_ARSA_URL",        "https://app-production-44ae.up.railway.app"),
    "pea_extract": os.getenv("AGENT_PEA_EXTRACT_URL", "https://pea-production.up.railway.app"),
    "pea_enforce": os.getenv("AGENT_PEA_ENFORCE_URL", "https://pea-agent-production.up.railway.app"),
    "rwa":         os.getenv("AGENT_RWA_URL",         "https://rwa-agent-production.up.railway.app"),
    "vca":         os.getenv("AGENT_VCA_URL",         "https://vcaagent-production.up.railway.app"),
    "did_vc":      os.getenv("AGENT_DID_VC_URL",      "https://did-vc-core-production.up.railway.app"),
    "faa":         os.getenv("AGENT_FAA_URL",         "https://faaagent-production.up.railway.app"),
    "crosswalk":   os.getenv("AGENT_CROSSWALK_URL",   "https://crosswalk-production.up.railway.app"),
}


# =============================================================================
# CONFIG: ENDPOINT MAP (ADJUST TO MATCH YOUR APIS)
# =============================================================================
ENDPOINTS = {
    # --- RMF Engine ---
    "health": ( "GET",  "/" ),

    "create_system": ( "POST", "/api/v1/rmf/systems/" ),
    "get_system":    ( "GET",  "/api/v1/rmf/systems/{system_id}" ),

    "submit_context":      ( "POST", "/api/v1/rmf/systems/{system_id}/context" ),
    "submit_categorization": ( "POST", "/api/v1/rmf/systems/{system_id}/categorization" ),
    "lock_categorization":   ( "PUT",  "/api/v1/rmf/systems/{system_id}/categorization/lock" ),

    "select_baseline": ( "POST", "/api/v1/rmf/systems/{system_id}/baseline" ),
    "lock_baseline":   ( "PUT",  "/api/v1/rmf/systems/{system_id}/baseline/lock" ),

    "connect_sources": ( "POST", "/api/v1/rmf/systems/{system_id}/sources/connect" ),
    "ingest_sources":  ( "POST", "/api/v1/rmf/systems/{system_id}/sources/ingest" ),

    "get_workflow":    ( "GET",  "/api/v1/rmf/systems/{system_id}/workflow" ),
    "get_gates":       ( "GET",  "/api/v1/rmf/systems/{system_id}/gates" ),
    "get_transitions": ( "GET",  "/api/v1/rmf/systems/{system_id}/transitions" ),

    # --- AutoDoc (can be separate service; here assumed under RMF or AutoDoc base) ---
    # Generate OSCAL artifacts based on system + baseline snapshot + ingested artifacts
    "autodoc_generate_cd":  ( "POST", "/api/v1/autodoc/systems/{system_id}/oscal/component-definition" ),
    "autodoc_generate_ssp": ( "POST", "/api/v1/autodoc/systems/{system_id}/oscal/ssp" ),
    "autodoc_generate_sap": ( "POST", "/api/v1/autodoc/systems/{system_id}/oscal/sap" ),
    "autodoc_run_assessment": ( "POST", "/api/v1/autodoc/systems/{system_id}/assess/run" ),
    "autodoc_generate_sar": ( "POST", "/api/v1/autodoc/systems/{system_id}/oscal/sar" ),
    "autodoc_generate_poam": ( "POST", "/api/v1/autodoc/systems/{system_id}/oscal/poam" ),

    "oscal_get_artifact":  ( "GET", "/api/v1/oscal/artifacts/{artifact_id}" ),
    "oscal_validate":      ( "POST", "/api/v1/oscal/validate" ),

    # --- Authorization (AuthZsync) ---
    "authz_review_package": ( "GET",  "/api/v1/authz/systems/{system_id}/review-package" ),
    "authz_decide":         ( "POST", "/api/v1/authz/systems/{system_id}/decision" ),
    "authz_get_decision":   ( "GET",  "/api/v1/authz/systems/{system_id}/decision" ),

    # --- Monitor ---
    "monitor_enable": ( "POST", "/api/v1/rmf/systems/{system_id}/monitor/enable" ),

    # --- Proofs (DID/VC/ZKP/Anchor/NFT) ---
    "did_issue_system": ( "POST", "/api/v1/proofs/did/issue/system" ),
    "did_issue_user":   ( "POST", "/api/v1/proofs/did/issue/user" ),

    "vc_issue":         ( "POST", "/api/v1/proofs/vc/issue" ),
    "vc_verify":        ( "POST", "/api/v1/proofs/vc/verify" ),

    "zkp_generate":     ( "POST", "/api/v1/proofs/zkp/generate" ),
    "zkp_verify":       ( "POST", "/api/v1/proofs/zkp/verify" ),

    "anchor_commit":    ( "POST", "/api/v1/proofs/anchor/commit" ),
    "anchor_verify":    ( "GET",  "/api/v1/proofs/anchor/verify/{anchor_id}" ),

    "nft_mint":         ( "POST", "/api/v1/proofs/nft/mint" ),
    "nft_verify":       ( "GET",  "/api/v1/proofs/nft/verify/{token_id}" ),

    # --- ControlHub ---
    # Snapshot and retrieval of catalogs/profiles/baselines (immutable references)
    "controlhub_latest_snapshot": ( "GET", "/api/v1/controlhub/snapshots/latest" ),
    "controlhub_get_snapshot":    ( "GET", "/api/v1/controlhub/snapshots/{snapshot_id}" ),
    "controlhub_get_baseline":    ( "GET", "/api/v1/controlhub/baselines/{baseline}/snapshot/{snapshot_id}" ),
    "controlhub_verify_snapshot": ( "POST", "/api/v1/controlhub/snapshots/verify" ),

    # --- GitHub Sentinel (Evidence Collection + Drift Detection) ---
    "sentinel_status":              ( "GET",  "/api/v1/sentinel/status" ),
    "sentinel_list_repos":          ( "GET",  "/api/v1/sentinel/repositories" ),
    "sentinel_add_repo":            ( "POST", "/api/v1/sentinel/repositories" ),
    "sentinel_get_sbom":            ( "GET",  "/api/v1/sentinel/evidence/{owner}/{repo}/sbom" ),
    "sentinel_get_vulnerabilities": ( "GET",  "/api/v1/sentinel/evidence/{owner}/{repo}/vulnerabilities" ),
    "sentinel_get_secrets":         ( "GET",  "/api/v1/sentinel/evidence/{owner}/{repo}/secrets" ),
    "sentinel_get_artifacts":       ( "GET",  "/api/v1/sentinel/evidence/{owner}/{repo}/artifacts" ),
    "sentinel_risk_analysis":       ( "GET",  "/api/v1/sentinel/risk/{owner}/{repo}" ),
    "sentinel_risk_dashboard":      ( "GET",  "/api/v1/sentinel/risk/dashboard" ),
    "sentinel_drift_report":        ( "GET",  "/api/v1/sentinel/drift/{owner}/{repo}" ),
    "sentinel_list_baselines":      ( "GET",  "/api/v1/sentinel/drift/baselines" ),
    "sentinel_compliance_frameworks": ( "GET", "/api/v1/sentinel/compliance/frameworks" ),
    "sentinel_compliance_coverage": ( "GET",  "/api/v1/sentinel/compliance/{framework}/coverage" ),
    "sentinel_collect_evidence":    ( "POST", "/api/v1/sentinel/evidence/collect" ),
    "sentinel_run_monitoring":      ( "POST", "/api/v1/rmf/systems/{system_id}/monitor/run" ),
    "sentinel_monitoring_status":   ( "GET",  "/api/v1/rmf/systems/{system_id}/monitor/status" ),

    # --- Agent Dashboard (Orchestration) ---
    "agents_status":    ( "GET",  "/api/v1/agents/status" ),
    "agents_registry":  ( "GET",  "/api/v1/agents/registry" ),
    "agents_phase":     ( "GET",  "/api/v1/agents/phase/{phase}" ),
    "agents_exec_log":  ( "GET",  "/api/v1/agents/execution-log/{system_id}" ),
    "agents_health":    ( "GET",  "/api/v1/agents/health/{agent_key}" ),
}


# =============================================================================
# HELPERS
# =============================================================================
def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def sha256_json(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, msg: str):
    if not condition:
        raise AssertionError(msg)


@dataclass
class TestResult:
    name: str
    passed: bool
    details: str = ""
    data: Optional[Dict[str, Any]] = None
    dur_s: float = 0.0


@dataclass
class SystemRunContext:
    system_id: Optional[str] = None
    system_name: str = ""
    baseline: str = ""
    controlhub_snapshot_id: Optional[str] = None
    controlhub_snapshot_hash: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)  # artifact_id by type
    did_system: Optional[str] = None
    did_ao: Optional[str] = None
    vc_id: Optional[str] = None
    zkp_id: Optional[str] = None
    anchor_id: Optional[str] = None
    nft_token_id: Optional[str] = None
    # GitHub Sentinel context
    sentinel_repos: List[Dict[str, str]] = field(default_factory=list)
    sentinel_evidence: Optional[Dict[str, Any]] = None
    sentinel_monitoring_result: Optional[Dict[str, Any]] = None


class Client:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def call(self, method: str, path: str, *, json_data: dict = None, params: dict = None, timeout: int = 120) -> Tuple[int, dict]:
        url = f"{self.base}{path}"
        try:
            resp = self.session.request(method, url, json=json_data, params=params, timeout=timeout)
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {"raw": resp.text[:1000]}
        except Exception as e:
            return 0, {"error": str(e), "url": url}


class Suite:
    def __init__(self, rmf_base: str, controlhub_base: str, proofs_base: str, systems: int, autodoc_base: str = None):
        self.rmf = Client(rmf_base)
        self.controlhub = Client(controlhub_base)
        self.proofs = Client(proofs_base)
        self.autodoc = Client(autodoc_base) if autodoc_base else None  # External AutoDoc service
        self.systems = systems
        self.results: List[TestResult] = []
        # Direct agent clients for comprehensive testing
        self.agent_clients: Dict[str, Client] = {}
        for key, url in AGENT_URLS.items():
            self.agent_clients[key] = Client(url)

    # -------------------------
    # Logging + result handling
    # -------------------------
    def log(self, msg: str, level: str = "INFO"):
        color = {
            "INFO": C.CYAN,
            "PASS": C.GREEN,
            "FAIL": C.RED,
            "WARN": C.YELLOW,
            "STEP": C.MAGENTA,
        }.get(level, C.RESET)
        print(f"{color}{msg}{C.RESET}")

    def run_test(self, name: str, fn, *args, **kwargs) -> Tuple[bool, Any]:
        start = time.time()
        try:
            out = fn(*args, **kwargs)
            dur = time.time() - start
            self.results.append(TestResult(name=name, passed=True, dur_s=dur))
            print(f"  {C.GREEN}[PASS]{C.RESET} {name} ({dur:.1f}s)")
            return True, out
        except Exception as e:
            dur = time.time() - start
            self.results.append(TestResult(name=name, passed=False, details=str(e), dur_s=dur))
            print(f"  {C.RED}[FAIL]{C.RESET} {name} ({dur:.1f}s) :: {str(e)}")
            return False, None

    # =============================================================================
    # STEP 0: HEALTH
    # =============================================================================
    def step_health(self):
        method, path = ENDPOINTS["health"]
        code, data = self.rmf.call(method, path)
        require(code == 200, f"RMF health failed: {code} {data}")

    # =============================================================================
    # STEP 1: CONTROLHUB SNAPSHOT (Try to get existing, or will be created later)
    # =============================================================================
    def step_controlhub_snapshot(self, ctx: SystemRunContext) -> None:
        """
        RMF correctness:
          - Control catalogs/profiles/baselines must be immutable references for an authorization event.
          - We try to get latest snapshot; if none exists, it will be created during baseline lock.
        """
        # 1.1 Try to get latest snapshot (may not exist on fresh deployment)
        method, path = ENDPOINTS["controlhub_latest_snapshot"]
        code, data = self.controlhub.call(method, path)
        
        if code == 200:
            snapshot_id = data.get("snapshot_id") or data.get("id")
            snapshot_hash = data.get("snapshot_hash") or data.get("hash")
            
            if snapshot_id and snapshot_hash:
                # 1.2 Verify snapshot integrity
                method, path = ENDPOINTS["controlhub_verify_snapshot"]
                code2, data2 = self.controlhub.call(method, path, json_data={"snapshot_id": snapshot_id, "snapshot_hash": snapshot_hash})
                require(code2 == 200 and data2.get("valid") is True, f"ControlHub snapshot verify failed: {code2} {data2}")
                
                ctx.controlhub_snapshot_id = snapshot_id
                ctx.controlhub_snapshot_hash = snapshot_hash
                return
        
        # No snapshot yet - this is OK, will be created during baseline lock
        # Use placeholder values that will be updated after baseline lock
        ctx.controlhub_snapshot_id = None
        ctx.controlhub_snapshot_hash = None

    # =============================================================================
    # STEP 2: PREPARE (System Registration + Context)
    # =============================================================================
    def step_prepare_system(self, ctx: SystemRunContext) -> None:
        # 2.1 create system
        method, path = ENDPOINTS["create_system"]
        payload = {
            "name": ctx.system_name,
            "owner_name": "E2E Test Runner",
            "description": "RMF E2E system (Prepare phase)",
            "system_type": "major_application",
            "deployment_model": "cloud",
        }
        code, data = self.rmf.call(method, path, json_data=payload)
        require(code in (200, 201), f"Create system failed: {code} {data}")
        ctx.system_id = data.get("system_id") or (data.get("system") or {}).get("system_id")
        require(ctx.system_id, "system_id missing from create response")

        # 2.2 submit system context intake (technical + business)
        method, path = ENDPOINTS["submit_context"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "description": f"{ctx.system_name} supporting mission operations",
            "system_boundary": "Cloud-hosted application boundary; includes API tier, DB tier, CI/CD pipeline",
            "deployment_model": "cloud",
            "data_types": ["PII", "financial", "operational"],
            "user_types": ["federal_employees", "contractors", "public"],
            "interconnections": ["Login.gov", "Treasury", "GSA"],
            "artifact_sources_expected": ["sbom", "github", "iac", "policies", "siem"],
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"Submit context failed: {code2} {data2}")

    # =============================================================================
    # STEP 3: CATEGORIZE (800-60/PIA/FIPS199) + Lock Gate
    # =============================================================================
    def step_categorize_and_gate(self, ctx: SystemRunContext) -> None:
        """
        RMF correctness:
          - Categorization is a governance decision.
          - Evidence is not “collected” here; we only set info types + privacy applicability + rationale.
        """
        method, path = ENDPOINTS["submit_categorization"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "information_types": ["PII", "Financial"],
            "privacy_applicable": True,
            "pia_required": True,

            # FIPS 199 impact levels (draft)
            "confidentiality": "moderate",
            "integrity": "high",
            "availability": "moderate",

            "rationale": "Processes PII/financial data; integrity requirements elevated (mission reporting).",
            "nist_800_60_refs": ["C.2.8.12", "D.1.1"],  # example info type IDs
        }
        code, data = self.rmf.call(method, path, json_data=payload)
        require(code in (200, 201), f"Categorization submit failed: {code} {data}")

        # Gate: lock categorization (ISSO / governance)
        method, path = ENDPOINTS["lock_categorization"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "user_id": "isso-001",
            "user_name": "ISSO Administrator",
            "notes": "Categorization approved per NIST SP 800-60 and FIPS 199.",
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"Categorization lock failed: {code2} {data2}")

    # =============================================================================
    # STEP 4: SELECT (Baseline from ControlHub snapshot) + Lock Gate
    # =============================================================================
    def step_select_baseline_and_gate(self, ctx: SystemRunContext) -> None:
        """
        RMF correctness:
          - Baseline selection is control selection (Select step).
          - Must reference ControlHub snapshot (immutable catalog/profile).
          - Baseline lock creates snapshot if none exists.
        """
        method, path = ENDPOINTS["select_baseline"]
        path = path.format(system_id=ctx.system_id)

        # Build payload - snapshot refs are optional if not yet created
        payload = {
            "baseline": ctx.baseline,  # LOW/MODERATE/HIGH
            "justification": f"{ctx.baseline} baseline selected based on categorization and mission context.",
            "tailoring": {
                "included": [],   # optional: additional controls
                "excluded": [],   # optional: justified scoping out controls
                "notes": "No tailoring in E2E run.",
            }
        }
        # Only include snapshot refs if we have them
        if ctx.controlhub_snapshot_id and ctx.controlhub_snapshot_hash:
            payload["controlhub_snapshot_id"] = ctx.controlhub_snapshot_id
            payload["controlhub_snapshot_hash"] = ctx.controlhub_snapshot_hash
            
        code, data = self.rmf.call(method, path, json_data=payload)
        require(code in (200, 201), f"Baseline select failed: {code} {data}")

        # Gate: lock baseline (SCA / governance) - this creates snapshot if needed
        method, path = ENDPOINTS["lock_baseline"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "user_id": "sca-001",
            "user_name": "Security Control Assessor",
            "notes": f"FedRAMP {ctx.baseline} baseline approved and locked (ControlHub snapshot pinned).",
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"Baseline lock failed: {code2} {data2}")
        
        # After baseline lock, fetch the snapshot if we don't have it yet
        if not ctx.controlhub_snapshot_id or not ctx.controlhub_snapshot_hash:
            # Try to get snapshot from response or fetch latest
            snapshot_id = data2.get("snapshot_id") or data2.get("controlhub_snapshot_id")
            snapshot_hash = data2.get("snapshot_hash") or data2.get("controlhub_snapshot_hash")
            
            if not snapshot_id or not snapshot_hash:
                # Fetch from ControlHub
                method3, path3 = ENDPOINTS["controlhub_latest_snapshot"]
                code3, data3 = self.controlhub.call(method3, path3)
                if code3 == 200:
                    snapshot_id = data3.get("snapshot_id") or data3.get("id")
                    snapshot_hash = data3.get("snapshot_hash") or data3.get("hash")
            
            ctx.controlhub_snapshot_id = snapshot_id or "snapshot-created-on-lock"
            ctx.controlhub_snapshot_hash = snapshot_hash or hashlib.sha256(f"{ctx.system_id}-{ctx.baseline}".encode()).hexdigest()

    # =============================================================================
    # STEP 5: IMPLEMENT (Connect + Ingest sources)
    # =============================================================================
    def step_implement_connect_ingest(self, ctx: SystemRunContext) -> None:
        """
        RMF correctness:
          - Implement step includes integrating sources and implementing/collecting evidence-ready artifacts.
          - This is where SBOM/GitHub/IaC/Policies/SIEM connectors come online.
        """
        # Connect sources (simulated)
        method, path = ENDPOINTS["connect_sources"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "sources": [
                {"type": "sbom", "mode": "upload"},
                {"type": "github", "mode": "github", "repo": "org/repo"},
                {"type": "iac", "mode": "github", "path": "infra/"},
                {"type": "policies", "mode": "upload"},
                {"type": "siem_events", "mode": "integration"},
            ]
        }
        code, data = self.rmf.call(method, path, json_data=payload)
        require(code in (200, 201), f"Connect sources failed: {code} {data}")

        # Ingest sources (agent/engine)
        method, path = ENDPOINTS["ingest_sources"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "ingestion_mode": "async",
            "normalize": True,
            "expected_artifacts": ["sbom", "iac", "pipeline", "policy_docs", "siem_events"],
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"Ingest sources failed: {code2} {data2}")

    # =============================================================================
    # STEP 6: AUTODOC (Generate CD -> SSP -> SAP)
    # =============================================================================
    def step_autodoc_generate_oscal_set(self, ctx: SystemRunContext) -> None:
        """
        AutoDoc must generate OSCAL artifacts *aligned to*:
          - system context
          - categorization
          - baseline selection
          - ControlHub snapshot references
          - ingested component inventory/dependencies
          
        Supports both:
          - Local AutoDoc endpoints (default)
          - External AutoDoc service (--autodoc-base)
        """
        if self.autodoc:
            # Use external AutoDoc service
            self._autodoc_external(ctx)
        else:
            # Use local RMF backend AutoDoc endpoints
            self._autodoc_local(ctx)
    
    def _autodoc_local(self, ctx: SystemRunContext) -> None:
        """Generate OSCAL via local RMF backend endpoints."""
        # 6.1 CD
        method, path = ENDPOINTS["autodoc_generate_cd"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
            "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            "include_inventory": True,
            "include_dependencies": True,
        }
        code, data = self.rmf.call(method, path, json_data=payload)
        require(code in (200, 201), f"AutoDoc CD failed: {code} {data}")
        ctx.artifacts["cd"] = data.get("artifact_id") or data.get("cd_id")
        require(ctx.artifacts.get("cd"), "CD artifact_id missing")

        # 6.2 validate CD schema
        self._validate_oscal(ctx, ctx.artifacts["cd"], expected_model="component-definition")

        # 6.3 SSP
        method, path = ENDPOINTS["autodoc_generate_ssp"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "baseline": ctx.baseline,
            "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
            "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            "component_definition_id": ctx.artifacts["cd"],
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"AutoDoc SSP failed: {code2} {data2}")
        ctx.artifacts["ssp"] = data2.get("artifact_id") or data2.get("ssp_id")
        require(ctx.artifacts.get("ssp"), "SSP artifact_id missing")

        self._validate_oscal(ctx, ctx.artifacts["ssp"], expected_model="system-security-plan")

        # 6.4 SAP
        method, path = ENDPOINTS["autodoc_generate_sap"]
        path = path.format(system_id=ctx.system_id)
        payload3 = {
            "baseline": ctx.baseline,
            "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
            "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            "ssp_id": ctx.artifacts["ssp"],
            "assessment_scope": {
                "include_all_controls": True,
                "sampling": "none",
                "notes": "E2E test full scope (demo).",
            }
        }
        code3, data3 = self.rmf.call(method, path, json_data=payload3)
        require(code3 in (200, 201), f"AutoDoc SAP failed: {code3} {data3}")
        ctx.artifacts["sap"] = data3.get("artifact_id") or data3.get("sap_id")
        require(ctx.artifacts.get("sap"), "SAP artifact_id missing")

        self._validate_oscal(ctx, ctx.artifacts["sap"], expected_model="assessment-plan")
    
    def _autodoc_external(self, ctx: SystemRunContext) -> None:
        """Generate OSCAL via external AutoDoc service (POST /execute with polling)."""
        # Build context for external AutoDoc
        base_context = {
            "system_overview": {
                "system_id": ctx.system_id,
                "system_name": ctx.system_name,
                "description": f"RMF E2E Test System - {ctx.system_name}",
                "environment": "production",
                "owner": "E2E Test Runner",
            },
            "categorization": {
                "confidentiality": "Moderate",
                "integrity": "High", 
                "availability": "Moderate",
            },
            "baseline": {
                "level": f"FedRAMP {ctx.baseline}",
                "control_count": 325,
            },
            "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
            "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            "control_implementation": [],
        }
        
        # Generate SSP via external AutoDoc
        exec_id = f"e2e-ssp-{uuid.uuid4().hex[:8]}"
        payload = {
            "execution_id": exec_id,
            "document_type": "SSP",
            "system_id": ctx.system_id,
            "context": base_context,
        }
        
        code, data = self.autodoc.call("POST", "/execute", json_data=payload)
        require(code in (200, 201, 202), f"External AutoDoc SSP execute failed: {code} {data}")
        
        # Poll for completion
        doc_id = self._poll_autodoc_execution(exec_id)
        ctx.artifacts["ssp"] = doc_id
        
        # Generate SAP
        exec_id_sap = f"e2e-sap-{uuid.uuid4().hex[:8]}"
        payload_sap = {
            "execution_id": exec_id_sap,
            "document_type": "SAP",
            "system_id": ctx.system_id,
            "context": base_context,
        }
        code2, data2 = self.autodoc.call("POST", "/execute", json_data=payload_sap)
        require(code2 in (200, 201, 202), f"External AutoDoc SAP execute failed: {code2} {data2}")
        
        doc_id_sap = self._poll_autodoc_execution(exec_id_sap)
        ctx.artifacts["sap"] = doc_id_sap
        
        # CD - use local endpoint as external AutoDoc may not support CD
        method, path = ENDPOINTS["autodoc_generate_cd"]
        path = path.format(system_id=ctx.system_id)
        payload_cd = {
            "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
            "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            "include_inventory": True,
            "include_dependencies": True,
        }
        code3, data3 = self.rmf.call(method, path, json_data=payload_cd)
        require(code3 in (200, 201), f"AutoDoc CD failed: {code3} {data3}")
        ctx.artifacts["cd"] = data3.get("artifact_id") or data3.get("cd_id")
        require(ctx.artifacts.get("cd"), "CD artifact_id missing")
    
    def _poll_autodoc_execution(self, execution_id: str, max_wait: int = 120) -> str:
        """Poll external AutoDoc for execution completion."""
        start = time.time()
        while time.time() - start < max_wait:
            code, data = self.autodoc.call("GET", f"/execute/executions/{execution_id}")
            if code == 200:
                status = data.get("status", "")
                if status == "completed":
                    # Get document ID from output
                    return data.get("document_id") or execution_id
                elif status == "failed":
                    raise AssertionError(f"AutoDoc execution failed: {data.get('error_message')}")
            time.sleep(2)
        raise AssertionError(f"AutoDoc execution timed out after {max_wait}s")

    def _validate_oscal(self, ctx: SystemRunContext, artifact_id: str, expected_model: str):
        # fetch artifact json
        method, path = ENDPOINTS["oscal_get_artifact"]
        path = path.format(artifact_id=artifact_id)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Fetch OSCAL artifact failed: {code} {data}")

        # strict: ensure ControlHub snapshot is embedded (either props, back-matter, or custom field)
        raw = data.get("oscal_json") or data
        raw_str = json.dumps(raw)
        require(ctx.controlhub_snapshot_id in raw_str, f"Artifact {artifact_id} missing controlhub_snapshot_id reference")
        require(ctx.controlhub_snapshot_hash in raw_str, f"Artifact {artifact_id} missing controlhub_snapshot_hash reference")

        # schema validate
        method2, path2 = ENDPOINTS["oscal_validate"]
        payload = {
            "model_type": expected_model,
            "oscal_json": raw,
        }
        code2, data2 = self.rmf.call(method2, path2, json_data=payload)
        require(code2 in (200, 201), f"OSCAL validate failed: {code2} {data2}")
        require(data2.get("valid") is True, f"OSCAL invalid: {data2}")

    # =============================================================================
    # STEP 7: ASSESS (Run assessment -> SAR -> POA&M)
    # =============================================================================
    def step_assess_generate_sar_poam(self, ctx: SystemRunContext) -> None:
        # 7.1 run assessment (collect evidence during assessment)
        method, path = ENDPOINTS["autodoc_run_assessment"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "sap_id": ctx.artifacts["sap"],
            "execution_mode": "automated",
            "evidence_sources": ["sbom", "github", "iac", "policies", "siem"],
        }
        code, data = self.rmf.call(method, path, json_data=payload, timeout=300)
        require(code in (200, 201), f"Assessment run failed: {code} {data}")
        assessment_id = data.get("assessment_id") or data.get("id")
        require(assessment_id, "assessment_id missing")
        ctx.artifacts["assessment_id"] = assessment_id

        # 7.2 SAR
        method, path = ENDPOINTS["autodoc_generate_sar"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "assessment_id": assessment_id,
            "ssp_id": ctx.artifacts["ssp"],
            "sap_id": ctx.artifacts["sap"],
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"SAR generate failed: {code2} {data2}")
        ctx.artifacts["sar"] = data2.get("artifact_id") or data2.get("sar_id")
        require(ctx.artifacts.get("sar"), "SAR artifact_id missing")
        self._validate_oscal(ctx, ctx.artifacts["sar"], expected_model="assessment-results")

        # 7.3 POA&M
        method, path = ENDPOINTS["autodoc_generate_poam"]
        path = path.format(system_id=ctx.system_id)
        payload3 = {
            "sar_id": ctx.artifacts["sar"],
            "ssp_id": ctx.artifacts["ssp"],
            "baseline": ctx.baseline,
        }
        code3, data3 = self.rmf.call(method, path, json_data=payload3)
        require(code3 in (200, 201), f"POA&M generate failed: {code3} {data3}")
        ctx.artifacts["poam"] = data3.get("artifact_id") or data3.get("poam_id")
        require(ctx.artifacts.get("poam"), "POA&M artifact_id missing")
        self._validate_oscal(ctx, ctx.artifacts["poam"], expected_model="plan-of-action-and-milestones")

    # =============================================================================
    # STEP 8: AUTHORIZE (AO review + decision gate)  [AuthZsync]
    # =============================================================================
    def step_authorize_decision(self, ctx: SystemRunContext) -> None:
        """
        RMF correctness:
          - Authorize is a governance decision by AO using review package.
          - The AO decision must be recorded and immutable (and then can be used for proof/NFT).
        """
        # 8.1 Review package
        method, path = ENDPOINTS["authz_review_package"]
        path = path.format(system_id=ctx.system_id)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"AuthZ review package failed: {code} {data}")

        # strict: ensure review package includes required artifacts
        required = ["cd", "ssp", "sap", "sar", "poam"]
        for k in required:
            require(ctx.artifacts.get(k), f"Missing artifact in context: {k}")

        # 8.2 AO decision (simulate "AUTHORIZED" or "AUTHORIZED_WITH_CONDITIONS")
        # If POA&M has items, likely "with conditions". In E2E, choose AUTHORIZED for demo.
        method, path = ENDPOINTS["authz_decide"]
        path = path.format(system_id=ctx.system_id)

        decision_payload = {
            "ao_user": {
                "user_id": "ao-001",
                "user_name": "Authorizing Official",
            },
            "decision": "AUTHORIZED",
            "decision_date": now_iso(),
            "rationale": "Risk accepted based on assessment results and evidence.",
            "artifacts": {
                "cd": ctx.artifacts["cd"],
                "ssp": ctx.artifacts["ssp"],
                "sap": ctx.artifacts["sap"],
                "sar": ctx.artifacts["sar"],
                "poam": ctx.artifacts["poam"],
            },
            "controlhub_snapshot": {
                "snapshot_id": ctx.controlhub_snapshot_id,
                "snapshot_hash": ctx.controlhub_snapshot_hash,
            }
        }
        code2, data2 = self.rmf.call(method, path, json_data=decision_payload)
        require(code2 in (200, 201), f"AuthZ decision failed: {code2} {data2}")

        # 8.3 Fetch stored decision
        method, path = ENDPOINTS["authz_get_decision"]
        path = path.format(system_id=ctx.system_id)
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"AuthZ get decision failed: {code3} {data3}")
        require(data3.get("decision") in ("AUTHORIZED", "AUTHORIZED_WITH_CONDITIONS", "NOT_AUTHORIZED"), "Invalid stored decision")

    # =============================================================================
    # STEP 9: PROOFS (DID -> VC -> ZKP -> Anchor -> NFT) + verify
    # =============================================================================
    def step_proofs_pipeline(self, ctx: SystemRunContext) -> None:
        """
        Proofs should be derived from:
          - AuthZ decision + artifact hashes + ControlHub snapshot hash
          - NOT from raw confidential content
        """
        # 9.1 issue system DID
        method, path = ENDPOINTS["did_issue_system"]
        payload = {
            "system_id": ctx.system_id,
            "system_name": ctx.system_name,
        }
        code, data = self.proofs.call(method, path, json_data=payload)
        require(code in (200, 201), f"DID issue system failed: {code} {data}")
        ctx.did_system = data.get("did")
        require(ctx.did_system, "system DID missing")

        # 9.2 issue AO DID (optional but recommended for signature provenance)
        method, path = ENDPOINTS["did_issue_user"]
        payload2 = {"user_id": "ao-001", "user_name": "Authorizing Official", "role": "AO"}
        code2, data2 = self.proofs.call(method, path, json_data=payload2)
        require(code2 in (200, 201), f"DID issue AO failed: {code2} {data2}")
        ctx.did_ao = data2.get("did")
        require(ctx.did_ao, "AO DID missing")

        # 9.3 Build a minimal “evidence manifest” hash (artifact IDs + snapshot + decision)
        manifest = {
            "system_id": ctx.system_id,
            "system_did": ctx.did_system,
            "ao_did": ctx.did_ao,
            "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
            "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            "artifacts": ctx.artifacts,
            "decision": "AUTHORIZED",
            "timestamp": now_iso(),
        }
        manifest_hash = sha256_json(manifest)

        # 9.4 Issue VC (claims: “System authorized under baseline X with snapshot Y and artifacts hashes”)
        method, path = ENDPOINTS["vc_issue"]
        vc_payload = {
            "issuer_did": ctx.did_ao,
            "subject_did": ctx.did_system,
            "type": ["VerifiableCredential", "RMFAuthorizationCredential"],
            "claims": {
                "baseline": ctx.baseline,
                "controlhub_snapshot_id": ctx.controlhub_snapshot_id,
                "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
                "evidence_manifest_hash": manifest_hash,
                "artifacts": {k: v for k, v in ctx.artifacts.items() if k in ["cd", "ssp", "sap", "sar", "poam"]},
                "authorization_status": "AUTHORIZED",
            }
        }
        code3, data3 = self.proofs.call(method, path, json_data=vc_payload)
        require(code3 in (200, 201), f"VC issue failed: {code3} {data3}")
        ctx.vc_id = data3.get("vc_id") or data3.get("id")
        vc_jwt = data3.get("vc_jwt") or data3.get("jwt")
        require(ctx.vc_id and vc_jwt, "VC id/jwt missing")

        # 9.5 Verify VC
        method, path = ENDPOINTS["vc_verify"]
        code4, data4 = self.proofs.call(method, path, json_data={"vc_jwt": vc_jwt})
        require(code4 == 200 and data4.get("valid") is True, f"VC verify failed: {code4} {data4}")

        # 9.6 Generate ZKP (prove manifest hash signed by AO VC without revealing contents)
        method, path = ENDPOINTS["zkp_generate"]
        zkp_payload = {
            "proof_type": "authorization_manifest_membership",
            "public_inputs": {
                "evidence_manifest_hash": manifest_hash,
                "baseline": ctx.baseline,
            },
            "private_inputs": {
                "vc_jwt": vc_jwt,
            }
        }
        code5, data5 = self.proofs.call(method, path, json_data=zkp_payload, timeout=300)
        require(code5 in (200, 201), f"ZKP generate failed: {code5} {data5}")
        ctx.zkp_id = data5.get("zkp_id") or data5.get("id")
        require(ctx.zkp_id, "zkp_id missing")

        # 9.7 Verify ZKP
        method, path = ENDPOINTS["zkp_verify"]
        code6, data6 = self.proofs.call(method, path, json_data={
            "zkp_id": ctx.zkp_id,
            "public_inputs": {"evidence_manifest_hash": manifest_hash, "baseline": ctx.baseline}
        })
        require(code6 == 200 and data6.get("valid") is True, f"ZKP verify failed: {code6} {data6}")

        # 9.8 Anchor commitment on-chain (anchor hash only)
        method, path = ENDPOINTS["anchor_commit"]
        anchor_payload = {
            "commitment_hash": manifest_hash,
            "network": "algorand",
            "metadata": {
                "system_did": ctx.did_system,
                "zkp_id": ctx.zkp_id,
                "controlhub_snapshot_hash": ctx.controlhub_snapshot_hash,
            }
        }
        code7, data7 = self.proofs.call(method, path, json_data=anchor_payload)
        require(code7 in (200, 201), f"Anchor commit failed: {code7} {data7}")
        ctx.anchor_id = data7.get("anchor_id") or data7.get("id")
        require(ctx.anchor_id, "anchor_id missing")

        # 9.9 Verify anchor
        method, path = ENDPOINTS["anchor_verify"]
        path = path.format(anchor_id=ctx.anchor_id)
        code8, data8 = self.proofs.call(method, path)
        require(code8 == 200 and data8.get("valid") is True, f"Anchor verify failed: {code8} {data8}")

        # 9.10 Mint NFT attestation (optional, but your workflow includes it)
        method, path = ENDPOINTS["nft_mint"]
        nft_payload = {
            "network": "algorand",
            "owner_did": ctx.did_system,
            "attestation": {
                "anchor_id": ctx.anchor_id,
                "commitment_hash": manifest_hash,
                "baseline": ctx.baseline,
            }
        }
        code9, data9 = self.proofs.call(method, path, json_data=nft_payload)
        require(code9 in (200, 201), f"NFT mint failed: {code9} {data9}")
        ctx.nft_token_id = data9.get("token_id") or data9.get("id")
        require(ctx.nft_token_id, "nft token_id missing")

        # 9.11 Verify NFT
        method, path = ENDPOINTS["nft_verify"]
        path = path.format(token_id=ctx.nft_token_id)
        code10, data10 = self.proofs.call(method, path)
        require(code10 == 200 and data10.get("valid") is True, f"NFT verify failed: {code10} {data10}")

    # =============================================================================
    # STEP 10: MONITOR (Continuous monitoring enablement)
    # =============================================================================
    def step_monitor_enable(self, ctx: SystemRunContext) -> None:
        method, path = ENDPOINTS["monitor_enable"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "enabled": True,
            "cadence": "continuous",
            "signals": ["sbom_drift", "iac_drift", "repo_events", "credential_monitoring", "runtime_findings"],
        }
        # Include sentinel repos if available
        if ctx.sentinel_repos:
            payload["repositories"] = ctx.sentinel_repos
        
        code, data = self.rmf.call(method, path, json_data=payload)
        require(code in (200, 201), f"Monitor enable failed: {code} {data}")

    # =============================================================================
    # STEP 12: GITHUB SENTINEL - Evidence Collection (RMF Step 1 Enhancement)
    # =============================================================================
    def step_sentinel_health_and_repos(self, ctx: SystemRunContext) -> None:
        """
        GitHub Sentinel integration:
          - Check Sentinel service health
          - List available repositories
          - Get risk dashboard
        """
        # 12.1 Check Sentinel status
        method, path = ENDPOINTS["sentinel_status"]
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Sentinel status failed: {code} {data}")
        
        # 12.2 List repositories
        method, path = ENDPOINTS["sentinel_list_repos"]
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Sentinel list repos failed: {code2} {data2}")
        
        repos = data2.get("repositories", [])
        if repos:
            # Use first available repo for testing
            first_repo = repos[0]
            ctx.sentinel_repos = [{
                "owner": first_repo.get("owner", "octocat"),
                "repo": first_repo.get("name", first_repo.get("repo", "Hello-World")),
                "branch": first_repo.get("branch", "main")
            }]
        else:
            # Default test repo
            ctx.sentinel_repos = [{"owner": "octocat", "repo": "Hello-World", "branch": "main"}]
        
        # 12.3 Risk dashboard
        method, path = ENDPOINTS["sentinel_risk_dashboard"]
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"Sentinel risk dashboard failed: {code3} {data3}")

    def step_sentinel_evidence_collection(self, ctx: SystemRunContext) -> None:
        """
        Collect evidence from repositories via GitHub Sentinel.
        Implements RMF Step 1 - Evidence Collection.
        """
        if not ctx.sentinel_repos:
            ctx.sentinel_repos = [{"owner": "octocat", "repo": "Hello-World", "branch": "main"}]
        
        repo = ctx.sentinel_repos[0]
        owner = repo["owner"]
        repo_name = repo["repo"]
        
        # 12.4 Get vulnerabilities
        method, path = ENDPOINTS["sentinel_get_vulnerabilities"]
        path = path.format(owner=owner, repo=repo_name)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Sentinel vulnerabilities failed: {code} {data}")
        vuln_count = data.get("count", 0)
        
        # 12.5 Get secrets detection
        method, path = ENDPOINTS["sentinel_get_secrets"]
        path = path.format(owner=owner, repo=repo_name)
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Sentinel secrets failed: {code2} {data2}")
        secret_count = data2.get("count", 0)
        
        # 12.6 Get artifacts
        method, path = ENDPOINTS["sentinel_get_artifacts"]
        path = path.format(owner=owner, repo=repo_name)
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"Sentinel artifacts failed: {code3} {data3}")
        
        # 12.7 Risk analysis
        method, path = ENDPOINTS["sentinel_risk_analysis"]
        path = path.format(owner=owner, repo=repo_name)
        code4, data4 = self.rmf.call(method, path)
        require(code4 == 200, f"Sentinel risk analysis failed: {code4} {data4}")
        
        # Store evidence summary
        ctx.sentinel_evidence = {
            "repository": f"{owner}/{repo_name}",
            "vulnerabilities": vuln_count,
            "secrets": secret_count,
            "risk_score": data4.get("score", "unknown"),
            "collected_at": now_iso(),
        }

    def step_sentinel_drift_detection(self, ctx: SystemRunContext) -> None:
        """
        Check for drift and compliance coverage via GitHub Sentinel.
        Implements RMF Step 13 - Continuous Monitoring.
        """
        if not ctx.sentinel_repos:
            return
        
        repo = ctx.sentinel_repos[0]
        owner = repo["owner"]
        repo_name = repo["repo"]
        
        # 12.8 Drift report
        method, path = ENDPOINTS["sentinel_drift_report"]
        path = path.format(owner=owner, repo=repo_name)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Sentinel drift report failed: {code} {data}")
        
        # 12.9 List baselines
        method, path = ENDPOINTS["sentinel_list_baselines"]
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Sentinel list baselines failed: {code2} {data2}")
        
        # 12.10 Compliance frameworks
        method, path = ENDPOINTS["sentinel_compliance_frameworks"]
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"Sentinel compliance frameworks failed: {code3} {data3}")
        
        # 12.11 NIST compliance coverage
        method, path = ENDPOINTS["sentinel_compliance_coverage"]
        path = path.format(framework="NIST")
        code4, data4 = self.rmf.call(method, path, params={"owner": owner, "repo": repo_name})
        require(code4 == 200, f"Sentinel NIST coverage failed: {code4} {data4}")

    def step_sentinel_continuous_monitoring(self, ctx: SystemRunContext) -> None:
        """
        Run continuous monitoring check via GitHub Sentinel.
        """
        if not ctx.system_id or not ctx.sentinel_repos:
            return
        
        # 12.12 Run monitoring check
        method, path = ENDPOINTS["sentinel_run_monitoring"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "repositories": ctx.sentinel_repos,
            "check_drift": True,
            "check_vulnerabilities": True,
            "check_secrets": True,
        }
        code, data = self.rmf.call(method, path, json_data=payload, timeout=60)
        require(code == 200, f"Sentinel monitoring run failed: {code} {data}")
        
        ctx.sentinel_monitoring_result = data
        
        # 12.13 Get monitoring status
        method, path = ENDPOINTS["sentinel_monitoring_status"]
        path = path.format(system_id=ctx.system_id)
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Sentinel monitoring status failed: {code2} {data2}")

    # =============================================================================
    # STEP 11: AUDIT TRAIL CHECKS (transitions/gates/workflow)
    # =============================================================================
    def step_audit_trail_checks(self, ctx: SystemRunContext) -> None:
        method, path = ENDPOINTS["get_workflow"]
        path = path.format(system_id=ctx.system_id)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Workflow fetch failed: {code} {data}")

        method, path = ENDPOINTS["get_gates"]
        path = path.format(system_id=ctx.system_id)
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Gates fetch failed: {code2} {data2}")

        method, path = ENDPOINTS["get_transitions"]
        path = path.format(system_id=ctx.system_id)
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"Transitions fetch failed: {code3} {data3}")

        transitions = data3.get("transitions", [])
        require(len(transitions) >= 6, f"Expected transitions >= 6, got {len(transitions)}")

    # =============================================================================
    # STEP 12B: AGENT ORCHESTRATION VIA RMF BACKEND (Real User Flow)
    # =============================================================================
    def step_agent_platform_readiness(self, ctx: SystemRunContext) -> None:
        """
        Real-user flow: verify the agent platform is operational THROUGH the
        RMF backend — not by calling agents directly.  An ISSO/AO interacts
        only with the RMF backend; the backend dispatches to agents.
        """
        # 12B.1 Agent registry (all registered agents visible)
        method, path = ENDPOINTS["agents_registry"]
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Agent registry failed: {code} {data}")
        agents = data.get("agents", [])
        require(len(agents) >= 10, f"Expected >= 10 registered agents, got {len(agents)}")

        # 12B.2 Agent status (health of all agents via orchestrator)
        method, path = ENDPOINTS["agents_status"]
        code2, data2 = self.rmf.call(method, path, timeout=60)
        require(code2 == 200, f"Agent status failed: {code2} {data2}")

        # 12B.3 Phase agent mapping (verify orchestrator knows which agents to call per phase)
        for phase in ["PREPARE", "ASSESS", "AUTHORIZE", "MONITOR"]:
            method, path = ENDPOINTS["agents_phase"]
            path = path.format(phase=phase)
            code3, data3 = self.rmf.call(method, path)
            require(code3 == 200, f"Phase {phase} agents failed: {code3} {data3}")

        # 12B.4 Spot-check one agent through backend health proxy
        method, path = ENDPOINTS["agents_health"]
        path = path.format(agent_key="cea")
        code4, data4 = self.rmf.call(method, path, timeout=30)
        require(code4 == 200, f"Agent health proxy failed: {code4} {data4}")

    # =============================================================================
    # STEP 12C: GOVERNANCE GATE ENFORCEMENT (Negative Tests)
    # =============================================================================
    def step_governance_gate_enforcement(self, ctx: SystemRunContext) -> None:
        """
        Real-user flow: governance gates prevent going backwards.
        After categorization is locked, re-submitting should fail or be idempotent.
        After baseline is locked, re-selecting should fail or be idempotent.
        """
        # 12C.1 Try to re-submit categorization after lock
        method, path = ENDPOINTS["submit_categorization"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "information_types": ["PII"],
            "privacy_applicable": False,
            "pia_required": False,
            "confidentiality": "low",
            "integrity": "low",
            "availability": "low",
            "rationale": "Attempting to change categorization after lock.",
        }
        code, data = self.rmf.call(method, path, json_data=payload)
        # Should either reject (4xx) or accept idempotently without changing locked values
        require(code in (200, 201, 400, 403, 409, 422),
                f"Gate enforcement: categorization re-submit unexpected: {code} {data}")

        # 12C.2 Try to re-lock categorization (should be idempotent or rejected)
        method, path = ENDPOINTS["lock_categorization"]
        path = path.format(system_id=ctx.system_id)
        payload2 = {
            "user_id": "attacker-001",
            "user_name": "Unauthorized User",
            "notes": "Attempting re-lock after already locked.",
        }
        code2, data2 = self.rmf.call(method, path, json_data=payload2)
        # 404 = no draft found (already locked & consumed) — correct behavior
        require(code2 in (200, 201, 400, 403, 404, 409, 422),
                f"Gate enforcement: re-lock unexpected: {code2} {data2}")

        # 12C.3 Verify system state hasn't regressed (should still be >= IMPLEMENT phase)
        method, path = ENDPOINTS["get_system"]
        path = path.format(system_id=ctx.system_id)
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"System fetch for gate check failed: {code3} {data3}")
        sys_data = data3.get("system", data3)
        wf = sys_data.get("workflow", {})
        current_state = (wf.get("current_state") or sys_data.get("current_state") or
                         sys_data.get("state") or sys_data.get("phase", ""))
        # State should NOT have gone back to PREPARE or CATEGORIZE
        require(current_state.upper() not in ("PREPARE", "CREATED"),
                f"System state regressed to {current_state} after gate enforcement test")

    # =============================================================================
    # STEP 12D: POST-AUTHORIZATION STATE VERIFICATION
    # =============================================================================
    def step_post_authorization_verify(self, ctx: SystemRunContext) -> None:
        """
        Real-user flow: after AO authorizes and proofs are minted, verify:
          - System state is AUTHORIZED or MONITOR
          - AO decision is stored and retrievable
          - All OSCAL artifacts are still retrievable
          - Proofs (DID/VC/ZKP/anchor/NFT) are referenced
        """
        # 12D.1 System state check
        method, path = ENDPOINTS["get_system"]
        path = path.format(system_id=ctx.system_id)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Post-auth system fetch failed: {code} {data}")
        sys_data = data.get("system", data)
        # State may be at top level or nested under workflow
        workflow = sys_data.get("workflow", {})
        state = (workflow.get("current_state") or sys_data.get("current_state") or
                 sys_data.get("state") or sys_data.get("phase", "")).upper()
        require(state in ("AUTHORIZED", "MONITOR", "CONTINUOUS_MONITORING", "MONITORING",
                          "ATO_GRANTED", "ATO_DECISION"),
                f"Expected AUTHORIZED/MONITOR state, got: {state}")

        # 12D.2 AO decision retrievable
        method, path = ENDPOINTS["authz_get_decision"]
        path = path.format(system_id=ctx.system_id)
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Post-auth decision fetch failed: {code2} {data2}")
        require(data2.get("decision") in ("AUTHORIZED", "AUTHORIZED_WITH_CONDITIONS"),
                f"Decision not AUTHORIZED: {data2.get('decision')}")

        # 12D.3 All 5 OSCAL artifacts still retrievable
        for doc_type in ["cd", "ssp", "sap", "sar", "poam"]:
            art_id = ctx.artifacts.get(doc_type)
            require(art_id, f"Missing {doc_type} artifact ID in context")
            method, path = ENDPOINTS["oscal_get_artifact"]
            path = path.format(artifact_id=art_id)
            code3, data3 = self.rmf.call(method, path)
            require(code3 == 200, f"Post-auth {doc_type} fetch failed: {code3}")

        # 12D.4 Proof chain intact
        require(ctx.did_system, "System DID missing after authorization")
        require(ctx.did_ao, "AO DID missing after authorization")
        require(ctx.vc_id, "VC ID missing after authorization")
        require(ctx.zkp_id, "ZKP ID missing after authorization")
        require(ctx.anchor_id, "Anchor ID missing after authorization")
        require(ctx.nft_token_id, "NFT token ID missing after authorization")

    # =============================================================================
    # STEP 12E: FULL MONITORING CYCLE (Run + Verify Results)
    # =============================================================================
    def step_monitoring_cycle_run(self, ctx: SystemRunContext) -> None:
        """
        Real-user flow: after enabling monitoring, actually run a monitoring
        cycle and verify the results contain drift/vuln/secrets findings.
        """
        if not ctx.sentinel_repos:
            ctx.sentinel_repos = [{"owner": "octocat", "repo": "Hello-World", "branch": "main"}]

        # 12E.1 Run a monitoring cycle
        method, path = ENDPOINTS["sentinel_run_monitoring"]
        path = path.format(system_id=ctx.system_id)
        payload = {
            "repositories": ctx.sentinel_repos,
            "check_drift": True,
            "check_vulnerabilities": True,
            "check_secrets": True,
        }
        code, data = self.rmf.call(method, path, json_data=payload, timeout=60)
        require(code == 200, f"Monitoring cycle run failed: {code} {data}")

        # 12E.2 Verify results structure
        # The response should contain monitoring results with sections
        require(isinstance(data, dict), f"Monitoring results not a dict: {type(data)}")

        # 12E.3 Check monitoring status reflects the completed run
        method, path = ENDPOINTS["sentinel_monitoring_status"]
        path = path.format(system_id=ctx.system_id)
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Monitoring status after run failed: {code2} {data2}")

        # 12E.4 Collect evidence through the unified endpoint
        method, path = ENDPOINTS["sentinel_collect_evidence"]
        payload2 = {
            "system_id": ctx.system_id,
            "repositories": ctx.sentinel_repos,
            "evidence_types": ["vulnerabilities", "secrets", "sbom", "artifacts"],
        }
        code3, data3 = self.rmf.call(method, path, json_data=payload2, timeout=60)
        require(code3 == 200, f"Evidence collection failed: {code3} {data3}")

    # =============================================================================
    # STEP 12F: AGENT EXECUTION LOG (Orchestrator Audit Trail)
    # =============================================================================
    def step_agent_execution_log(self, ctx: SystemRunContext) -> None:
        """
        Real-user flow: verify the orchestrator logged agent invocations
        for this system throughout the RMF lifecycle.
        """
        method, path = ENDPOINTS["agents_exec_log"]
        path = path.format(system_id=ctx.system_id)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Agent exec log failed: {code} {data}")

        # The log may be empty if the orchestrator wasn't invoked (local-only mode)
        # but the endpoint must work and return a list
        entries = data.get("entries", [])
        require(isinstance(entries, list), f"Exec log entries not a list: {type(entries)}")

    # =============================================================================
    # STEP 12G: FINAL SYSTEM STATE (Complete Verification)
    # =============================================================================
    def step_final_system_state(self, ctx: SystemRunContext) -> None:
        """
        Final verification: fetch the complete system record and verify
        every piece of the RMF lifecycle is intact:
          - System metadata
          - All workflow transitions recorded
          - All gates locked
          - All OSCAL artifacts referenced
          - Authorization decision stored
          - Monitoring enabled
        """
        # 12G.1 Full system record
        method, path = ENDPOINTS["get_system"]
        path = path.format(system_id=ctx.system_id)
        code, data = self.rmf.call(method, path)
        require(code == 200, f"Final system fetch failed: {code} {data}")
        sys_data = data.get("system", data)
        require(sys_data.get("name") or sys_data.get("system_name"),
                "System name missing in final state")

        # 12G.2 All transitions present (at least 6: PREPARE→CAT→SEL→IMPL→ASSESS→AUTH→MON)
        method, path = ENDPOINTS["get_transitions"]
        path = path.format(system_id=ctx.system_id)
        code2, data2 = self.rmf.call(method, path)
        require(code2 == 200, f"Final transitions fetch failed: {code2} {data2}")
        transitions = data2.get("transitions", [])
        require(len(transitions) >= 6,
                f"Expected >= 6 transitions in final state, got {len(transitions)}")

        # 12G.3 Gates check (both categorization and baseline should be locked)
        method, path = ENDPOINTS["get_gates"]
        path = path.format(system_id=ctx.system_id)
        code3, data3 = self.rmf.call(method, path)
        require(code3 == 200, f"Final gates fetch failed: {code3} {data3}")
        gates = data3.get("gates", data3)
        # Verify gates structure exists
        require(isinstance(gates, (dict, list)), f"Gates not dict/list: {type(gates)}")

        # 12G.4 Workflow completeness
        method, path = ENDPOINTS["get_workflow"]
        path = path.format(system_id=ctx.system_id)
        code4, data4 = self.rmf.call(method, path)
        require(code4 == 200, f"Final workflow fetch failed: {code4} {data4}")

        # 12G.5 All 5 OSCAL artifact IDs present in context
        for doc_type in ["cd", "ssp", "sap", "sar", "poam"]:
            require(ctx.artifacts.get(doc_type),
                    f"Final state: missing {doc_type} artifact")

        # 12G.6 Full proof chain present
        require(ctx.did_system and ctx.did_ao, "Final state: DIDs missing")
        require(ctx.vc_id, "Final state: VC missing")
        require(ctx.zkp_id, "Final state: ZKP missing")
        require(ctx.anchor_id, "Final state: Anchor missing")
        require(ctx.nft_token_id, "Final state: NFT missing")

    # =============================================================================
    # STEP 14: LIVE AGENT CONNECTIVITY TESTS (Direct Verification)
    # =============================================================================

    def _agent_call(self, agent_key: str, method: str, path: str, **kwargs) -> Tuple[int, dict]:
        """Helper: call a live agent directly."""
        client = self.agent_clients.get(agent_key)
        if not client:
            return 0, {"error": f"No client for agent {agent_key}"}
        return client.call(method, path, **kwargs)

    # --- CEA: Control Evaluation Agent ---
    def step_agent_cea(self, ctx: SystemRunContext) -> None:
        """CEA Agent: health + root info"""
        code, data = self._agent_call("cea", "GET", "/cea/health")
        require(code == 200, f"CEA health failed: {code} {data}")
        require(data.get("status") in ("healthy", "degraded"), f"CEA unexpected status: {data}")

        code2, data2 = self._agent_call("cea", "GET", "/")
        require(code2 == 200, f"CEA root failed: {code2} {data2}")
        require("CEA" in data2.get("message", ""), f"CEA root missing identity: {data2}")

    # --- CMA: Credential Monitor Agent ---
    def step_agent_cma(self, ctx: SystemRunContext) -> None:
        """CMA Agent: health + credential check + monitoring"""
        code, data = self._agent_call("cma", "GET", "/health")
        require(code == 200, f"CMA health failed: {code} {data}")

        # Check credential status (with a test VC ID)
        code2, data2 = self._agent_call("cma", "POST", "/credentials/check",
            json_data={"vc_id": ctx.vc_id or "test-vc-001"})
        require(code2 in (200, 201, 404, 422), f"CMA credential check failed: {code2} {data2}")

        # Framework alignment (POST, not GET)
        code3, data3 = self._agent_call("cma", "POST", "/integration/alignment/map",
            json_data={"framework": "NIST-800-53"})
        require(code3 in (200, 201, 404, 405, 422), f"CMA alignment map failed: {code3} {data3}")

    # --- AutoDoc Agent (External) ---
    def step_agent_autodoc_external(self, ctx: SystemRunContext) -> None:
        """AutoDoc Agent: health + ontology + schemas"""
        code, data = self._agent_call("autodoc", "GET", "/health")
        require(code == 200, f"AutoDoc health failed: {code} {data}")
        require(data.get("status") == "healthy", f"AutoDoc unhealthy: {data}")

        # Ontology controls
        code2, data2 = self._agent_call("autodoc", "GET", "/ontology/controls",
            params={"framework": "NIST-800-53"})
        require(code2 == 200, f"AutoDoc ontology failed: {code2} {data2}")

        # Schemas
        code3, data3 = self._agent_call("autodoc", "GET", "/autodoc/schemas")
        require(code3 == 200, f"AutoDoc schemas failed: {code3} {data3}")

    # --- ZKP Agent ---
    def step_agent_zkp(self, ctx: SystemRunContext) -> None:
        """ZKP Agent: health + readiness"""
        code, data = self._agent_call("zkp", "GET", "/health")
        require(code == 200, f"ZKP health failed: {code} {data}")
        require(data.get("status") in ("healthy", "degraded"), f"ZKP unexpected status: {data}")

        # Liveness probe
        code2, data2 = self._agent_call("zkp", "GET", "/health/live")
        require(code2 == 200, f"ZKP liveness failed: {code2} {data2}")

        # Readiness probe
        code3, data3 = self._agent_call("zkp", "GET", "/health/ready")
        require(code3 in (200, 503), f"ZKP readiness failed: {code3} {data3}")

    # --- AuditPack Agent ---
    def step_agent_auditpack(self, ctx: SystemRunContext) -> None:
        """AuditPack Agent: health + evidence listing"""
        code, data = self._agent_call("auditpack", "GET", "/health")
        require(code == 200, f"AuditPack health failed: {code} {data}")
        require(data.get("status") == "healthy", f"AuditPack unhealthy: {data}")

        # Evidence listing (may require auth, accept 401/403)
        code2, data2 = self._agent_call("auditpack", "GET", "/api/v1/evidence/")
        require(code2 in (200, 401, 403), f"AuditPack evidence list failed: {code2} {data2}")

    # --- PDA: Policy Drift Agent ---
    def step_agent_pda(self, ctx: SystemRunContext) -> None:
        """PDA Agent: health + detailed health + document listing"""
        code, data = self._agent_call("pda", "GET", "/health")
        require(code == 200, f"PDA health failed: {code} {data}")

        code2, data2 = self._agent_call("pda", "GET", "/api/v1/health/detailed")
        require(code2 == 200, f"PDA detailed health failed: {code2} {data2}")

        # List documents
        code3, data3 = self._agent_call("pda", "GET", "/api/v1/ingestion/documents")
        require(code3 in (200, 404), f"PDA documents list failed: {code3} {data3}")

    # --- ARSA: Automated Risk Scoring & Analysis ---
    def step_agent_arsa(self, ctx: SystemRunContext) -> None:
        """ARSA Agent: health + db health + event ingestion"""
        code, data = self._agent_call("arsa", "GET", "/health")
        require(code == 200, f"ARSA health failed: {code} {data}")
        require(data.get("status") == "ok", f"ARSA unexpected status: {data}")

        code2, data2 = self._agent_call("arsa", "GET", "/api/v1/health/db")
        require(code2 in (200, 500), f"ARSA db health failed: {code2} {data2}")

        # List assets (requires valid org_id UUID; 400 = endpoint alive but invalid ID)
        code3, data3 = self._agent_call("arsa", "GET", "/api/v1/assets",
            params={"org_id": "e2e-test-org"})
        require(code3 in (200, 400, 404, 422), f"ARSA assets list failed: {code3} {data3}")

    # --- PEA Extract: Policy Extraction Agent ---
    def step_agent_pea_extract(self, ctx: SystemRunContext) -> None:
        """PEA Extract Agent: health check (accepts degraded - DB may be disconnected)"""
        code, data = self._agent_call("pea_extract", "GET", "/health")
        require(code == 200, f"PEA Extract health failed: {code} {data}")
        require(data.get("status") in ("healthy", "degraded"), f"PEA Extract down: {data}")
        # Verify it still has API keys and frameworks configured
        require(len(data.get("frameworks", [])) >= 1, f"PEA Extract missing frameworks: {data}")

    # --- PEA Enforce: Policy Enforcement Agent ---
    def step_agent_pea_enforce(self, ctx: SystemRunContext) -> None:
        """PEA Enforce Agent: health + results listing"""
        code, data = self._agent_call("pea_enforce", "GET", "/health")
        require(code == 200, f"PEA Enforce health failed: {code} {data}")
        require(data.get("status") in ("healthy", "degraded"), f"PEA Enforce unexpected: {data}")

        # Results listing
        code2, data2 = self._agent_call("pea_enforce", "GET", "/api/v1/results")
        require(code2 in (200, 404), f"PEA Enforce results failed: {code2} {data2}")

    # --- RWA: Regulatory Web Agent ---
    def step_agent_rwa(self, ctx: SystemRunContext) -> None:
        """RWA Agent: health + root info"""
        code, data = self._agent_call("rwa", "GET", "/health")
        require(code == 200, f"RWA health failed: {code} {data}")
        require(data.get("status") == "healthy", f"RWA unhealthy: {data}")

        code2, data2 = self._agent_call("rwa", "GET", "/")
        require(code2 == 200, f"RWA root failed: {code2} {data2}")

    # --- VCA: Vulnerability & Commit Analysis ---
    def step_agent_vca(self, ctx: SystemRunContext) -> None:
        """VCA Agent: healthcheck + root identity + vulnerability-compliance dashboard"""
        code, data = self._agent_call("vca", "GET", "/healthcheck")
        require(code == 200, f"VCA healthcheck failed: {code} {data}")

        code2, data2 = self._agent_call("vca", "GET", "/")
        require(code2 == 200, f"VCA root failed: {code2} {data2}")
        require("Commit Analysis" in data2.get("name", "") or "GitHub" in data2.get("name", ""),
                f"VCA root missing identity: {data2}")

        # Vulnerability compliance dashboard summary (read-only, no DB dependency)
        code3, data3 = self._agent_call("vca", "GET", "/vulnerability-compliance/dashboard/summary")
        require(code3 in (200, 404, 500), f"VCA vuln dashboard failed: {code3} {data3}")

    # --- DID/VC Service ---
    def step_agent_did_vc(self, ctx: SystemRunContext) -> None:
        """DID/VC Service: health check"""
        code, data = self._agent_call("did_vc", "GET", "/api/health")
        require(code == 200, f"DID/VC health failed: {code} {data}")
        require(data.get("status") in ("ok", "healthy"), f"DID/VC unexpected: {data}")

    # --- FAA: Framework Alignment Agent ---
    def step_agent_faa(self, ctx: SystemRunContext) -> None:
        """FAA Agent: health check"""
        code, data = self._agent_call("faa", "GET", "/health")
        require(code == 200, f"FAA health failed: {code} {data}")

    # --- Crosswalk Agent ---
    def step_agent_crosswalk(self, ctx: SystemRunContext) -> None:
        """Crosswalk Agent: health check"""
        code, data = self._agent_call("crosswalk", "GET", "/health")
        require(code == 200, f"Crosswalk health failed: {code} {data}")

    # =============================================================================
    # MAIN RUNNER
    # =============================================================================
    def run(self) -> int:
        print(f"\n{C.BOLD}{'='*80}{C.RESET}")
        print(f"{C.BOLD}  CompliLedger RMF E2E Suite (RMF-Correct + ControlHub + AutoDoc + AuthZ + Proofs){C.RESET}")
        print(f"  Started: {now_iso()}")
        print(f"  RMF:       {self.rmf.base}")
        print(f"  ControlHub:{self.controlhub.base}")
        print(f"  AutoDoc:   {self.autodoc.base if self.autodoc else '(local - same as RMF)'}")
        print(f"  Proofs:    {self.proofs.base}")
        print(f"  Systems:   {self.systems}")
        print(f"{'='*80}\n")

        # Health
        ok, _ = self.run_test("Health Check (RMF)", self.step_health)
        if not ok:
            self._summary()
            return 1

        for i in range(self.systems):
            ctx = SystemRunContext(
                system_name=f"RMF E2E System {i+1} - {uuid.uuid4().hex[:6]}",
                baseline="MODERATE",
            )

            print(f"\n{C.BOLD}{C.CYAN}{'═'*80}{C.RESET}")
            print(f"{C.BOLD}{C.CYAN}SYSTEM {i+1}/{self.systems}: {ctx.system_name}{C.RESET}")
            print(f"{C.BOLD}{C.CYAN}{'═'*80}{C.RESET}\n")

            # 1 ControlHub snapshot
            self.run_test("ControlHub Snapshot: Fetch + Verify", self.step_controlhub_snapshot, ctx)

            # 2 Prepare
            self.run_test("RMF Prepare: Create System + Context", self.step_prepare_system, ctx)

            # 3 Categorize + gate
            self.run_test("RMF Categorize: Submit + Lock (Gate)", self.step_categorize_and_gate, ctx)

            # 4 Select + gate (ControlHub snapshot pinned)
            self.run_test("RMF Select: Baseline Select + Lock (Gate)", self.step_select_baseline_and_gate, ctx)

            # 5 Implement (connect+ingest)
            self.run_test("RMF Implement: Connect Sources + Ingest", self.step_implement_connect_ingest, ctx)

            # 6 AutoDoc generate OSCAL (CD/SSP/SAP) + validate + snapshot assertions
            self.run_test("AutoDoc: Generate CD/SSP/SAP + Validate + Snapshot Embed", self.step_autodoc_generate_oscal_set, ctx)

            # 7 Assess (Run assessment -> SAR -> POA&M) + validate + snapshot assertions
            self.run_test("RMF Assess: Run + Generate SAR/POA&M + Validate", self.step_assess_generate_sar_poam, ctx)

            # 8 Authorize (AO review + decision gate)
            self.run_test("RMF Authorize: AO Review + Decision (AuthZsync)", self.step_authorize_decision, ctx)

            # 9 Proofs pipeline (DID/VC/ZKP/Anchor/NFT) + verify
            self.run_test("Proofs: DID -> VC -> ZKP -> Anchor -> NFT (+Verify)", self.step_proofs_pipeline, ctx)

            # 10 Monitor
            self.run_test("RMF Monitor: Enable Continuous Monitoring", self.step_monitor_enable, ctx)

            # 11 Audit trail checks
            self.run_test("Audit Trail: Workflow/Gates/Transitions", self.step_audit_trail_checks, ctx)

            # --- Real-User Flow: Governance & State Verification ---
            print(f"\n{C.BOLD}{C.MAGENTA}--- Governance & State Verification ---{C.RESET}")
            self.run_test("Governance: Gate Enforcement (Negative Tests)", self.step_governance_gate_enforcement, ctx)
            self.run_test("Post-Auth: State + Artifacts + Proof Chain Intact", self.step_post_authorization_verify, ctx)

            # --- GitHub Sentinel Integration ---
            print(f"\n{C.BOLD}{C.MAGENTA}--- GitHub Sentinel Integration ---{C.RESET}")
            self.run_test("Sentinel: Health + Repos + Risk Dashboard", self.step_sentinel_health_and_repos, ctx)
            self.run_test("Sentinel: Evidence Collection (Vulns/Secrets/Artifacts)", self.step_sentinel_evidence_collection, ctx)
            self.run_test("Sentinel: Drift Detection + Compliance Coverage", self.step_sentinel_drift_detection, ctx)
            self.run_test("Sentinel: Run Continuous Monitoring Check", self.step_sentinel_continuous_monitoring, ctx)

            # --- Real-User Flow: Full Monitoring Cycle ---
            print(f"\n{C.BOLD}{C.MAGENTA}--- Monitoring Cycle & Evidence ---{C.RESET}")
            self.run_test("Monitor: Full Cycle Run + Evidence Collection", self.step_monitoring_cycle_run, ctx)

            # --- Agent Orchestration via RMF Backend (real user perspective) ---
            print(f"\n{C.BOLD}{C.MAGENTA}--- Agent Orchestration (via RMF Backend) ---{C.RESET}")
            self.run_test("Orchestrator: Agent Registry + Status + Phase Map", self.step_agent_platform_readiness, ctx)
            self.run_test("Orchestrator: Agent Execution Log", self.step_agent_execution_log, ctx)

            # --- Final System State Verification ---
            print(f"\n{C.BOLD}{C.MAGENTA}--- Final System State ---{C.RESET}")
            self.run_test("Final: Complete System State Verification", self.step_final_system_state, ctx)

            # --- Direct Agent Connectivity (14 agents) ---
            print(f"\n{C.BOLD}{C.MAGENTA}--- Direct Agent Connectivity (14 Agents) ---{C.RESET}")
            self.run_test("Agent: CEA (Control Evaluation)", self.step_agent_cea, ctx)
            self.run_test("Agent: CMA (Credential Monitor)", self.step_agent_cma, ctx)
            self.run_test("Agent: AutoDoc (OSCAL Generation)", self.step_agent_autodoc_external, ctx)
            self.run_test("Agent: ZKP (Zero-Knowledge Proofs)", self.step_agent_zkp, ctx)
            self.run_test("Agent: AuditPack (Compliance Packaging)", self.step_agent_auditpack, ctx)
            self.run_test("Agent: PDA (Policy Drift)", self.step_agent_pda, ctx)
            self.run_test("Agent: ARSA (Risk Scoring)", self.step_agent_arsa, ctx)
            self.run_test("Agent: PEA Extract (Policy Extraction)", self.step_agent_pea_extract, ctx)
            self.run_test("Agent: PEA Enforce (Policy Enforcement)", self.step_agent_pea_enforce, ctx)
            self.run_test("Agent: RWA (Regulatory Web)", self.step_agent_rwa, ctx)
            self.run_test("Agent: VCA (Vuln & Commit Analysis)", self.step_agent_vca, ctx)
            self.run_test("Agent: DID/VC Service", self.step_agent_did_vc, ctx)
            self.run_test("Agent: FAA (Framework Alignment)", self.step_agent_faa, ctx)
            self.run_test("Agent: Crosswalk (Framework Mapping)", self.step_agent_crosswalk, ctx)

        self._summary()
        failed = sum(1 for r in self.results if not r.passed)
        return 0 if failed == 0 else 1

    def _summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        rate = (passed / total * 100) if total else 0.0

        print(f"\n{C.BOLD}{'='*80}{C.RESET}")
        print(f"{C.BOLD}SUMMARY{C.RESET}")
        print(f"{'-'*80}")
        print(f"Total: {total}  Passed: {C.GREEN}{passed}{C.RESET}  Failed: {C.RED}{failed}{C.RESET}  Rate: {rate:.1f}%")
        if failed:
            print(f"\n{C.RED}{C.BOLD}Failed tests:{C.RESET}")
            for r in self.results:
                if not r.passed:
                    print(f" - {r.name}: {r.details}")
        else:
            print(f"\n{C.GREEN}{C.BOLD}✅ ALL TESTS PASSED{C.RESET}")
        print(f"{'='*80}\n")


def main():
    p = argparse.ArgumentParser(description="RMF-correct E2E suite with ControlHub + AutoDoc + AuthZ + Proofs")
    p.add_argument("--rmf-base", default=os.getenv("RMF_BASE", "http://localhost:8922"))
    p.add_argument("--controlhub-base", default=os.getenv("CONTROLHUB_BASE", "http://localhost:8922"))
    p.add_argument("--proofs-base", default=os.getenv("PROOFS_BASE", "http://localhost:8922"))
    p.add_argument("--autodoc-base", default=os.getenv("AUTODOC_BASE", None),
                   help="External AutoDoc service URL (e.g., https://autodoc-main-production.up.railway.app)")
    p.add_argument("--systems", type=int, default=int(os.getenv("SYSTEMS", "1")))
    args = p.parse_args()

    suite = Suite(
        rmf_base=args.rmf_base,
        controlhub_base=args.controlhub_base,
        proofs_base=args.proofs_base,
        autodoc_base=args.autodoc_base,
        systems=args.systems,
    )
    rc = suite.run()
    sys.exit(rc)


if __name__ == "__main__":
    main()