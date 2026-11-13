import os

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueClient


def main() -> None:
    if os.getenv("PANGOLIN_STORAGE_MODE", "").strip().casefold() != "azurite":
        raise RuntimeError("Storage initialization is only allowed in Azurite mode.")

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    container_name = os.getenv("BLOB_CONTAINER_NAME", "").strip()
    queue_names = (
        os.getenv("SAMPLE_JOB_QUEUE_NAME", "").strip(),
        os.getenv("SAMPLE_POISON_QUEUE_NAME", "").strip(),
    )
    if not connection_string or not container_name or not all(queue_names):
        raise RuntimeError("Azurite connection, container, and queues are required.")

    blob_service = BlobServiceClient.from_connection_string(connection_string)
    try:
        try:
            blob_service.create_container(container_name)
        except ResourceExistsError:
            pass

        for queue_name in queue_names:
            queue = QueueClient.from_connection_string(
                connection_string,
                queue_name=queue_name,
            )
            try:
                try:
                    queue.create_queue()
                except ResourceExistsError:
                    pass
            finally:
                queue.close()
    finally:
        blob_service.close()


if __name__ == "__main__":
    main()
