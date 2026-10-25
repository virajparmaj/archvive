"""Bounded, purposive comparison sample; no claim about company hiring volume."""

import json
import re
import unicodedata
from collections import defaultdict
from urllib.parse import unquote, urlsplit

from phase0 import Collector, DATA, archive_evidence, atomic_json, export, extract, record, source_date_conflict, historical_payload
from verify import requisition

YEARS = list(range(2020, 2026))
FAMILIES = ["software_engineering", "data_analytics", "product_management", "risk_compliance", "customer_operations"]


def family(title):
    text = unicodedata.normalize("NFKD", title.lower())
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("-", " ")
    if re.search(r"\bintern(?:ship)?\b|director|vice president|\bvp\b|head of", text):
        return None
    if re.search(r"ux|ui designer|design", text) and not re.search(r"product manag",text):
        return None
    if re.search(r"software (?:engineer|developer)|application developer|ios developer", text):
        return "software_engineering"
    if re.search(r"data (?:analyst|scientist|analysis)|business analyst|statistician|quantitative", text):
        return "data_analytics"
    if re.search(r"product manag", text):
        return "product_management"
    if re.search(r"risk|compliance|audit|controls", text):
        return "risk_compliance"
    if re.search(r"teller|customer service|contact center|branch ambassador|cafe ambassador", text):
        return "customer_operations"
    return None


def identity(row):
    return requisition(row) or row["identifiers"].get("careers_site_job_id") or row["original_url"]


def us_eligible(row):
    locations = row.get("location")
    locations = locations if isinstance(locations,list) else [locations]
    countries = set()
    for location in locations:
        if isinstance(location,dict):
            address = location.get("address",{})
            if isinstance(address,dict) and address.get("addressCountry"):
                countries.add(str(address["addressCountry"]).lower().strip())
    if countries:
        return countries <= {"us","usa","united states","united states of america","remote"} and countries != {"remote"}
    return "United States of America" in row["description"][:600] or str(row.get("location","")).startswith("United States-")


def comparison_eligible(row):
    return us_eligible(row) and not source_date_conflict(row) and not re.search(r"\b20\d{2}\b|development program|new grad", row["title"] or "",re.I)


def pool(records):
    cells = defaultdict(list)
    for row in records:
        capture = row.get("archive_capture_at")
        if not row["historical"] or not row["archive_timestamp_verified"] or not capture or not comparison_eligible(row):
            continue
        year = int(capture[:4])
        role = family(row["title"] or "")
        if year in YEARS and role and identity(row) not in {identity(r) for r in cells[year, role]}:
            cells[year, role].append(row)
    return cells


def recover():
    amendment = json.loads((DATA / "scope-amendment.json").read_text())
    assert amendment["historical_payload_limit"] == 320
    collector = Collector()
    records = json.loads((DATA / "results.json").read_text())
    prior = DATA / "comparison-recovery-results.json"
    if prior.exists():
        records.extend(json.loads(prior.read_text()))
    cells = pool(records)
    candidates = defaultdict(list)
    for observation in json.loads((DATA / "comparison-discovery.json").read_text()):
        for row in observation["candidates"]:
            parts = urlsplit(row["original"]).path.split("/")
            if len(parts)>3 and parts[2].lower() in {"bengaluru","bangalore","alabang","toronto","nottingham","london","mexico-city"}:
                continue
            if len(parts)>3 and re.search(r"\b20\d{2}\b|development-program|new-grad",parts[3]):
                continue
            role = family(unquote(parts[3])) if len(parts)>3 else None
            if role:
                candidates[observation["year"], role].append(row)
    outcomes_path = DATA / "comparison-attempts.json"
    outcomes = json.loads(outcomes_path.read_text()) if outcomes_path.exists() else []
    attempted = {r["source_url"] for r in outcomes}
    added = json.loads(prior.read_text()) if prior.exists() else []
    # Round-robin prioritizes missing cells instead of spending on easy years first.
    while True:
        progressed = False
        for year in YEARS:
            for role in FAMILIES:
                if len(cells[year, role]) >= 2:
                    continue
                choices = candidates[year, role]
                while choices:
                    row = choices.pop(0)
                    url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
                    if url not in attempted:
                        break
                else:
                    continue
                used = sum(historical_payload(r["requested_url"])
                           for r in collector.requests.values())
                if used >= amendment["historical_payload_limit"]:
                    print("PARTIAL historical payload cap reached", flush=True)
                    return
                item = collector.fetch(url)
                item = {**item, "original_url":row["original"], "requested_archive_timestamp":row["timestamp"]}
                parsed = extract(collector.body(item), row["original"]) if item["outcome"] == "ok" else None
                capture = archive_evidence(item)
                if parsed:
                    result = record(item, parsed, historical=True)
                    added.append(result)
                    actual_family = family(result["title"] or "")
                    actual_year = int(capture[:4]) if capture else None
                    if actual_family and actual_year in YEARS and comparison_eligible(result):
                        cell = cells[actual_year, actual_family]
                        if identity(result) not in {identity(r) for r in cell}:
                            cell.append(result)
                outcomes.append(dict(source_url=url, original_url=row["original"], request_key=item["request_key"],
                                     year_target=year, family_target=role, outcome=item["outcome"],
                                     extracted=bool(parsed), archive_capture_at=capture))
                attempted.add(url)
                export(added, "comparison-recovery-results")
                atomic_json(outcomes_path, outcomes)
                print(f"COMPARISON {year} {role} {len(cells[year,role])}/2 {item['outcome']} extracted={bool(parsed)}", flush=True)
                progressed = True
        if not progressed or all(len(cells[y,f]) >= 2 for y in YEARS for f in FAMILIES):
            break


def curate():
    records = json.loads((DATA / "results.json").read_text())
    cells = pool(records)
    selected = []
    matrix = []
    for year in YEARS:
        for role in FAMILIES:
            # Favor reviewed records; keep distinct IDs and exact source versions intact.
            choices = sorted(cells[year, role], key=lambda r:(r["review_status"] != "validated", r["title"], r["version_key"]))[:2]
            for row in choices:
                selected.append({**row, "comparison_year":year, "comparison_family":role,
                                 "comparison_region":"United States",
                                 "comparison_year_basis":"verified archive capture year; publication date retained separately"})
            matrix.append(dict(year=year, family=role, target=2, recovered=len(choices),
                               version_keys=[r["version_key"] for r in choices]))
    export(selected, "comparison-results")
    atomic_json(DATA / "comparison-matrix.json", matrix)
    benchmark = []
    for role in FAMILIES:
        choices = [r for r in records if r["historical"] and r["archive_timestamp_verified"]
                   and r["archive_capture_at"][:4] in {"2013","2014"}
                   and r["review_status"] == "validated" and family(r["title"] or "") == role]
        if choices:
            benchmark.append({**min(choices,key=lambda r:r["archive_capture_at"]), "comparison_family":role})
    export(benchmark, "comparison-early-benchmark")
    print(json.dumps(dict(comparison_records=len(selected), complete_cells=sum(r["recovered"]==2 for r in matrix),
                         cells=len(matrix), early_benchmark=len(benchmark)), indent=2))


if __name__ == "__main__":
    import sys
    recover() if "--recover" in sys.argv else curate()
