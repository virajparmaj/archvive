"""Recheck human source-review expectations offline; this is a development set."""

import json

from phase0 import DATA, archive_evidence, atomic_json, digest, extract

EXPECTED = [
    ("1a3abc00d65f403656261e45e7ec603b4bc3db279167f0d869287e65b957bb59", "Senior Risk Representative", "High School Diploma", "3739165"),
    ("392f2e8fb20b39602341f942c466ce91cdc65ac988ff3d0f36fb6fe1efce871a", "Director, Data Analysis", "5 years of People Management", "R76225"),
    ("7eb97ee99086ebbf1fed7cb75e7af9193b5eb9743a20e08b040bf648e9046756", "Principal Process Manager, Digital Accessibility", "Web Content Accessibility Guidelines", "R76230"),
    ("59789ad6b36f108796b953134ad97a19e675c64d3c133678cd27314f657b9d30", "Lead Data Engineer (Remote Eligible)", "2 years of experience in big data", "R143487"),
    ("bb876de2ddab7d7386f6017e03b5a3c4d51e1ee054ef48e3d43f9dbac2f34f26", "Lead Software Engineer, Back End (Remote Eligible)", "6 years of professional software engineering", "R143912"),
    ("3a2016303bc500b8bf4745f5bb26bdea80b73a07f0ca09ffdb4825adc9ceeecd", "Principal Associate, UX/UI Designer - EPX.xd", "4 years of experience with UX", "R189247"),
    ("85bd432e39e42239b3a08d08adfb427c1444de5ac7427cacb5282db875f0cb4d", "Lead UX/UI Designer - Audit.xd", "6 years of experience with UX", "R195205"),
    ("27277b3b0bb2f4534ea52dd6b0e9f8465df97025bc857b7f3a233d3f43bb8323", "Regional Engagement Lead, Community Impact & Investment", "3 years of experience in people leadership", "R239707"),
    ("85606e15ab77bd12c2618f2b3d0f0a2b884fe815a203c0cf593e3e75cd0fc4ec", "Current PhD, Applied Research Internship Program - Summer 2026", "Currently enrolled in an accredited PhD Program", "R218606"),
    ("e27d0af989e8af3df011bdc18a883d55c9d162eb4dd6c68462fd93a96b4afd4d", "Part Time Teller Bypass Branch Abbeville", "6 months of Sales experience", "776415"),
    ("119daae7fefe6ddbb1e24428d391ed821e8182e5710f677b7df932805dfc5762", "UX Researcher", "3 years of UX research experience", "R112433"),
]
NEGATIVES = [
    ("ecd82a6d40c354994674f536bbe419139fbbe82765e5abbe455b6375838a2c55", "2012 redirect document has no role description"),
    ("7f8772703e0806058dccb8f1b7cfee8e400e010205d7ac702fcd5858870cdabd", "Taleo Career Section Unavailable is a maintenance notice, not closure"),
    ("17006e3c60f4857e48e892a03f7309bd8010163d30afdad8e2e018365685e534", "Location suffix is an Arlington marketing page, not the job"),
    ("fa2f7d204c4d23f2bf551c4296827e6963fa90d42156ec52a0770034ed84d29e", "Current original returns HTTP 404 and Custom Job Error, not a description"),
]


def main():
    requests = {r["request_key"]: r for r in map(json.loads, (DATA / "requests.jsonl").read_text().splitlines())}
    reviews = []
    for key, title, phrase, identifier in EXPECTED:
        item = requests[key]
        body = (DATA / item["artifact_path"]).read_bytes()
        original = item["requested_url"].split("id_/", 1)[1]
        result = extract(body, original)
        checks = dict(hash=digest(body) == item["sha256"], title=result["title"] == title,
                      qualification=phrase in result["description"],
                      identity=identifier in json.dumps(result["identifiers"]),
                      capture_verified=bool(archive_evidence({**item, "original_url": original})),
                      no_related_jobs="Related Jobs" not in result["description"])
        reviews.append(dict(request_key=key, expected_title=title, expected_identifier=identifier,
                            expected_qualification=phrase, original_url=original, checks=checks,
                            passed=all(checks.values()), artifact_path=item["artifact_path"],
                            sha256=item["sha256"], sample_role="development", expected_extraction="role description",
                            review_method="Source title, role ID, duties/qualification boundaries, replay headers and section text inspected"))
    for key, reason in NEGATIVES:
        item = requests[key]
        body = (DATA / item["artifact_path"]).read_bytes()
        original = item["requested_url"].split("id_/", 1)[-1]
        reviews.append(dict(request_key=key, original_url=original, artifact_path=item["artifact_path"],
                            expected_extraction="none", reason=reason, sha256=item["sha256"],
                            passed=extract(body, original) is None and digest(body) == item["sha256"],
                            sample_role="development"))
    atomic_json(DATA / "manual-review.json", reviews)
    metrics = dict(cases=len(reviews), passed=sum(r["passed"] for r in reviews))
    atomic_json(DATA / "manual-review-results.json", metrics)
    print(metrics)
    if metrics["passed"] != metrics["cases"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
