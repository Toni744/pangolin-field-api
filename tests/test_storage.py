from unittest.mock import Mock

from app.storage import BlobStore


def test_readiness_checks_blob_container_and_job_queue() -> None:
    store = BlobStore.__new__(BlobStore)
    store._service = Mock()
    store._queue = Mock()
    store._container_name = "samples"

    store.check_readiness()

    store._service.get_container_client.assert_called_once_with("samples")
    store._service.get_container_client.return_value.get_container_properties.assert_called_once_with()
    store._queue.get_queue_properties.assert_called_once_with()
