import json
import logging
import os
import re
import signal
import time
from typing import Any
from uuid import UUID

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient
from prometheus_client import Counter, start_http_server

from app.fastq_qc import FastqFormatError, calculate_fastq_qc
from app.storage import (
    create_blob_service_client,
    create_queue_client,
    create_storage_credential,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
MAX_DEQUEUE_COUNT = int(os.getenv("MAX_DEQUEUE_COUNT", "5"))
POLL_INTERVAL_SECONDS = float(os.getenv("QUEUE_POLL_INTERVAL_SECONDS", "3"))
SAMPLE_JOBS = Counter(
    "pangolin_sample_jobs_total",
    "Pangolin sample jobs handled by the worker.",
    ("outcome",),
)
running = True


def _stop_worker(_signum: int, _frame: Any) -> None:
    global running
    _ = (_signum, _frame)
    running = False


def _is_expected_metadata_path(blob_name: str) -> bool:
    return (
        re.fullmatch(
            r"users/[0-9a-f]{64}/samples/[0-9a-f-]{36}/metadata\.json",
            blob_name,
        )
        is not None
    )


def _update_metadata(metadata_blob: Any, metadata: dict[str, Any]) -> None:
    metadata_blob.upload_blob(
        json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )


def _process_metadata_blob(
    blob_service: BlobServiceClient,
    container_name: str,
    metadata_name: str,
) -> None:
    if not _is_expected_metadata_path(metadata_name):
        raise ValueError("The queue message contains an invalid metadata path.")

    container = blob_service.get_container_client(container_name)
    metadata_blob = container.get_blob_client(metadata_name)
    metadata = json.loads(metadata_blob.download_blob().readall())
    if not isinstance(metadata, dict):
        raise TypeError("The sample metadata is invalid.")
    if metadata.get("status") == "completed":
        return

    sample_id = UUID(metadata["sample_id"])
    path_sample_id = UUID(metadata_name.split("/")[-2])
    if sample_id != path_sample_id:
        raise ValueError("The sample metadata ID does not match its Blob path.")
    sample_prefix = metadata_name.rsplit("/", 1)[0]
    data_blob_name = metadata.get("data_blob_name")
    expected_prefix = f"{sample_prefix}/data/"
    if (
        not isinstance(data_blob_name, str)
        or not data_blob_name.startswith(expected_prefix)
        or "/" in data_blob_name[len(expected_prefix) :]
    ):
        raise ValueError("The sample metadata contains an invalid data path.")

    metadata["status"] = "processing"
    metadata.pop("processing_error", None)
    _update_metadata(metadata_blob, metadata)

    data_blob = container.get_blob_client(data_blob_name)
    qc = calculate_fastq_qc(data_blob.download_blob().chunks())
    result_name = f"{sample_prefix}/results/qc.json"
    result_blob = container.get_blob_client(result_name)
    result_blob.upload_blob(
        json.dumps(qc, separators=(",", ":")).encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )

    metadata["status"] = "completed"
    metadata["qc_result_blob_name"] = result_name
    metadata["qc"] = qc
    _update_metadata(metadata_blob, metadata)
    logger.info("Completed FASTQ QC for sample %s", sample_id)


def _move_to_poison_queue(
    message: Any,
    queue_client: QueueClient,
    poison_queue_client: QueueClient,
    blob_service: BlobServiceClient,
    container_name: str,
    metadata_name: str | None,
    error_code: str,
) -> None:
    if metadata_name and _is_expected_metadata_path(metadata_name):
        container = blob_service.get_container_client(container_name)
        metadata_blob = container.get_blob_client(metadata_name)
        try:
            metadata = json.loads(metadata_blob.download_blob().readall())
        except (ResourceNotFoundError, json.JSONDecodeError):
            metadata = None
        if isinstance(metadata, dict):
            metadata["status"] = "failed"
            metadata["processing_error"] = error_code
            _update_metadata(metadata_blob, metadata)

    poison_queue_client.send_message(
        json.dumps(
            {
                "message_id": message.id,
                "error": error_code,
                "original_content": message.content,
            },
            separators=(",", ":"),
        )
    )
    queue_client.delete_message(message.id, message.pop_receipt)
    logger.error("Moved sample job to poison queue: %s", error_code)


def process_next_message(
    queue_client: QueueClient,
    poison_queue_client: QueueClient,
    blob_service: BlobServiceClient,
    container_name: str,
) -> bool:
    messages = queue_client.receive_messages(
        messages_per_page=1, visibility_timeout=300
    )
    message = next(iter(messages), None)
    if message is None:
        return False

    metadata_name: str | None = None
    try:
        payload = json.loads(message.content)
        metadata_name = (
            payload.get("metadata_blob_name") if isinstance(payload, dict) else None
        )
        if not isinstance(metadata_name, str):
            raise TypeError("The queue message is missing its metadata path.")
        _process_metadata_blob(blob_service, container_name, metadata_name)
    except (
        FastqFormatError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ):
        _move_to_poison_queue(
            message,
            queue_client,
            poison_queue_client,
            blob_service,
            container_name,
            metadata_name if isinstance(metadata_name, str) else None,
            "invalid_sample",
        )
        SAMPLE_JOBS.labels("deadlettered").inc()
        return True
    except AzureError as error:
        if message.dequeue_count >= MAX_DEQUEUE_COUNT:
            _move_to_poison_queue(
                message,
                queue_client,
                poison_queue_client,
                blob_service,
                container_name,
                metadata_name if isinstance(metadata_name, str) else None,
                "storage_unavailable",
            )
            SAMPLE_JOBS.labels("deadlettered").inc()
        else:
            logger.warning(
                "Azure request failed while processing sample job (attempt %s/%s): %s",
                message.dequeue_count,
                MAX_DEQUEUE_COUNT,
                type(error).__name__,
            )
            SAMPLE_JOBS.labels("retried").inc()
        return True

    queue_client.delete_message(message.id, message.pop_receipt)
    SAMPLE_JOBS.labels("completed").inc()
    return True


def main() -> None:
    queue_name = os.getenv("SAMPLE_JOB_QUEUE_NAME", "").strip()
    poison_queue_name = os.getenv("SAMPLE_POISON_QUEUE_NAME", "").strip()
    container_name = os.getenv("BLOB_CONTAINER_NAME", "").strip()
    if not all((queue_name, poison_queue_name, container_name)):
        raise RuntimeError("Azure Blob and Queue Storage settings must be configured.")

    credential = create_storage_credential()
    blob_service = create_blob_service_client(credential)
    queue_client = create_queue_client(queue_name, credential)
    poison_queue_client = create_queue_client(poison_queue_name, credential)
    signal.signal(signal.SIGTERM, _stop_worker)
    signal.signal(signal.SIGINT, _stop_worker)
    # Prometheus needs to reach this listener through the pod IP.
    start_http_server(8001, addr="0.0.0.0")  # nosec B104
    logger.info("Pangolin sample worker started")
    try:
        while running:
            try:
                received = process_next_message(
                    queue_client,
                    poison_queue_client,
                    blob_service,
                    container_name,
                )
            except AzureError:
                logger.exception("Could not poll or acknowledge the sample queue")
                time.sleep(min(POLL_INTERVAL_SECONDS * 2, 30))
                continue
            if not received:
                time.sleep(POLL_INTERVAL_SECONDS)
    finally:
        blob_service.close()
        queue_client.close()
        poison_queue_client.close()
        if credential is not None:
            credential.close()


if __name__ == "__main__":
    main()
