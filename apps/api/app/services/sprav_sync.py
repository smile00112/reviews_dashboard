"""Plan and apply a Sprav-cabinet → ``organizations`` sync.

Read-only against Yandex (constitution hard rule): the cabinet is only *read*;
the sole writes are to our own DB, and even those are opt-in (the caller runs a
dry-run first and applies only on confirmation).

The plan builder is pure — no network, no DB queries. It takes the cabinet
branches already matched to our organizations (via ``services.sprav_branch_match``)
plus a ``resolve_maps_url`` callback, and returns a :class:`SyncPlan` of the four
outcomes. Keeping the I/O in a callback is what lets the branching rules be
contract-tested without Playwright — ``test_sprav_sync.py``.

Sync rules (confirmed with the operator, see
``docs/superpowers/specs/2026-07-23-yandex-org-sync-design.md``):

* **deactivate** — our active point whose ``external_id`` is set but absent from
  the chain's cabinet permalinks. Points with **no** ``external_id`` are never
  deactivated (a missing match there means "unidentified", not "removed").
* **update** — a matched point whose fields differ from the cabinet.
* **new_in_cabinet** — a cabinet branch that matched no point (report only).
* **ambiguous** — our point with no ``external_id`` that matched nothing (report
  only, never touched).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from app.models.organization import Organization
from app.scraper.yandex_sprav_chain import SpravBranch
from app.services.sprav_branch_match import BranchMatch

# The permanent_id inside a Maps url, with or without a slug segment:
#   /maps/org/17369842518            → 17369842518
#   /maps/org/sushi_master/17369842518 → 17369842518
# A short /maps/-/CODE link carries no permanent_id and yields None.
_PID_IN_URL = re.compile(r"/org/(?:[^/]+/)?(\d+)")

# Fields the sync may write. rating/review_count are deliberately absent — the
# review scrapers own those.
ResolveMapsUrl = Callable[[SpravBranch], "str | None"]


def permanent_id_in_url(url: str | None) -> str | None:
    """The permanent_id embedded in a Maps url, or None (e.g. a /maps/-/CODE link)."""
    if not url:
        return None
    match = _PID_IN_URL.search(url)
    return match.group(1) if match else None


def maps_url_for(permanent_id: str) -> str:
    """The canonical slug-less Maps url for a permanent_id."""
    return f"https://yandex.ru/maps/org/{permanent_id}"


@dataclass
class FieldUpdate:
    """A matched point and the field changes the cabinet implies for it.

    ``changes`` maps a column name to ``(old, new)`` so the report can show the
    diff and :func:`apply_plan` can write it back generically.
    """

    organization: Organization
    branch: SpravBranch
    changes: dict[str, tuple[object, object]]


# A branch is "open" only in this state; everything else (closed,
# temporarily_closed, unpublished…) counts as not-open for the sync.
OPEN_STATUS = "publish"


@dataclass
class SyncPlan:
    deactivate: list[Organization] = field(default_factory=list)
    update: list[FieldUpdate] = field(default_factory=list)
    new_in_cabinet: list[SpravBranch] = field(default_factory=list)
    ambiguous: list[Organization] = field(default_factory=list)
    # Cabinet branches that are not open AND match no point of ours. We do not
    # pull their data in (report only) — an open branch we don't have is a real
    # candidate, a closed one we never had is not.
    skipped_closed: list[SpravBranch] = field(default_factory=list)


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _url_changes(
    org: Organization,
    branch: SpravBranch,
    resolve_maps_url: ResolveMapsUrl,
) -> dict[str, tuple[object, object]]:
    """external_id / normalized_url changes for one matched point.

    Split by whether the point already carries an ``external_id``:

    * **has external_id** — the branch permanent_id is authoritative and already
      known from the branch list; touch ``normalized_url`` only when the id it
      currently embeds disagrees (the Maps card was recreated under a new id).
      No edit/main fetch.
    * **no external_id** — its ``normalized_url`` is a short /maps/-/CODE link
      with no permanent_id, so fetch the branch's /p/edit/main Maps link via
      ``resolve_maps_url`` and fill both ``external_id`` and ``normalized_url``.
      This is the only path that pays for the per-point request.
    """
    changes: dict[str, tuple[object, object]] = {}
    if org.external_id:
        if permanent_id_in_url(org.normalized_url) != branch.permanent_id:
            new_url = maps_url_for(branch.permanent_id)
            if org.normalized_url != new_url:
                changes["normalized_url"] = (org.normalized_url, new_url)
        return changes

    resolved = resolve_maps_url(branch)
    if not resolved:  # throttled / unavailable — leave the point untouched
        return changes
    new_pid = permanent_id_in_url(resolved) or branch.permanent_id
    changes["external_id"] = (org.external_id, new_pid)
    if org.normalized_url != resolved:
        changes["normalized_url"] = (org.normalized_url, resolved)
    return changes


def _diff(
    org: Organization,
    branch: SpravBranch,
    resolve_maps_url: ResolveMapsUrl,
) -> dict[str, tuple[object, object]]:
    """Every field the cabinet would change on this matched point."""
    changes: dict[str, tuple[object, object]] = {}

    if branch.name and branch.name != org.name:
        changes["name"] = (org.name, branch.name)
    if branch.address and branch.address != org.address:
        changes["address"] = (org.address, branch.address)
    # region only fills a gap — never overwrites an existing value.
    if branch.region and _blank(org.region):
        changes["region"] = (org.region, branch.region)
    # A closed cabinet listing deactivates; 'publish' never auto-reactivates.
    if branch.publishing_status == "closed" and org.is_active:
        changes["is_active"] = (org.is_active, False)

    changes.update(_url_changes(org, branch, resolve_maps_url))
    return changes


def build_plan(
    matches: list[BranchMatch],
    organizations: list[Organization],
    resolve_maps_url: ResolveMapsUrl,
    allow_deactivation: bool = True,
) -> SyncPlan:
    """Turn matched branches + our organizations into a :class:`SyncPlan`.

    ``matches`` is one :class:`BranchMatch` per cabinet branch (the output of
    ``match_branches``); ``organizations`` is the full pool for the chain's
    company. ``resolve_maps_url`` is called at most once per matched point that
    lacks an ``external_id``.

    ``allow_deactivation=False`` suppresses the deactivate bucket entirely. Pass
    it whenever the cabinet branch list was read only **partially** (throttling,
    an unreached page): absence from a truncated list is not a removal, and
    deactivating on it silently closes live points. Only a **complete** read may
    deactivate — the same invariant the review scraper's corroborated full pass
    enforces.
    """
    plan = SyncPlan()
    cabinet_pids = {m.branch.permanent_id for m in matches}
    matched_org_ids: set = set()

    for match in matches:
        if match.organization is None:
            # An open branch we don't have is a real "new point" candidate; a
            # closed one we never tracked is not pulled in.
            if match.branch.publishing_status == OPEN_STATUS:
                plan.new_in_cabinet.append(match.branch)
            else:
                plan.skipped_closed.append(match.branch)
            continue
        matched_org_ids.add(match.organization.id)
        changes = _diff(match.organization, match.branch, resolve_maps_url)
        if changes:
            plan.update.append(FieldUpdate(match.organization, match.branch, changes))

    for org in organizations:
        if org.id in matched_org_ids:
            continue
        if allow_deactivation and org.external_id and org.external_id not in cabinet_pids and org.is_active:
            plan.deactivate.append(org)
        elif _blank(org.external_id):
            plan.ambiguous.append(org)
        # else: external_id present but in cabinet (or the read was partial) —
        # not a confirmed removal, nothing to do.

    return plan


def apply_plan(plan: SyncPlan) -> dict[str, int]:
    """Mutate the ORM objects in ``plan`` in place. The caller commits.

    Returns counts per outcome. Only ``deactivate`` and ``update`` write;
    ``new_in_cabinet`` and ``ambiguous`` are report-only and untouched.
    """
    for org in plan.deactivate:
        org.is_active = False
    for item in plan.update:
        for field_name, (_old, new) in item.changes.items():
            setattr(item.organization, field_name, new)
    return {
        "deactivated": len(plan.deactivate),
        "updated": len(plan.update),
        "new_in_cabinet": len(plan.new_in_cabinet),
        "ambiguous": len(plan.ambiguous),
        "skipped_closed": len(plan.skipped_closed),
    }
