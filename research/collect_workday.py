"""Public Workday board cross-check, fetching only previously uncaptured apply paths."""

import html
import json
import re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from phase0 import Collector, DATA, atomic_json, export, now, record, text_content

HOST = "https://capitalone.wd12.myworkdayjobs.com"


def main():
    collector = Collector()
    robots = collector.fetch(HOST + "/robots.txt")
    rules = RobotFileParser()
    rules.parse(collector.body(robots).decode("utf-8", "replace").splitlines())
    endpoint = HOST + "/wday/cxs/capitalone/Capital_One/jobs"
    if robots["outcome"] == "ok" and not rules.can_fetch("ArchvivePhase0", endpoint):
        atomic_json(DATA / "workday-inventory.json", dict(outcome="excluded_by_robots", request_key=robots["request_key"], urls=[], pagination_complete=False))
        return
    known_paths = set()
    for item in collector.requests.values():
        if "capitalonecareers" not in item["requested_url"] and "capitalone.co.uk" not in item["requested_url"]:
            continue
        if not item.get("artifact_path") or item["outcome"] != "ok":
            continue
        body = collector.body(item).decode("utf-8", "replace")
        match = re.search(r'<meta name="search-job-apply-url" content="([^"]+)"', body)
        if match and "/Capital_One/job/" in match[1]:
            path = urlsplit(html.unescape(match[1])).path.split("/Capital_One", 1)[1]
            known_paths.add(path.removesuffix("/apply"))
    pages = []
    postings = []
    offset, total = 0, 1
    while offset < total:
        item = collector.fetch(endpoint, method="POST", payload=dict(appliedFacets={}, limit=20, offset=offset, searchText=""))
        if item["outcome"] != "ok":
            pages.append(dict(offset=offset, request_key=item["request_key"], outcome=item["outcome"]))
            break
        try:
            data = json.loads(collector.body(item))
        except ValueError:
            break
        total = data.get("total", 0)
        found = data.get("jobPostings", [])
        pages.append(dict(offset=offset, request_key=item["request_key"], reported_total=total, count=len(found)))
        postings.extend(found)
        if not found:
            break
        offset += len(found)
        atomic_json(DATA / "workday-inventory.json", dict(pages=pages, postings=postings, reported_total=total,
                    pagination_complete=offset >= total, collected_at=now(), known_apply_paths=len(known_paths)))
    records = []
    for candidate in postings:
        path = candidate.get("externalPath", "")
        if not path.startswith("/job/") or path in known_paths:
            continue
        url = HOST + "/wday/cxs/capitalone/Capital_One" + path
        item = collector.fetch(url)
        if item["outcome"] != "ok":
            continue
        try:
            data = json.loads(collector.body(item))["jobPostingInfo"]
        except (ValueError, KeyError):
            continue
        description = data.get("jobDescription", "")
        if not description:
            continue
        extracted = dict(title=data.get("title"), description_html=description,
                         description=text_content(description), identifiers={"requisition_id": data.get("jobReqId"), "workday_posting_path": path},
                         source_declared_dates={k:data[k] for k in ["startDate", "endDate"] if data.get(k)},
                         location={"primary":data.get("location"), "additional":data.get("additionalLocations")},
                         language=None, extraction_kind="regional_workday",
                         extraction_selector="$.jobPostingInfo.jobDescription")
        records.append({**record(item, extracted), "original_url": HOST + "/en-US/Capital_One" + path,
                        "board_region":"Global Workday"})
        export(records, "workday-results")
    print(f"WORKDAY {len(postings)}/{total} listed, {len(records)} additional descriptions", flush=True)


if __name__ == "__main__":
    main()
