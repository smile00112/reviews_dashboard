# Feature Specification: Twice-Daily Review Sync with Removal Tracking

**Feature Branch**: `011-review-removal-sync`

**Created**: 2026-07-19

**Status**: Draft

**Input**: User description: "Twice-daily scheduled review sync with removal tracking. On production, run the metrics job twice a day and the reviews job twice a day for all platforms (Yandex, 2GIS). The reviews job must trigger a scrape whenever the platform's review count differs from the count of locally stored non-removed reviews — in either direction (reviews can be added by users, or removed by the platform / successfully disputed by the organization). Reviews that disappear from the platform must be marked as removed (kept in the database, visible as removed, excluded from count comparison), and only after a full, non-truncated scrape pass. A review that reappears must be un-marked, not duplicated. Optionally force a periodic full scrape to cover the blind spot where additions and removals cancel out."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detect and record reviews removed from the platform (Priority: P1)

An operator tracks an organization whose review was taken down by the platform (moderation) or successfully disputed by the organization. Today the dashboard keeps showing that review as if it were still live, and the platform's review counter permanently disagrees with the local count, so the nightly sync either skips the organization forever or can never reconcile. After this feature, a completed full re-scrape marks the disappeared review as "removed from platform" with the date it was noticed. The review stays in the dashboard history, clearly labeled, and no longer counts toward the "collected reviews" total used for sync decisions.

**Why this priority**: This is the core data-correctness gap. Without removal tracking, the count comparison that drives the whole automated sync is permanently poisoned the first time any review disappears upstream, and the twice-daily schedule (P3) would waste scrapes or silently skip stale organizations.

**Independent Test**: Seed an organization with collected reviews, simulate a full scrape result that no longer contains one of them, and verify: that review is marked removed with a timestamp, remains readable in the dashboard flagged as removed, and the organization's non-removed count now matches the platform counter.

**Acceptance Scenarios**:

