"""WARC identity/timestamp validation must precede historical acceptance."""

import io
import json
import sys
from pathlib import Path

import pytest
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from phase0 import digest
from recover_commoncrawl import decode_warc


def fixture():
    url = "https://www.capitalonecareers.com/job/a/analyst/1732/1"
    body = ('<script type="application/ld+json">'+json.dumps(dict(
        **{"@type":"JobPosting"},title="Analyst",hiringOrganization={"name":"Capital One"},
        identifier="R1",description="<h2>Responsibilities</h2>Analyze risk<h2>Qualifications</h2>Degree"))+'</script>').encode()
    output = io.BytesIO()
    writer = WARCWriter(output, gzip=True)
    headers = StatusAndHeaders("200 OK",[("Content-Type","text/html")],protocol="HTTP/1.1")
    warc = writer.create_warc_record(url,"response",payload=io.BytesIO(body),http_headers=headers,
                                     warc_headers_dict={"WARC-Date":"2020-11-28T13:55:21Z"})
    writer.write_record(warc)
    raw = output.getvalue()
    item = dict(request_key="one",requested_url="https://data.commoncrawl.org/test.warc.gz",sha256=digest(raw),
                retrieved_at="2026-10-09T00:00:00+00:00",response_headers=[],artifact_path="test.bin")
    locator = dict(url=url,timestamp="20201128135521",length=str(len(raw)))
    return item,raw,locator


def test_warc_response_retains_actual_capture_and_payload_evidence():
    item,raw,locator = fixture()
    result = decode_warc(item,raw,locator,"index")[0]
    assert result["archive_timestamp_verified"]
    assert result["archive_capture_at"] == "2020-11-28T13:55:21+00:00"
    assert result["warc_evidence"]["target_uri"] == locator["url"]
    assert result["source_sha256"] == digest(raw)


@pytest.mark.parametrize("field,value",[("url","https://www.capitalonecareers.com/job/other"),
                                         ("timestamp","20201128135522")])
def test_mismatched_index_locator_is_not_verified(field,value):
    item,raw,locator = fixture()
    locator[field] = value
    with pytest.raises(AssertionError):
        decode_warc(item,raw,locator,"index")
