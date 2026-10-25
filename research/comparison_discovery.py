"""Discover bounded 2020+ candidates without spending historical payload budget."""

import json
from urllib.parse import urlencode

from phase0 import Collector, DATA, atomic_json, is_detail
from survey import index
from comparison import FAMILIES, YEARS, pool


def main():
    collector = Collector()
    path = DATA / "comparison-discovery.json"
    observations = json.loads(path.read_text()) if path.exists() else []
    done = {(r["year"], r.get("variant", "base")) for r in observations}
    probes = [(year, "base") for year in range(2020,2026)] + [(year,"data_analytics") for year in [2024,2025]]
    for year, variant in probes:
        if (year, variant) in done:
            continue
        parameters = [
            ("url", "www.capitalonecareers.com/job/*"), ("from", str(year)), ("to", str(year)),
            ("output", "json"), ("filter", "statuscode:200"), ("filter", "mimetype:text/html"),
            ("collapse", "urlkey"), ("limit", "200"),
            ("fl", "timestamp,original,statuscode,mimetype,digest")]
        parameters.append(("filter", "!original:.*/job/-/.*" if variant == "base" else
                           "original:.*(data-analyst|data-scientist|data-analysis|business-analyst|quantitative|statistician).*"))
        url = "https://web.archive.org/cdx/search/cdx?" + urlencode(parameters)
        # Six supplemental credits preceded this shared ledger; 19 + 6 = 25 maximum.
        rows, item = index(collector, url, credit_limit=19)
        candidates = [r for r in rows or [] if is_detail(r["original"])]
        observations.append(dict(year=year, variant=variant, request_key=item["request_key"],
                                 outcome="index_read" if rows is not None else item["outcome"],
                                 count=len(rows) if rows is not None else None,
                                 possibly_truncated=bool(rows and len(rows)>=200), candidates=candidates))
        atomic_json(path, observations)
        print(year, observations[-1]["outcome"], len(candidates), flush=True)
    records = json.loads((DATA / "results.json").read_text())
    recovered = DATA / "comparison-recovery-results.json"
    if recovered.exists():
        records += json.loads(recovered.read_text())
    cells = pool(records)
    expressions = dict(software_engineering="software-engineer|application-developer",
                       data_analytics="data-analyst|data-scientist|data-analysis|business-analyst|quantitative|statistician",
                       product_management="product-manag", risk_compliance="risk|compliance|audit|controls",
                       customer_operations="teller|customer-service|branch-ambassador|cafe-ambassador")
    for year in YEARS:
        for role in FAMILIES:
            variant = role + "_US"
            if len(cells[year,role])>=2 or (year,variant) in done:
                continue
            url = "https://web.archive.org/cdx/search/cdx?" + urlencode([
                ("url","www.capitalonecareers.com/job/*"),("from",str(year)),("to",str(year)),
                ("output","json"),("filter","statuscode:200"),("filter","mimetype:text/html"),
                ("filter",f"original:.*({expressions[role]}).*"),
                ("filter","!original:.*/job/-/.*"),
                ("filter","!original:.*/job/(bengaluru|bangalore|alabang|toronto|nottingham|london|mexico-city).*"),
                ("collapse","urlkey"),("limit","200"),("fl","timestamp,original,statuscode,mimetype,digest")])
            rows,item = index(collector,url,credit_limit=19)
            observations.append(dict(year=year,variant=variant,request_key=item["request_key"],
                outcome="index_read" if rows is not None else item["outcome"],count=len(rows) if rows is not None else None,
                possibly_truncated=bool(rows and len(rows)>=200),candidates=[r for r in rows or [] if is_detail(r["original"])]))
            atomic_json(path,observations)
            print(year,variant,observations[-1]["outcome"],len(rows or []),flush=True)


if __name__ == "__main__":
    main()
