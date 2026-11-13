import json
from dataclasses import dataclass

import pytest
from azure.core.exceptions import AzureError

from app import worker


@dataclass
class Message:
    content: str
    dequeue_count: int = 1
    id: str = "message-id"
    pop_receipt: str = "receipt"


class FakeQueue:
    def __init__(self, message: Message | None) -> None:
        self.message = message
        self.deleted: list[tuple[str, str]] = []
        self.sent: list[str] = []

    def receive_messages(self, **kwargs: object) -> list[Message]:
        _ = kwargs
        return [] if self.message is None else [self.message]

    def delete_message(self, message_id: str, pop_receipt: str) -> None:
        self.deleted.append((message_id, pop_receipt))

    def send_message(self, content: str) -> None:
        self.sent.append(content)


def test_process_next_message_acknowledges_completed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_name = (
        f"users/{'a' * 64}/samples/2dbf85de-daa5-4e16-bdbe-c8ab11392400/metadata.json"
    )
    message = Message(json.dumps({"metadata_blob_name": metadata_name}))
    queue = FakeQueue(message)
    poison_queue = FakeQueue(None)

    def complete_job(*args: object) -> None:
        _ = args

    monkeypatch.setattr(worker, "_process_metadata_blob", complete_job)

    received = worker.process_next_message(queue, poison_queue, object(), "samples")

    assert received is True
    assert queue.deleted == [("message-id", "receipt")]
    assert poison_queue.sent == []


def test_process_next_message_leaves_transient_failure_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_name = (
        f"users/{'a' * 64}/samples/2dbf85de-daa5-4e16-bdbe-c8ab11392400/metadata.json"
    )
    queue = FakeQueue(Message(json.dumps({"metadata_blob_name": metadata_name})))
    poison_queue = FakeQueue(None)

    def fail_processing(*args: object) -> None:
        _ = args
        raise AzureError("temporary storage failure")

    monkeypatch.setattr(worker, "_process_metadata_blob", fail_processing)

    received = worker.process_next_message(queue, poison_queue, object(), "samples")

    assert received is True
    assert queue.deleted == []
    assert poison_queue.sent == []


def test_process_next_message_dead_letters_invalid_message() -> None:
    queue = FakeQueue(Message("not-json"))
    poison_queue = FakeQueue(None)

    received = worker.process_next_message(queue, poison_queue, object(), "samples")

    assert received is True
    assert queue.deleted == [("message-id", "receipt")]
    poison_message = json.loads(poison_queue.sent[0])
    assert poison_message["error"] == "invalid_sample"
    assert poison_message["original_content"] == "not-json"
