"""Validate a historical handover with the Python standard library, entirely offline."""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path


KEYS = {
    "source_record_id", "company", "title", "url", "url_aliases", "requisition_id",
    "provider", "provider_posting_id", "published_at", "published_at_raw",
    "published_at_provenance", "updated_at", "updated_at_raw", "updated_at_provenance",
    "captured_at", "captured_at_provenance", "wording_valid_at",
    "wording_valid_at_provenance", "locations", "employment_type", "description",
    "description_completeness", "evidence_files", "notes",
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    lines = (root / "historical-postings.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    canonical = {r["version_key"]: r for r in json.loads(
        (root / "evidence/collection/historical-results.json").read_text(encoding="utf-8")
    )}
    subset = {r["version_key"] for r in json.loads(
        (root / "evidence/collection/target-comparison-compact.json").read_text(encoding="utf-8")
    )}
    mappings = {m["source_record_id"]: m for m in manifest["records"]}
    assert len(records) == len(mappings) == len(manifest["records"])
    assert len({r["source_record_id"] for r in records}) == len(records)
    expected = {(key, e["request_key"]) for key, r in canonical.items() for e in r["evidence"]}
    actual = {(m["version_key"], m["request_key"]) for m in mappings.values()}
    assert expected == actual and len(expected) == len(records)
    references = 0
    for row in records:
        assert set(row) == KEYS
        for key in ["url_aliases", "locations", "evidence_files", "notes"]:
            assert isinstance(row[key], list)
        assert isinstance(row["description"], str) and row["description"]
        assert row["description_completeness"] in {"complete", "partial", "unknown"}
        mapping = mappings[row["source_record_id"]]
        assert row["description"] == canonical[mapping["version_key"]]["description"]
        assert sha256(row["description"].encode("utf-8")) == mapping["description_sha256"]
        is_subset = mapping["version_key"] in subset
        assert mapping["comparison_subset"] == is_subset
        assert f"comparison_subset={'true' if is_subset else 'false'}" in row["notes"]
        for field in ["published_at", "updated_at", "captured_at", "wording_valid_at"]:
            value = row[field]
            if value is not None:
                assert row[field + "_provenance"]
                if "T" in value:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    date.fromisoformat(value)
                else:
                    assert re.fullmatch(r"\d{4}(?:-\d{2})?", value)
            else:
                assert row[field + "_provenance"] is None or row.get(field + "_raw") is not None
        for relative in row["evidence_files"]:
            path = root / relative
            assert relative.startswith("evidence/")
            assert path.resolve().is_relative_to(root / "evidence") and path.is_file()
            references += 1
        for relative in mapping["original_evidence_files"]:
            assert sha256((root / relative).read_bytes()) == mapping["original_sha256"]
    for relative, digest in manifest["files_sha256"].items():
        path = root / relative
        assert path.resolve().is_relative_to(root) and path.is_file()
        assert sha256(path.read_bytes()) == digest, relative
    assert sha256((root / "evidence/collection/historical-results.json").read_bytes()) == (
        manifest["canonical_input_sha256"]
    )
    return {
        "validation_passed": True, "jsonl_lines_parsed": len(records),
        "unique_source_record_ids": len(mappings), "evidence_references_checked": references,
        "missing_referenced_evidence_files": 0,
        "package_files_hash_checked": len(manifest["files_sha256"]),
        "original_evidence_hashes_checked": len(records),
        "canonical_description_matches": len(records),
        "observation_coverage_complete": True, "comparison_flags_validated": True,
    }


if __name__ == "__main__":
    print(json.dumps(validate(Path(__file__).parent), indent=2))
