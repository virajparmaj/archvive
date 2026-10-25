# Capital One source profile

Collection date: October 8, 2026 in America/Chicago (October 9 UTC). This profile records observed source relationships, not an assertion that every historical recruitment domain has been found.

## Verified sources and ownership evidence

| Source | Relationship and observed patterns | Evidence |
|---|---|---|
| [Global careers board](https://www.capitalonecareers.com/search-jobs) | Capital One branding, employer descriptions, links to `www.capitalone.com`, regional boards, and the scoped Workday tenant. Modern detail URLs use `/job/<city>/<title>/<board-id>/<posting-id>`, including older `/-/-/` aliases. | Retained first search page; `current-inventory.json`; request key `813e3c154db426019d3996d7ea3f59c4823e91512b44b8253b9b433a6a6abea6`. |
| [Canada](https://www.capitalonecareers.ca/) | Linked by the global board; regional employer statement and `capitalone.wd12.myworkdayjobs.com/Capital_One` apply links. | `regional-probes.json`, `regional-inventories.json`, and raw role pages. |
| [United Kingdom](https://jobs.capitalone.co.uk/) | Linked by the global board; Capital One Europe employer statement; same scoped Workday tenant. | Regional root and detail artifacts, including `en-Uk` login link. |
| [Philippines](https://capitalonecareers.com.ph/career-opportunities.php) | Linked by the global board; Capital One Philippines Service Corp. employer statement. Five public PHP role pages link to specific Workday requisitions. | `philippines-inventory.json`; `philippines-probes.json`; raw role pages. Filename digits are not treated as publication dates. |
| [Workday](https://capitalone.wd12.myworkdayjobs.com/Capital_One) | Official careers boards link directly to tenant `capitalone`, board `Capital_One`. Public CXS inventory is `/wday/cxs/capitalone/Capital_One/jobs`; detail paths supply requisition IDs and descriptions. | `workday-inventory.json`; raw POST request bodies, responses, and apply URLs in careers HTML. |
| `capitalone.wd1.myworkdayjobs.com` | An older tenant host remains linked by the Philippines board. Association is verified by that link; historical payload coverage is unresolved. | Philippines root artifact and historical coverage probes. |
| `jobs.capitalone.com` | Verified archived Capital One detail pages use `/city/role-family/jobid<number>-<title>-jobs`. Descriptions, employer identity, and original URL replay headers agree. | [July 2013 example](https://web.archive.org/web/20130701151540id_/http://jobs.capitalone.com:80/chester/call-center-and-customer-service/jobid3739165-senior-risk-representative-jobs); benchmark artifacts and response headers. Present DNS failures are recorded as unknown availability. |
| `cscapitalone.taleo.net` | Legacy ATS links appear in attributable recruiting material and archived Capital One pages; `careersection/usx/jobdetail.ftl?lang=en&job=<reference>` and a section-less variant are preserved. | [USC recruiting copy](https://cse.sc.edu/job/capital-one-it-development-program), [AEA 2013 copy](https://www.aeaweb.org/joe/archive/listing.php?JOE_ID=201312_399328), archived official pages. The Taleo job reference differs from the legacy careers site's job ID. |

The global collection includes postings with locations in the United States, Canada, United Kingdom, India, Mexico, Philippines, and Singapore. “Remote” is retained when a source uses it as a country value; it is not counted as a verified country. Observed careers HTML declares English. Workday API records without an explicit language remain null. No additional language board was verified in this investigation.

## Earlier leads and secondary sources

The `capitalone.taleo.net` tenant has a February 18, 2012 indexed/replayed lead for job `712390`, but its retained response is only a redirect document. It does not establish a recovered description or independently confirm that tenant's ownership. `www.capitalone-campus.com` is mentioned by the 2014 university copy; its content and ownership were not independently verified. Bare `capitalonecareers.com` links also occur in recruiting copies and remain aliases/leads, not additional counted boards.

[AEA's December 2013 issue](https://www.aeaweb.org/joe/archive/listing.php?JOE_ID=201312_399327), the USC March 25, 2014 copy, and two [UCF recruiting PDFs](https://sciences.ucf.edu/statistics/dms/wp-content/uploads/sites/8/2014/01/Capital-One-Statistician-Analyst-Development-Program-749588.pdf) preserve attributable text. These are separate source versions. AEA issue dates have month precision; USC has a day-level copy publication date. The UCF upload path and graduation windows are contextual evidence, not verified publication or archive dates. Two AEA copies lack an identifiable original detail URL, which stays null.

Wayback CDX supplies candidate URLs and capture observations. A historical timestamp is accepted only from a direct replay whose final replay timestamp, `Memento-Datetime`, and `Link: rel="original"` agree. Rendered CDX transport is discovery evidence only. Five recovered versions with double-escaped original links remain timestamp-unverified.

Common Crawl exposes collection indexes and bounded WARC locators. Neighboring indexes establish Capital One coverage even where initial gateway failures were inconclusive. Record status, target URL, timestamp, filename, offset, and length are retained; an index hit alone is not a recovered description.

One 2020 response was recovered directly by byte range and verified against the WARC target URI/date and index locator. Wayback identifies the same WARC as its upstream source. The two retrieval routes share one historical capture and identical text; both evidence records survive without inventing an additional version.

## Collection boundaries

The main, Canada, and UK inventories use root `/search-jobs?p=N` pagination and verify the returned page number and totals. The published `/search-jobs/` robots exclusion was not used as an AJAX collection route. Workday's public endpoint was checked against its robots response. The Philippines board is a finite linked list without a reported total; “complete” there means all five linked role pages, not every vacancy that might exist elsewhere.

All source artifacts are inert. Archived scripts are not executed and cannot fetch today's ATS content into a historical record. Same-title postings stay separate; exact requisition/reference IDs support aliases, while different texts and sources retain separate versions. Source warnings preserve malformed regional `hiringOrganization` fields rather than silently correcting the source.

The local evidence registry is [requests.jsonl](../data/capital-one/requests.jsonl); board inventories and raw artifacts are under the gitignored [collection directory](../data/capital-one/). The checked-in research scripts are investigation helpers, not an engine API.
