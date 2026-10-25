"""Find a nearby 2020 WARC response for a comparison posting, then checkpoint it."""

import json
from datetime import datetime
from urllib.parse import urlencode

from phase0 import Collector, DATA, atomic_json


def main():
    collector = Collector()
    catalog_item = collector.fetch("https://index.commoncrawl.org/collinfo.json")
    catalog = json.loads(collector.body(catalog_item))
    collections = [r["id"] for r in catalog if r["id"].startswith("CC-MAIN-2020-")]
    rows = json.loads((DATA / "comparison-recovery-results.json").read_text())
    candidates = [r for r in rows if (r.get("archive_capture_at") or "").startswith("2020")]
    observations = []
    path = DATA / "commoncrawl-targeted-probes.json"
    for candidate in candidates[:3]:
        week = datetime.fromisoformat(candidate["archive_capture_at"]).isocalendar().week
        nearby = sorted(collections, key=lambda c:abs(int(c.rsplit("-",1)[1])-week))[:2]
        for collection in nearby:
            url = f"https://index.commoncrawl.org/{collection}-index?" + urlencode(dict(
                url=candidate["original_url"], output="json", filter="status:200", pageSize=1))
            item = collector.fetch(url)
            found = [json.loads(line) for line in collector.body(item).splitlines() if line.strip()] if item["outcome"] == "ok" else []
            observations.append(dict(collection=collection, original_url=candidate["original_url"],
                                     request_key=item["request_key"], outcome=item["outcome"], index_records=found))
            atomic_json(path, observations)
            print(collection, item["outcome"], len(found), flush=True)
            if found:
                return


if __name__ == "__main__":
    main()
