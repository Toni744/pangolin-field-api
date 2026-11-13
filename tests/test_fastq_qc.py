import pytest

from app.fastq_qc import FastqFormatError, calculate_fastq_qc


def test_calculate_fastq_qc_handles_chunk_boundaries() -> None:
    chunks = [b"@read1\nAC", b"GT\n+\n!!!!\n@read2\nGG\n+\n##"]

    result = calculate_fastq_qc(chunks)

    assert result == {
        "read_count": 2,
        "base_count": 6,
        "gc_fraction": 2 / 3,
        "mean_phred_quality": 2 / 3,
    }


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"@read1\nACGT\n+\n!!!\n",
        b"read1\nACGT\n+\n!!!!\n",
        b"@read1\nACGT\n-\n!!!!\n",
        b"@read1\nACGX\n+\n!!!!\n",
    ],
)
def test_calculate_fastq_qc_rejects_malformed_records(content: bytes) -> None:
    with pytest.raises(FastqFormatError):
        calculate_fastq_qc([content])
