"""Collect the separately linked Canada and UK current inventories."""

import json
from urllib.parse import urljoin

from phase0 import Collector, DATA, atomic_json, export, extract, now, record, soup


def main():
    collector = Collector()
    records = []
    inventories = []
    for host, region in [("www.capitalonecareers.ca", "Canada"), ("jobs.capitalone.co.uk", "United Kingdom")]:
        urls = []
        pages = []
        page, total = 1, 1
        while page <= total:
            url = f"https://{host}/search-jobs?p={page}"
            item = collector.fetch(url)
            document = soup(collector.body(item))
            section = document.select_one("#search-results")
            if section is None or section.get("data-current-page") != str(page):
                pages.append(dict(page=page, request_key=item["request_key"], outcome="pagination_failed"))
                break
            total = int(section.get("data-total-pages", "1"))
            found = list(dict.fromkeys(urljoin(url, a["href"]) for a in section.select('a[href*="/job/"]')))
            pages.append(dict(page=page, request_key=item["request_key"], reported_total=int(section["data-total-results"]), urls=found))
            urls.extend(found)
            page += 1
        inventory = dict(host=host, region=region, pages=pages, urls=list(dict.fromkeys(urls)),
                         pagination_complete=page > total, collected_at=now())
        inventories.append(inventory)
        atomic_json(DATA / "regional-inventories.json", inventories)
        for url in inventory["urls"]:
            item = collector.fetch(url)
            parsed = extract(collector.body(item), url) if item["outcome"] == "ok" else None
            if parsed:
                records.append({**record(item, parsed), "board_region": region})
            export(records, "regional-results")
        print(f"REGION {region}: {len(inventory['urls'])} URLs, {sum(r['board_region']==region for r in records)} descriptions, complete={inventory['pagination_complete']}", flush=True)


if __name__ == "__main__":
    main()
