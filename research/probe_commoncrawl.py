"""Probe neighboring crawl indexes; defer payloads after the historical cap."""

import json
from urllib.parse import urlencode

from phase0 import Collector, DATA, atomic_json


def main():
    collector = Collector()
    path = DATA / "commoncrawl-probes.json"
    probes = json.loads(path.read_text())
    catalog = collector.fetch("https://index.commoncrawl.org/collinfo.json")
    identifiers = {r["id"] for r in json.loads(collector.body(catalog))}
    for collection, pattern in [
        ("CC-MAIN-2014-41", "jobs.capitalone.com/*"),
        ("CC-MAIN-2019-51", "www.capitalonecareers.com/job/*"),
        ("CC-MAIN-2026-34", "www.capitalonecareers.com/job/*"),
    ]:
        if collection not in identifiers:
            continue
        item = collector.fetch(f"https://index.commoncrawl.org/{collection}-index?" + urlencode(
            dict(url=pattern, output="json", pageSize=1, page=0)))
        rows = []
        if item["outcome"] == "ok":
            rows = [json.loads(line) for line in collector.body(item).splitlines() if line.strip()]
        probes.append(dict(collection=collection, url_pattern=pattern, outcome=item["outcome"],
                           request_key=item["request_key"], index_records=rows,
                           payloads_deferred="200 historical payload cap reached" if rows else None))
        probes = list({r["request_key"]:r for r in probes}.values())
        atomic_json(path, probes)
        print(collection, item["outcome"], flush=True)


if __name__ == "__main__":
    main()
