import time
import httpx

BASE_URL = "http://localhost:8000/api"

def main():
    print("[*] Testing end-to-end AI Analyst Brief pipeline...")
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 1. Login or register
    user_data = {"email": "ai_verifier@example.com", "password": "Password123!"}
    res = client.post("/auth/register", json=user_data)
    if res.status_code == 400:
        res = client.post("/auth/login", json=user_data)
    assert res.status_code in (200, 201), f"Auth failed: {res.text}"
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[+] Logged in as ai_verifier@example.com")

    # 2. Load demo sample (QPSK)
    res = client.post("/recordings/load-demo", json={"sample_id": "qpsk_48k"}, headers=headers)
    assert res.status_code in (200, 201), f"Load demo failed: {res.text}"
    rec = res.json()
    print(f"[+] Loaded demo recording: {rec['id']} ({rec['original_filename']})")

    # 3. Create project
    res = client.post(
        "/projects",
        headers=headers,
        json={"name": "AI Brief Test Project", "recording_id": rec["id"]},
    )
    assert res.status_code == 201, f"Project creation failed: {res.text}"
    proj = res.json()
    proj_id = proj["id"]
    print(f"[+] Created project: {proj_id}")

    # 4. Run parameter estimation first
    res = client.post(f"/projects/{proj_id}/estimate-parameters", headers=headers)
    assert res.status_code == 202, f"Estimate failed: {res.text}"
    job_id = res.json()["id"]
    print(f"[+] Parameter estimation dispatched (Job: {job_id})")

    for _ in range(30):
        time.sleep(1)
        res = client.get(f"/jobs/{job_id}", headers=headers)
        status = res.json().get("status")
        if status in ("completed", "failed"):
            break
    assert status == "completed", f"Estimation job failed: {res.json()}"
    print("[+] Parameter estimation completed!")

    # 5. Generate AI Brief
    res = client.post(f"/projects/{proj_id}/insights", headers=headers)
    assert res.status_code == 202, f"Insight generation request failed: {res.text}"
    ai_job_id = res.json()["id"]
    print(f"[+] AI Insight generation dispatched (Job: {ai_job_id})")

    for _ in range(30):
        time.sleep(1)
        res = client.get(f"/jobs/{ai_job_id}", headers=headers)
        status = res.json().get("status")
        if status in ("completed", "failed"):
            break
    assert status == "completed", f"AI Insight job failed: {res.json()}"
    print("[+] AI Insight job completed!")

    # 6. Fetch the generated insight
    res = client.get(f"/projects/{proj_id}/insights", headers=headers)
    assert res.status_code == 200, f"Fetch insight failed: {res.text}"
    insight = res.json()
    print(f"\n[+] AI Insight Received (Status: {insight.get('status')})")
    print(f"    * Model: {insight.get('model_name')}")
    print(f"    * Summary: {insight.get('summary')}")
    print(f"    * Citations: {insight.get('response_json', {}).get('citations')}")
    print(f"    * Hypotheses: {insight.get('response_json', {}).get('hypothesis')}")

    print("\n[SUCCESS] End-to-end Gemma 4 AI Analyst Brief verified successfully!")

if __name__ == "__main__":
    main()
