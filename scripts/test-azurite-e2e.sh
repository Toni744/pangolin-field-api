#!/usr/bin/env bash
set -euo pipefail

docker compose up -d azurite
docker compose run --rm storage-init

PANGOLIN_STORAGE_MODE=azurite \
AZURE_STORAGE_CONNECTION_STRING='DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;' \
BLOB_CONTAINER_NAME=samples \
SAMPLE_JOB_QUEUE_NAME=sample-jobs \
SAMPLE_POISON_QUEUE_NAME=sample-jobs-poison \
PANGOLIN_RUN_AZURITE_E2E=1 \
./.venv/bin/python -m pytest -q tests/test_azurite_integration.py
