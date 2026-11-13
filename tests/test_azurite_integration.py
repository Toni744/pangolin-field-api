import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app import main, worker
from app.storage import (
    BlobStore,
    create_blob_service_client,
    create_queue_client,
    create_storage_credential,
)

pytestmark = pytest.mark.skipif(
    os.getenv("PANGOLIN_RUN_AZURITE_E2E") != "1",
    reason="Set PANGOLIN_RUN_AZURITE_E2E=1 to run against local Azurite.",
)

FASTQ = b"@PANGOLIN-E2E\nACGTACGT\n+\nIIIIIIII\n"


def test_api_blob_queue_worker_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.getenv("PANGOLIN_STORAGE_MODE") != "azurite":
        pytest.fail("The end-to-end test must use Azurite, never Azure Storage.")

    sample_id = uuid4()
    queue_name = f"e2e-{sample_id.hex[:12]}"
    poison_queue_name = f"e2e-poison-{sample_id.hex[:12]}"
    monkeypatch.setenv("SAMPLE_JOB_QUEUE_NAME", queue_name)
    monkeypatch.setenv("SAMPLE_POISON_QUEUE_NAME", poison_queue_name)
    store = BlobStore.from_environment()
    credential = create_storage_credential()
    blob_service = create_blob_service_client(credential)
    queue_client = create_queue_client(queue_name, credential)
    poison_queue_client = create_queue_client(poison_queue_name, credential)
    queue_client.create_queue()
    poison_queue_client.create_queue()
    submitted_by = f"azurite-e2e-{sample_id}"
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": submitted_by}

    try:

        async def submit_sample() -> httpx.Response:
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                return await client.post(
                    "/samples",
                    data={
                        "sample_id": str(sample_id),
                        "site_code": "interview-demo",
                        "observed_at": datetime.now(UTC).isoformat(),
                    },
                    files={"file": ("sample.fastq", FASTQ, "text/plain")},
                )

        response = asyncio.run(submit_sample())
        assert response.status_code == 201
        assert worker.process_next_message(
            queue_client,
            poison_queue_client,
            blob_service,
            os.environ["BLOB_CONTAINER_NAME"],
        )

        status = store.get_sample_status(
            submitted_by=submitted_by,
            sample_id=sample_id,
        )
        assert status is not None
        assert status["status"] == "completed"
        assert status["qc"] == {
            "read_count": 1,
            "base_count": 8,
            "gc_fraction": 0.5,
            "mean_phred_quality": 40.0,
        }

        container = store._service.get_container_client(
            os.environ["BLOB_CONTAINER_NAME"]
        )
        subject_path = response.json()["metadata_blob_name"].rsplit("/samples/", 1)[0]
        blob_prefix = f"{subject_path}/samples/{sample_id}"
        for blob in container.list_blobs(name_starts_with=blob_prefix):
            container.delete_blob(blob.name)
    finally:
        main.app.dependency_overrides.clear()
        queue_client.delete_queue()
        poison_queue_client.delete_queue()
        store.close()
        blob_service.close()
        queue_client.close()
        poison_queue_client.close()
        if credential is not None:
            credential.close()
