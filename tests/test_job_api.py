"""FastAPI endpoint tests for job server - requires database setup."""

import pytest

# These tests require database and profile setup
# Mark as integration tests that need real infrastructure
pytestmark = pytest.mark.skip(reason="Requires database setup - integration test")


def test_health_endpoint():
    """Test health endpoint returns expected structure."""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "job-server"
    assert data["version"] == "2.0.0"
    assert "running_jobs" in data


def test_list_jobs_empty():
    """Test GET /jobs returns empty list on fresh start."""
    response = client.get("/jobs")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_create_ingest_job():
    """Test POST /ingest/jobs creates new job."""
    response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen", "truncate": False}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "status" in data
    assert data["status"] == "pending"
    assert data["profile"] == "avi-cohen"


def test_create_ingest_job_with_truncate():
    """Test POST /ingest/jobs with truncate flag."""
    response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen", "truncate": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["truncate"] is True


def test_create_ingest_invalid_profile():
    """Test POST /ingest/jobs with non-existent profile."""
    response = client.post(
        "/ingest/jobs",
        json={"profile": "non-existent-profile"}
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_job_status():
    """Test GET /jobs/{job_id} returns job details."""
    # First create a job
    create_response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen"}
    )
    job_id = create_response.json()["job_id"]
    
    # Then fetch it
    response = client.get(f"/jobs/{job_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["profile"] == "avi-cohen"
    assert "status" in data
    assert "created_at" in data


def test_get_job_status_not_found():
    """Test GET /jobs/{job_id} with non-existent job."""
    response = client.get("/jobs/non-existent-job-id")
    
    assert response.status_code == 404


def test_job_lifecycle():
    """Test full job lifecycle: create → check → cancel."""
    # 1. Create job
    create_response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen", "truncate": False}
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job_id"]
    
    # 2. Check initial status (should be pending or running)
    status_response = client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    status = status_response.json()["status"]
    assert status in ["pending", "running", "done", "failed"]
    
    # 3. Wait briefly for job to start
    time.sleep(0.5)
    
    # 4. Cancel all jobs
    cancel_response = client.post("/ingest/cancel_all")
    assert cancel_response.status_code == 200
    cancel_data = cancel_response.json()
    assert cancel_data["message"] == "cancellation_requested"


def test_list_jobs_after_creation():
    """Test GET /jobs includes newly created job."""
    # Create a job
    create_response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen"}
    )
    job_id = create_response.json()["job_id"]
    
    # List all jobs
    list_response = client.get("/jobs")
    assert list_response.status_code == 200
    jobs = list_response.json()
    
    # Find our job
    job_ids = [job["job_id"] for job in jobs]
    assert job_id in job_ids


def test_cancel_all_jobs_idempotent():
    """Test POST /ingest/cancel_all can be called multiple times."""
    response1 = client.post("/ingest/cancel_all")
    assert response1.status_code == 200
    
    response2 = client.post("/ingest/cancel_all")
    assert response2.status_code == 200


def test_create_job_missing_profile():
    """Test POST /ingest/jobs without profile field."""
    response = client.post(
        "/ingest/jobs",
        json={"truncate": False}
    )
    
    # Should fail validation
    assert response.status_code == 422


def test_job_status_includes_metadata():
    """Test job status includes all expected metadata fields."""
    # Create job
    create_response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen"}
    )
    job_id = create_response.json()["job_id"]
    
    # Get status
    response = client.get(f"/jobs/{job_id}")
    data = response.json()
    
    # Check required fields
    assert "job_id" in data
    assert "profile" in data
    assert "status" in data
    assert "created_at" in data
    # Optional fields (may not exist if job hasn't started)
    if data["status"] == "running":
        assert "phase" in data
