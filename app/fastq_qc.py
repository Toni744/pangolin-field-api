from collections.abc import Iterable


class FastqFormatError(ValueError):
    pass


def calculate_fastq_qc(chunks: Iterable[bytes]) -> dict[str, int | float]:
    pending = bytearray()
    record: list[bytes] = []
    reads = 0
    bases = 0
    gc_bases = 0
    quality_sum = 0

    def consume_line(line: bytes) -> None:
        nonlocal reads, bases, gc_bases, quality_sum
        line = line.removesuffix(b"\r")
        record.append(line)
        if len(record) < 4:
            return

        header, sequence, separator, quality = record
        if not header.startswith(b"@") or not separator.startswith(b"+"):
            raise FastqFormatError("FASTQ record header or separator is invalid.")
        if not sequence or len(sequence) != len(quality):
            raise FastqFormatError("FASTQ sequence and quality lengths do not match.")
        if any(base not in b"ACGTNacgtn" for base in sequence):
            raise FastqFormatError("FASTQ sequence contains unsupported bases.")
        if any(score < 33 or score > 126 for score in quality):
            raise FastqFormatError("FASTQ quality contains an invalid Phred+33 score.")

        reads += 1
        bases += len(sequence)
        upper_sequence = sequence.upper()
        gc_bases += upper_sequence.count(b"G") + upper_sequence.count(b"C")
        quality_sum += sum(score - 33 for score in quality)
        record.clear()

    for chunk in chunks:
        pending.extend(chunk)
        lines = pending.split(b"\n")
        pending = bytearray(lines.pop())
        for line in lines:
            consume_line(line)

    if pending:
        consume_line(bytes(pending))
    if record:
        raise FastqFormatError("FASTQ input ended before a complete record.")
    if reads == 0:
        raise FastqFormatError("FASTQ input contains no records.")

    return {
        "read_count": reads,
        "base_count": bases,
        "gc_fraction": gc_bases / bases,
        "mean_phred_quality": quality_sum / bases,
    }
