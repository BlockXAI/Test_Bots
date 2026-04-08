import requests
import json
import time
import io
import sys
from PIL import Image, ImageDraw

BASE_URL = "https://joyo-cc-production.up.railway.app"
RESULTS = []
TEST_USER_ID = f"test_user_{int(time.time())}"
TEST_PLANT_ID = None  # Will be set after registration


def log(status, endpoint, method, detail, elapsed_ms, tx_hash=None):
    icon = "PASS" if status else "FAIL"
    entry = {
        "status": status,
        "endpoint": endpoint,
        "method": method,
        "detail": detail,
        "elapsed_ms": elapsed_ms,
    }
    if tx_hash:
        entry["tx_hash"] = tx_hash
    RESULTS.append(entry)
    print_detail = f"{detail}"
    if tx_hash:
        print_detail += f" TX:{tx_hash}"
    print(f"  [{icon}] {method} {endpoint} ({elapsed_ms}ms) - {print_detail}")


def create_test_image():
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.rectangle([395, 300, 405, 500], fill='#2d5016')
    draw.ellipse([300, 250, 400, 350], fill='#228b22')
    draw.ellipse([400, 250, 500, 350], fill='#228b22')
    draw.ellipse([350, 200, 450, 300], fill='#32cd32')
    try:
        draw.text((300, 50), "Bamboo Plant", fill='black')
    except Exception:
        pass
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 1. GET / (Index)
# ---------------------------------------------------------------------------
def test_index():
    print("\n--- 1. GET / (Index) ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json() if ok else r.text[:200]
        log(ok, "/", "GET", f"status={r.status_code} keys={list(body.keys()) if isinstance(body, dict) else body}", ms)
        return body
    except Exception as e:
        log(False, "/", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 2. GET /health
# ---------------------------------------------------------------------------
def test_health():
    print("\n--- 2. GET /health ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json() if ok else r.text[:200]
        log(ok, "/health", "GET", f"status={r.status_code} body={body}", ms)
        return body
    except Exception as e:
        log(False, "/health", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 3. GET /plants/catalog
# ---------------------------------------------------------------------------
def test_plant_catalog():
    print("\n--- 3. GET /plants/catalog ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/plants/catalog", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        plant_count = len(body.get("catalog", body.get("plants", [])))
        log(ok, "/plants/catalog", "GET", f"status={r.status_code} plants={plant_count}", ms)
        return body
    except Exception as e:
        log(False, "/plants/catalog", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 4. POST /plants/register
# ---------------------------------------------------------------------------
def test_register_plant():
    global TEST_PLANT_ID
    print("\n--- 4. POST /plants/register ---")
    start = time.time()
    try:
        data = {
            "user_id": TEST_USER_ID,
            "plant_type": "bamboo",
            "location": "Mumbai, India",
            "gps_latitude": 19.076,
            "gps_longitude": 72.8777,
            "name": "Test User",
            "email": "test@example.com",
        }
        r = requests.post(f"{BASE_URL}/plants/register", data=data, timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        TEST_PLANT_ID = body.get("plant_id") or body.get("plant", {}).get("id")
        log(ok, "/plants/register", "POST", f"status={r.status_code} plant_id={TEST_PLANT_ID} points={body.get('points_awarded')}", ms)
        return body
    except Exception as e:
        log(False, "/plants/register", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 5. GET /plants/{plant_id}
# ---------------------------------------------------------------------------
def test_get_plant():
    print("\n--- 5. GET /plants/{plant_id} ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}", "GET", "No plant_id from registration", 0)
        return
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/plants/{TEST_PLANT_ID}", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, f"/plants/{TEST_PLANT_ID}", "GET", f"status={r.status_code} type={body.get('plant',{}).get('plant_type', 'N/A')}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 6. GET /plants/user/{user_id}
# ---------------------------------------------------------------------------
def test_get_user_plants():
    print("\n--- 6. GET /plants/user/{user_id} ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/plants/user/{TEST_USER_ID}", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        count = len(body.get("plants", []))
        log(ok, f"/plants/user/{TEST_USER_ID}", "GET", f"status={r.status_code} plant_count={count}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/user/{TEST_USER_ID}", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 7. POST /plants/{plant_id}/planting-photo (AI Plant Recognition)
# ---------------------------------------------------------------------------
def test_planting_photo():
    print("\n--- 7. POST /plants/{plant_id}/planting-photo (AI Recognition) ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}/planting-photo", "POST", "No plant_id", 0)
        return
    start = time.time()
    try:
        img = create_test_image()
        files = {"image": ("plant.jpg", img, "image/jpeg")}
        data = {"gps_latitude": 19.076, "gps_longitude": 72.8777}
        r = requests.post(f"{BASE_URL}/plants/{TEST_PLANT_ID}/planting-photo", files=files, data=data, timeout=60)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        ai_result = body.get("ai_analysis") or body.get("recognition") or "present" if "species" in json.dumps(body).lower() else "none"
        log(ok, f"/plants/{TEST_PLANT_ID}/planting-photo", "POST", f"status={r.status_code} ai={ai_result} points={body.get('points_awarded')}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}/planting-photo", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 8. POST /plants/{plant_id}/health-scan (AI Health Diagnosis)
# ---------------------------------------------------------------------------
def test_health_scan():
    print("\n--- 8. POST /plants/{plant_id}/health-scan (AI Health) ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}/health-scan", "POST", "No plant_id", 0)
        return
    start = time.time()
    try:
        img = create_test_image()
        files = {"image": ("plant.jpg", img, "image/jpeg")}
        r = requests.post(f"{BASE_URL}/plants/{TEST_PLANT_ID}/health-scan", files=files, timeout=60)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        health_score = body.get("health_score") or body.get("ai_health", {}).get("health_score", "N/A")
        log(ok, f"/plants/{TEST_PLANT_ID}/health-scan", "POST", f"status={r.status_code} health_score={health_score} points={body.get('points_awarded')}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}/health-scan", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 9. POST /plants/{plant_id}/water (Watering)
# ---------------------------------------------------------------------------
def test_watering():
    print("\n--- 9. POST /plants/{plant_id}/water ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}/water", "POST", "No plant_id", 0)
        return
    start = time.time()
    try:
        img = create_test_image()
        files = {"video": ("water.jpg", img, "image/jpeg")}
        data = {"gps_latitude": 19.076, "gps_longitude": 72.8777}
        r = requests.post(f"{BASE_URL}/plants/{TEST_PLANT_ID}/water", files=files, data=data, timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, f"/plants/{TEST_PLANT_ID}/water", "POST", f"status={r.status_code} points={body.get('points_awarded')} streak={body.get('streak')}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}/water", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 10. POST /plants/{plant_id}/remedy-apply
# ---------------------------------------------------------------------------
def test_remedy_apply():
    print("\n--- 10. POST /plants/{plant_id}/remedy-apply ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}/remedy-apply", "POST", "No plant_id", 0)
        return
    start = time.time()
    try:
        img = create_test_image()
        files = {"image": ("remedy.jpg", img, "image/jpeg")}
        data = {"remedy_type": "neem_spray"}
        r = requests.post(f"{BASE_URL}/plants/{TEST_PLANT_ID}/remedy-apply", files=files, data=data, timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, f"/plants/{TEST_PLANT_ID}/remedy-apply", "POST", f"status={r.status_code} points={body.get('points_awarded')}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}/remedy-apply", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 11. POST /plants/{plant_id}/protection
# ---------------------------------------------------------------------------
def test_protection():
    print("\n--- 11. POST /plants/{plant_id}/protection ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}/protection", "POST", "No plant_id", 0)
        return
    start = time.time()
    try:
        img = create_test_image()
        files = {"image": ("protection.jpg", img, "image/jpeg")}
        data = {"protection_type": "netting"}
        r = requests.post(f"{BASE_URL}/plants/{TEST_PLANT_ID}/protection", files=files, data=data, timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, f"/plants/{TEST_PLANT_ID}/protection", "POST", f"status={r.status_code} points={body.get('points_awarded')}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}/protection", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 12. GET /users/{user_id}/points
# ---------------------------------------------------------------------------
def test_user_points():
    print("\n--- 12. GET /users/{user_id}/points ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/users/{TEST_USER_ID}/points", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, f"/users/{TEST_USER_ID}/points", "GET", f"status={r.status_code} total_points={body.get('total_points')}", ms)
        return body
    except Exception as e:
        log(False, f"/users/{TEST_USER_ID}/points", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 13. GET /users/{user_id}/history
# ---------------------------------------------------------------------------
def test_user_history():
    print("\n--- 13. GET /users/{user_id}/history ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/users/{TEST_USER_ID}/history?limit=10", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        activity_count = len(body.get("activities", body.get("history", [])))
        log(ok, f"/users/{TEST_USER_ID}/history", "GET", f"status={r.status_code} activities={activity_count}", ms)
        return body
    except Exception as e:
        log(False, f"/users/{TEST_USER_ID}/history", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 14. GET /stats
# ---------------------------------------------------------------------------
def test_stats():
    print("\n--- 14. GET /stats ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/stats", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, "/stats", "GET", f"status={r.status_code} keys={list(body.keys())[:6]}", ms)
        return body
    except Exception as e:
        log(False, "/stats", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 15. GET /stats/csr
# ---------------------------------------------------------------------------
def test_csr_stats():
    print("\n--- 15. GET /stats/csr ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/stats/csr", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, "/stats/csr", "GET", f"status={r.status_code} keys={list(body.keys())[:6]}", ms)
        return body
    except Exception as e:
        log(False, "/stats/csr", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 16. GET /weather
# ---------------------------------------------------------------------------
def test_weather():
    print("\n--- 16. GET /weather ---")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/weather", params={"latitude": 19.076, "longitude": 72.8777}, timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        temp = body.get("temperature") or body.get("weather", {}).get("temp", "N/A")
        log(ok, "/weather", "GET", f"status={r.status_code} temp={temp}", ms)
        return body
    except Exception as e:
        log(False, "/weather", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 17. POST /users/{user_id}/biometric
# ---------------------------------------------------------------------------
def test_biometric():
    print("\n--- 17. POST /users/{user_id}/biometric ---")
    start = time.time()
    try:
        data = {
            "signature": "biometric_test_hash_abc123def456",
            "gesture_count": 5,
            "confidence": 0.92,
        }
        r = requests.post(f"{BASE_URL}/users/{TEST_USER_ID}/biometric", data=data, timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        log(ok, f"/users/{TEST_USER_ID}/biometric", "POST", f"status={r.status_code} stored={body.get('stored') or body.get('success')}", ms)
        return body
    except Exception as e:
        log(False, f"/users/{TEST_USER_ID}/biometric", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 18. POST /verify/fraud-check (AI Fraud Detection)
# ---------------------------------------------------------------------------
def test_fraud_check():
    print("\n--- 18. POST /verify/fraud-check (AI Fraud Detection) ---")
    start = time.time()
    try:
        img = create_test_image()
        files = {"plant_image": ("plant.jpg", img, "image/jpeg")}
        data = {
            "plant_type": "bamboo",
            "location": "Mumbai, India",
            "gps_latitude": 19.076,
            "gps_longitude": 72.8777,
            "trees_planted": 1,
        }
        r = requests.post(f"{BASE_URL}/verify/fraud-check", files=files, data=data, timeout=60)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        valid = body.get("valid") or body.get("is_valid") or body.get("fraud_check", {}).get("valid")
        risk = body.get("risk_level") or body.get("fraud_check", {}).get("risk_level", "N/A")
        log(ok, "/verify/fraud-check", "POST", f"status={r.status_code} valid={valid} risk={risk}", ms)
        return body
    except Exception as e:
        log(False, "/verify/fraud-check", "POST", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 19. POST /nft/mint
# ---------------------------------------------------------------------------
def test_nft_mint():
    print("\n--- 19. POST /nft/mint ---")
    start = time.time()
    tx = "N/A"  # Initialize tx
    try:
        data = {
            "trees_planted": 1,
            "location": "Mumbai, India",
            "gps_coords": "19.076,72.8777",
            "worker_id": TEST_USER_ID,
            "plant_id": TEST_PLANT_ID or "test_plant",
            "gesture_signature": "biometric_test_hash_abc123def456",
        }
        r = requests.post(f"{BASE_URL}/nft/mint", data=data, timeout=60)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        tx = body.get("transaction_id") or body.get("tx_id") or body.get("nft", {}).get("transaction_id", "N/A")
        log(ok, "/nft/mint", "POST", f"status={r.status_code}", ms, tx_hash=str(tx)[:40])
        return body
    except Exception as e:
        log(False, "/nft/mint", "POST", str(e), int((time.time() - start) * 1000), tx_hash=str(tx)[:40])


# ---------------------------------------------------------------------------
# 20. GET /plants/{plant_id}/verification-report
# ---------------------------------------------------------------------------
def test_verification_report():
    print("\n--- 20. GET /plants/{plant_id}/verification-report ---")
    if not TEST_PLANT_ID:
        log(False, "/plants/{id}/verification-report", "GET", "No plant_id", 0)
        return
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/plants/{TEST_PLANT_ID}/verification-report", timeout=30)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        stages = body.get("stages_completed") or body.get("report", {}).get("stages", "N/A")
        log(ok, f"/plants/{TEST_PLANT_ID}/verification-report", "GET", f"status={r.status_code} stages={stages}", ms)
        return body
    except Exception as e:
        log(False, f"/plants/{TEST_PLANT_ID}/verification-report", "GET", str(e), int((time.time() - start) * 1000))


# ---------------------------------------------------------------------------
# 21. POST /verify/complete (Full 7-Stage Pipeline)
# ---------------------------------------------------------------------------
def test_complete_verification():
    print("\n--- 21. POST /verify/complete (FULL 7-STAGE PIPELINE) ---")
    start = time.time()
    try:
        img = create_test_image()
        files = {"plant_image": ("bamboo.jpg", img, "image/jpeg")}
        data = {
            "user_id": TEST_USER_ID,
            "plant_type": "bamboo",
            "location": "Mumbai, India",
            "gps_latitude": 19.076,
            "gps_longitude": 72.8777,
            "trees_planted": 1,
            "biometric_signature": "biometric_test_hash_abc123def456",
            "gesture_count": 5,
            "gesture_confidence": 0.92,
        }
        r = requests.post(f"{BASE_URL}/verify/complete", files=files, data=data, timeout=120)
        ms = int((time.time() - start) * 1000)
        ok = r.status_code == 200
        body = r.json()
        overall = body.get("status") or body.get("overall_status", "N/A")
        log(ok, "/verify/complete", "POST", f"status={r.status_code} overall={overall} duration={ms}ms", ms)
        # Print stage details
        stages = body.get("stages") or body.get("stage_results") or {}
        if isinstance(stages, dict):
            for stage_name, stage_data in stages.items():
                if isinstance(stage_data, dict):
                    s = stage_data.get("status") or stage_data.get("passed") or stage_data.get("success", "?")
                    print(f"    Stage [{stage_name}]: {s}")
                else:
                    print(f"    Stage [{stage_name}]: {stage_data}")
        return body
    except Exception as e:
        log(False, "/verify/complete", "POST", str(e), int((time.time() - start) * 1000))


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    print("=" * 70)
    print(f"  JOYO PRODUCTION API - COMPLETE E2E TEST")
    print(f"  Server: {BASE_URL}")
    print(f"  Test User: {TEST_USER_ID}")
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    total_start = time.time()

    # Run all tests in order (some depend on earlier results)
    test_index()
    test_health()
    test_plant_catalog()
    test_register_plant()
    test_get_plant()
    test_get_user_plants()
    test_planting_photo()
    test_health_scan()
    test_watering()
    test_remedy_apply()
    test_protection()
    test_user_points()
    test_user_history()
    test_stats()
    test_csr_stats()
    test_weather()
    test_biometric()
    test_fraud_check()
    test_nft_mint()
    test_verification_report()
    test_complete_verification()

    total_ms = int((time.time() - total_start) * 1000)

    # Summary
    passed = sum(1 for r in RESULTS if r["status"])
    failed = sum(1 for r in RESULTS if not r["status"])
    total = len(RESULTS)

    print("\n" + "=" * 70)
    print(f"  TEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"  Total Tests : {total}")
    print(f"  Passed      : {passed}")
    print(f"  Failed      : {failed}")
    print(f"  Pass Rate   : {passed/total*100:.1f}%" if total else "N/A")
    print(f"  Total Time  : {total_ms}ms ({total_ms/1000:.1f}s)")
    print("=" * 70)

    if failed > 0:
        print("\n  FAILED TESTS:")
        for r in RESULTS:
            if not r["status"]:
                tx_info_fail = f" TX:{r['tx_hash']}" if 'tx_hash' in r else ""
                print(f"    - {r['method']} {r['endpoint']}: {r['detail']}{tx_info_fail}")

    print("\n  ALL TESTS:")
    for i, r in enumerate(RESULTS, 1):
        icon = "PASS" if r["status"] else "FAIL"
        tx_info = f" TX:{r['tx_hash']}" if 'tx_hash' in r else ""
        print(f"    {i:2d}. [{icon}] {r['method']:5s} {r['endpoint'][:45]:45s} {r['elapsed_ms']:>6d}ms{tx_info}")

    # Write results to JSON
    report = {
        "server": BASE_URL,
        "test_user": TEST_USER_ID,
        "test_plant": TEST_PLANT_ID,
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{passed/total*100:.1f}%" if total else "N/A",
        "total_time_ms": total_ms,
        "results": RESULTS,
    }
    with open("test_live_server_results.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Results saved to test_live_server_results.json")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
