# Contract: GET /api/dashboard/overview — payload unchanged, query budget bounded

**Feature**: 012-dashboard-overview-perf

## Payload contract

The endpoint contract is **identical** to feature 009: see
[specs/009-network-overview/contracts/dashboard-overview.md](../../009-network-overview/contracts/dashboard-overview.md).
Same route, parameters (`period`, `platform`, `org_ids`, `company_id`), auth, status codes,
response schema (`DashboardOverview`), and — critically — same **values** for any given
database state. Only `generated_at` may differ between two live calls.

Executable form of this contract: `apps/api/tests/test_dashboard_overview.py` and
`apps/api/tests/test_dashboard_attention_rules.py` MUST pass **without modification**.

## Performance contract

| Guarantee | Bound |
|---|---|
| SELECT count per overview request | constant w.r.t. organization count AND review count; + O(enabled count-type attention rules) |
| Rows materialized per request | O(orgs) + O(period rows with responses) + O(14-day rows with problems) — never O(total reviews) |
| Columns loaded from `reviews` | never `review_text`; `problems` only for the 14-day window |
| Response time (production data, default filters) | < 300 ms (p95 < 500 ms) |
| Platform-filtered request | no second scan; ≤ cost of unfiltered request |

Guard test: `test_query_counts.py::test_overview_query_count_does_not_scale_with_orgs`
(kept) plus a new case asserting the SELECT count does not grow with review volume.
