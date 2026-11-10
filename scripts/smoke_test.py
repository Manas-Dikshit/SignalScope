import time
import httpx

BASE_URL = "http://localhost:8000/api"

def main():
    print("Starting SignalScope End-to-End Smoke Test...")
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 1. Register test user
    user_data = {"email": "smoketest@example.com", "password": "Password123!"}
    res = client.post("/auth/register", json=user_data)
    if res.status_code == 400:  # User already exists
        res = client.post("/auth/login", json=user_data)
    
    assert res.status_code in (200, 201), f"Auth failed: {res.text}"
    tokens = res.json()
    token = tokens.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("[+] Authenticated successfully as smoketest@example.com")

    # 2. Upload sample_qpsk_48k.wav
    wav_path = "samples/sample_qpsk_48k.wav"
    with open(wav_path, "rb") as f:
        files = {"file": ("sample_qpsk_48k.wav", f, "audio/wav")}
        data = {"stereo_mode": "left_is_i_right_is_q", "loader": "wav"}
        res = client.post("/recordings/upload", headers=headers, files=files, data=data)

    assert res.status_code == 201, f"Upload failed: {res.text}"
    rec = res.json()
    rec_id = rec["id"]
    print(f"[+] Uploaded recording ID: {rec_id} (Format: {rec.get('file_format')}, Samples: {rec.get('total_samples')})")

    # 3. Create project
    res = client.post(
        "/projects",
        headers=headers,
        json={"name": "QPSK End-to-End Test Project", "recording_id": rec_id},
    )
    assert res.status_code == 201, f"Create project failed: {res.text}"
    proj = res.json()
    proj_id = proj["id"]
    print(f"[+] Created project ID: {proj_id}")

    # 4. Trigger parameter estimation job
    res = client.post(f"/projects/{proj_id}/estimate-parameters", headers=headers)
    assert res.status_code == 202, f"Estimate parameters failed: {res.text}"
    job = res.json()
    job_id = job["id"]
    print(f"[+] Dispatched Celery DSP job ID: {job_id}")

    # 5. Poll job status until complete
    status = "queued"
    for _ in range(30):
        time.sleep(1)
        res = client.get(f"/jobs/{job_id}", headers=headers)
        job_data = res.json()
        status = job_data.get("status")
        print(f"    Waiting for Celery worker... Job status: {status}")
        if status in ("completed", "failed"):
            break

    assert status == "completed", f"Job did not complete: {job_data}"
    print("[+] DSP Job completed successfully!")

    # 6. Fetch estimated parameters
    res = client.get(f"/projects/{proj_id}/parameters", headers=headers)
    params = res.json()
    print(f"\n[+] Parameter Estimates ({len(params)} found):")
    for p in params:
        print(f"    * {p.get('parameter_name')}: {p.get('value_type')} (Confidence: {p.get('confidence')})")

    print("\n[SUCCESS] End-to-end stack verification complete!")

if __name__ == "__main__":
    main()
