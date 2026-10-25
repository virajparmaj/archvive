"""Capture all role links on the verified Philippines board; no form submission."""

import json
from urllib.parse import urlsplit

from phase0 import Collector, DATA, atomic_json, soup


def main():
    collector = Collector()
    index_url = "https://capitalonecareers.com.ph/career-opportunities.php"
    index = collector.fetch(index_url)
    collector.fetch("https://capitalonecareers.com.ph/robots.txt")
    document = soup(collector.body(index))
    urls = sorted({a["href"] for a in document.select('a[href]')
                   if urlsplit(a["href"]).hostname == "capitalonecareers.com.ph"
                   and a["href"].endswith(".php")
                   and not any(x in a["href"] for x in ["security", "career-opportunities"])})
    observations = [collector.fetch(url) for url in urls]
    atomic_json(DATA / "philippines-inventory.json", dict(index_request_key=index["request_key"],
                urls=urls, pagination_complete=index["outcome"] == "ok", reported_total=None,
                observations=[dict(url=i["requested_url"], request_key=i["request_key"], outcome=i["outcome"])
                              for i in observations]))
    print(json.dumps(dict(linked_roles=len(urls), successful=sum(i["outcome"] == "ok" for i in observations))))


if __name__ == "__main__":
    main()