1. **Given** an organization with 10 collected reviews and a platform counter of 9, **When** a full scrape pass completes successfully and returns only 9 of those reviews, **Then** the missing review is marked as removed with the detection date, and the non-removed local count equals 9.
2. **Given** a scrape pass that was truncated (page/volume limits reached before the end of the platform's list) or ended with an error or a manual-action outcome, **When** the pass finishes, **Then** no review is marked as removed as a result of that pass.
3. **Given** a review previously marked as removed, **When** a later scrape finds the identical review again on the platform, **Then** the existing record is un-marked (no longer removed) and no duplicate record is created.
4. **Given** a review marked as removed, **When** an operator views the organization's reviews, **Then** the removed review is not shown in the default list but can be seen via an explicit "show removed" view, labeled as removed with the detection date.

---

### User Story 2 - Sync triggers on any counter mismatch, in both directions (Priority: P2)

The automated reviews job compares the platform's public review counter with the number of locally collected (non-removed) reviews. Today it only reacts when the platform shows *more* reviews than collected; a *lower* platform counter (reviews deleted or disputed upstream) is skipped with a note. After this feature, any difference — higher or lower — triggers a collection pass for that organization, so removals are discovered by the same mechanism as additions.

**Why this priority**: This is the decision rule that makes P1 reachable automatically. It depends on P1 (excluding removed reviews from the local count) to avoid re-scraping the same organization forever after a removal.

**Independent Test**: Run the reviews job against organizations in the three counter states (platform higher, equal, lower) and verify: higher → scrape, lower → scrape, equal → skip, and each decision is recorded with a human-readable reason.

**Acceptance Scenarios**:

1. **Given** a platform counter of 12 and 10 non-removed collected reviews, **When** the reviews job processes the organization, **Then** a collection pass runs.
2. **Given** a platform counter of 8 and 10 non-removed collected reviews, **When** the reviews job processes the organization, **Then** a collection pass runs (instead of today's "platform shows fewer reviews" skip).
3. **Given** a platform counter of 10, 10 non-removed collected reviews and 2 removed ones, **When** the reviews job processes the organization, **Then** the organization is skipped with a "counters match" reason (removed reviews do not count).
4. **Given** an unknown platform counter (metrics never collected), **When** the reviews job processes the organization, **Then** the organization is skipped with a reason pointing to metrics collection, unchanged from today.

---

### User Story 3 - Twice-daily automated schedule on production (Priority: P3)

The operator team wants ratings/counters refreshed and review mismatches acted on twice a day without manual triggers: a morning cycle and an afternoon cycle, metrics first, reviews about an hour later so the comparison always sees fresh counters.

**Why this priority**: Pure operations value on top of P1+P2. The scheduling capability already exists (per-job editable cron); this story is about the recommended twice-daily configuration being documented and applied on production.

**Independent Test**: Set the documented twice-daily schedules on a running instance, verify each of the four jobs (metrics/reviews × Yandex/2GIS) fires at both configured times of day and that a reviews cycle observes counters updated by the same day's preceding metrics cycle.

**Acceptance Scenarios**:

1. **Given** the four jobs enabled with the documented twice-daily schedules, **When** a scheduled day passes, **Then** each job has two runs recorded for that day, and each reviews run starts after the same cycle's metrics run for the same platform has finished its schedule slot.
2. **Given** a job run still in progress when its second daily slot fires, **When** the scheduler triggers, **Then** the duplicate trigger is rejected exactly as it is today for overlapping runs.

---

### User Story 4 - Periodic forced full pass (blind-spot coverage) (Priority: P4)

If one review is added and another is removed between two sync cycles, the counters can match while the local data is stale. An optional per-job setting forces a full collection pass for every organization every N days regardless of counter match, putting an upper bound on how long such silent drift can persist.

**Why this priority**: Covers a rare edge case; valuable but not required for the primary flows to work.

**Independent Test**: Configure the forced-pass interval to N days, give an organization matching counters and a last full pass older than N days, run the reviews job, and verify a collection pass runs with a reason indicating the forced refresh; with a recent full pass, verify the normal "counters match" skip.

**Acceptance Scenarios**:

1. **Given** matching counters and a last successful full pass older than the configured interval, **When** the reviews job processes the organization, **Then** a full collection pass runs and the decision reason names the forced refresh.
2. **Given** matching counters and a last successful full pass within the interval, **When** the reviews job processes the organization, **Then** the organization is skipped as today.
3. **Given** the setting is absent or disabled, **When** the reviews job runs, **Then** behavior is identical to P2 rules only.

---

### Edge Cases

- **Truncated pass must never mark removals.** Collection has volume/page safety limits; a pass that stops early sees only a prefix of the platform's list. Marking unseen reviews as removed would mass–false-flag the tail. Removal marking is allowed only when the pass demonstrably reached the end of the platform's list and completed successfully.
- **Pass ends in `needs_manual_action` (captcha/bot-wall) or failure mid-way**: no removal marking, decision recorded, unchanged failure semantics (debug artifacts, statuses) per existing constitution rules.
- **Review reappears after being marked removed** (e.g. platform reinstates it after appeal): the identical content maps to the existing record, which is un-marked; the dedup contract guarantees no duplicate row.
- **Platform counter is stale or wrong** (platform caches its own counter): the job may scrape and find nothing new; the pass completes, marks nothing removed (everything was seen), counters still disagree → the organization will be retried next cycle. Acceptable: bounded by two cycles/day; no infinite tight loop within a single run.
- **All reviews removed upstream** (counter drops to 0 with collected reviews present): a full pass returning zero reviews while ending "complete and successful" is suspicious — indistinguishable from a parsing regression. Guard: a full pass that returns zero reviews for an organization that previously had collected reviews must NOT mark all of them removed; it must surface as an anomaly for operator attention instead.
- **Removal detection with mixed platforms**: removal marking for one platform's pass must only consider that organization's reviews on that platform, never the other platform's rows.
- **Counters equal but composition changed** (+1/−1 between cycles): not detected by P2 rules; bounded by the P4 forced pass if enabled, otherwise accepted as a known limitation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record, per collected review, whether it is currently present on its platform or has been observed as removed, including the date removal was first detected. Removed reviews MUST be retained, never deleted.
- **FR-002**: The system MUST mark reviews as removed only from a collection pass that (a) completed successfully and (b) demonstrably covered the platform's full review list for that organization (not stopped by volume/page safety limits, errors, or manual-action outcomes). Any other pass MUST leave removal state untouched.
- **FR-003**: Every collection pass MUST record whether it covered the full list (full pass vs. partial pass) so that downstream decisions and operators can tell them apart.
- **FR-004**: A review found on the platform again after being marked removed MUST have its removal state cleared on the existing record; the deduplication contract (content-hash identity, no duplicate rows) MUST remain unchanged.
- **FR-005**: The automated reviews job MUST trigger a collection pass whenever the platform's review counter differs in either direction from the count of non-removed collected reviews for that organization and platform, and MUST skip when they are equal. Unknown platform counters keep today's skip-with-reason behavior.
- **FR-006**: Removed reviews MUST be excluded from the collected-review count used in the job's comparison and from default review listings; operators MUST be able to view removed reviews explicitly, labeled with removal date. Existing exports/analytics defaults MAY continue to include them only if clearly distinguishable (see Assumptions).
- **FR-007**: Every job decision (scrape or skip) MUST record a human-readable reason including the counters compared, as today.
- **FR-008**: A full pass that returns zero reviews for an organization that previously had non-removed collected reviews MUST NOT mark those reviews removed and MUST surface the anomaly for operator attention.
- **FR-009**: The recommended twice-daily production schedule (metrics cycle, then reviews cycle ~1 hour later, morning and afternoon) MUST be documented, and applying it MUST require no code change (schedules stay editable per job as today).
- **FR-010**: The system SHOULD support an optional per-job interval setting that forces a full collection pass for an organization when its last successful full pass is older than the interval, even when counters match; the decision reason MUST name the forced refresh. Absent/disabled ⇒ behavior identical to FR-005.
- **FR-011**: Removal marking MUST be scoped to the organization and platform of the pass that ran; reviews of other platforms or organizations MUST never be affected.
- **FR-012**: The change MUST be additive to stored data (no destructive migration of existing reviews); existing reviews start as "present" (not removed).

### Key Entities

- **Review**: an individual collected review; gains a removal state — "present on platform" or "removed from platform since [date]". Identity and deduplication attributes are unchanged.
- **Collection pass (scrape run)**: one attempt to collect an organization's reviews on one platform; gains a "full list covered" indicator alongside its existing status, counters, and timestamps.
- **Reviews job / job run item**: the per-organization automated decision record; its skip/scrape reasons now reflect two-direction comparison, the zero-result anomaly, and (optionally) forced refresh.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a review disappears from a platform, the dashboard reflects it as removed within at most two scheduled sync cycles (≤ 1 calendar day at the twice-daily schedule) without any operator action.
- **SC-002**: An organization whose platform counter is lower than the collected count is no longer skipped: the next scheduled reviews run processes it, and after one full pass its counters reconcile (non-removed collected count equals the platform counter).
- **SC-003**: Zero duplicate reviews are created by removal/reappearance flows: a reinstated review resolves to its existing record 100% of the time in the automated test suite.
- **SC-004**: No review is ever marked removed by a truncated, failed, or manual-action pass in the automated test suite (0 false removals across those scenarios).
- **SC-005**: With the documented schedule applied, each platform gets counters refreshed and mismatches acted on twice per calendar day, observable in the job run history.
- **SC-006**: Operators can, from the dashboard, list an organization's removed reviews with their removal dates without database access.

## Assumptions

- The existing per-job editable schedule mechanism is sufficient for twice-daily operation; this feature documents recommended schedule values rather than adding scheduling capability. Overlap protection (rejecting a trigger while a run is active) already exists and is unchanged.
- "Full list covered" is determinable by the collection mechanism itself (pagination exhausted / end of list reached before any safety cap); when coverage cannot be determined, the pass MUST be treated as partial (safe default — no removal marking).
- The platform counter used for comparison is the one already collected by the metrics job; its freshness is bounded by the metrics schedule, which is why the reviews cycle is scheduled after the metrics cycle.
- Removed reviews remain included in raw exports and historical analytics unless a consumer explicitly filters them; the only counts that MUST exclude them are the job's sync comparison and default dashboard listings. Analytics recomputation over removed reviews is out of scope.
- Restoring/appealing reviews on the platform, notifying operators in real time, and any write action toward the platforms remain out of scope (read-only constitution principle).
- The zero-result anomaly (FR-008) surfaces through existing failure/attention channels (run status + reason, attention rules); a dedicated notification system is out of scope.
- Organizations participate in the sync when they have the platform URL/identifier filled in, as today; a dedicated "active point" on/off flag is not introduced by this feature (can be added later as a small separate change).
