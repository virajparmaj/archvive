"""Comparison eligibility and identity checks are independent of network access."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from comparison import family, pool


def test_family_handles_accents_and_excludes_interns_and_executives():
    assert family("Café Ambassador - Boston Metro") == "customer_operations"
    assert family("Software Engineering Intern") is None
    assert family("Director, Data Analysis") is None
    assert family("Senior Software Engineer") == "software_engineering"
    assert family("Lead UX/UI Designer - Audit.xd") is None
    assert family("Manager, Internal Audit") == "risk_compliance"


def test_panel_uses_verified_capture_year_and_unique_requisitions():
    row = dict(title="Senior Software Engineer", historical=True, archive_timestamp_verified=True,
               archive_capture_at="2020-11-01T00:00:00+00:00", original_url="https://example/job/1",
               identifiers={"requisition_id":"R1"}, source_declared_dates={"datePosted":"2019-12-01"},
               location={"address":{"addressCountry":"United States"}},description="Duties")
    duplicate = {**row,"original_url":"https://example/job/alias"}
    different = {**row,"identifiers":{"requisition_id":"R2"}}
    live = {**row,"historical":False}
    unverified = {**row,"archive_timestamp_verified":False}
    recent = {**row,"archive_capture_at":"2026-01-01T00:00:00+00:00"}
    foreign = {**row,"identifiers":{"requisition_id":"R3"},"location":{"address":{"addressCountry":"India"}}}
    cells = pool([row,duplicate,different,live,unverified,recent,foreign])
    assert len(cells[2020,"software_engineering"]) == 2
    assert (2019,"software_engineering") not in cells
    assert (2026,"software_engineering") not in cells
