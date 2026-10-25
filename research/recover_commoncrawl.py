"""Validate one bounded 2020 response record against its public CC index locator."""

import io
import json
from datetime import datetime

from warcio.archiveiterator import ArchiveIterator

from phase0 import Collector, DATA, atomic_json, digest, export, extract, record, historical_payload


def decode_warc(item, raw, locator, index_request_key):
    assert digest(raw) == item["sha256"]
    assert len(raw) == int(locator["length"])
    results = []
    for warc in ArchiveIterator(io.BytesIO(raw)):
        if warc.rec_type != "response":
            continue
        target = warc.rec_headers.get_header("WARC-Target-URI")
        date = warc.rec_headers.get_header("WARC-Date")
        captured = datetime.fromisoformat(date.replace("Z", "+00:00"))
        assert target == locator["url"]
        assert captured.strftime("%Y%m%d%H%M%S") == locator["timestamp"]
        assert warc.http_headers.get_statuscode() == "200"
        payload = warc.content_stream().read(16*1024**2+1)
        assert len(payload) <= 16*1024**2
        parsed = extract(payload, target)
        if parsed:
            parsed["extraction_kind"] = "commoncrawl_warc"
            result = record({**item,"original_url":target}, parsed, historical=True)
            result.update(source_type="commoncrawl", archive_capture_at=captured.isoformat(),
                          archive_timestamp_verified=True, requested_archive_timestamp=locator["timestamp"],
                          warc_evidence=dict(target_uri=target, warc_date=date, locator=locator,
                              index_request_key=index_request_key, payload_sha256=digest(payload),
                              http_headers=warc.http_headers.headers, record_id=warc.rec_headers.get_header("WARC-Record-ID")))
            results.append(result)
    return results


def main():
    collector = Collector()
    used = sum(historical_payload(i["requested_url"])
               for i in collector.requests.values())
    assert used < json.loads((DATA / "scope-amendment.json").read_text())["historical_payload_limit"]
    observations = json.loads((DATA / "commoncrawl-targeted-probes.json").read_text())
    probe = next(p for p in observations if any(r.get("status")=="200" for r in p["index_records"]))
    locator = next(r for r in probe["index_records"] if r.get("status")=="200")
    offset, length = int(locator["offset"]), int(locator["length"])
    assert 0 < length < 16 * 1024**2
    item = collector.fetch("https://data.commoncrawl.org/" + locator["filename"],
                           headers={"Range":f"bytes={offset}-{offset+length-1}"})
    outcome = dict(request_key=item["request_key"], outcome=item["outcome"], locator=locator,
                   index_request_key=probe["request_key"])
    if item["outcome"] != "ok":
        atomic_json(DATA / "commoncrawl-payload-review.json", outcome)
        print(outcome)
        return
    results = decode_warc(item, collector.body(item), locator, probe["request_key"])
    export(results, "commoncrawl-results")
    outcome.update(extracted=len(results), identity_and_timestamp_verified=bool(results))
    atomic_json(DATA / "commoncrawl-payload-review.json", outcome)
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    main()
