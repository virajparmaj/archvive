"""Rebuild the canonical exports with networking disabled and compare exact bytes."""

import json
import runpy
import socket
import sys
from pathlib import Path

import httpx

sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase0 import DATA, ROOT, atomic_json, digest


def disabled(*args, **kwargs):
    raise AssertionError("Network attempted during offline reproduction")


def main():
    names = ["results.json","results.csv","historical-results.json","historical-results.csv",
             "current-results.json","current-results.csv","comparison-results.json","comparison-results.csv",
             "comparison-early-benchmark.json","comparison-early-benchmark.csv","comparison-matrix.json",
             "postings.json","versions.json","validation.json","budget.json","discovery-summary.json"]
    before = {name:digest((DATA/name).read_bytes()) for name in names}
    manifest_hash = digest((DATA/"requests.jsonl").read_bytes())
    socket.socket.connect = disabled
    socket.create_connection = disabled
    httpx.Client.send = disabled
    for script in ["benchmark.py","review_checks.py","comparison_review.py","reprocess.py","verify.py","comparison.py"]:
        runpy.run_path(str(ROOT/"research"/script),run_name="__main__")
    after = {name:digest((DATA/name).read_bytes()) for name in names}
    changed = [name for name in names if before[name]!=after[name]]
    assert not changed, f"Non-deterministic exports: {changed}"
    assert digest((DATA/"requests.jsonl").read_bytes())==manifest_hash
    result = dict(passed=True,network_disabled=True,request_manifest_unchanged=True,
                  request_manifest_sha256=manifest_hash,deterministic_exports=after,
                  description="Exact JSON/CSV regeneration from retained HTML, PDF, Workday JSON and WARC bytes")
    atomic_json(DATA/"offline-reproducibility.json",result)
    print(json.dumps(dict(passed=True,deterministic_exports=len(after),network_disabled=True)))


if __name__ == "__main__":
    main()
