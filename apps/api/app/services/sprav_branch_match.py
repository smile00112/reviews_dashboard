"""Match Sprav chain branches to our organizations.

The cabinet identifies a branch by its Maps permalink, which is exactly
``Organization.external_id`` — for the organizations that have one. Roughly half
of ours were imported with short ``/maps/-/CODE`` links instead and carry no
permalink at all, so those need a second route.

That route leans on a convention in our own data: organization names encode
``Город-NN Улица Дом`` (``Ростов-на-Дону-08 Буденовский 68``). Matching on city
plus house number plus street-token overlap recovers most of them.

The fallback is deliberately **conservative**: it refuses whenever two
candidates tie, and it scores a house number whose literal suffix disagrees
("21" vs "21А") below an exact hit. Calibrating it against the branches we can
match exactly is the point of ``calibrate`` — a fallback that guesses wrong is
worse than one that abstains, because a wrong match silently attributes one
branch's ratings to another.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.models.organization import Organization
from app.scraper.yandex_sprav_chain import SpravBranch

# Street-type words and administrative noise carry no discriminating power:
# every address has them, so they would inflate every overlap score equally.
_STOP_WORDS = frozenset(
    {
        "улица", "ул", "проспект", "пр", "проезд", "переулок", "пер", "шоссе", "ш",
        "бульвар", "площадь", "пл", "микрорайон", "мкр", "квартал", "тракт",
        "набережная", "наб", "аллея", "тц", "трц", "тк", "г", "город", "им", "имени",
        "россия", "федерация", "округ", "область", "край", "республика",
        "городской", "муниципальный", "район", "федеральный", "автономный",
    }
)

_HOUSE_RE = re.compile(r"\b(\d+)\s*([а-я]?)\b")
# Organization names lead with "Город-NN ...", but the city itself may contain
# hyphens (Ростов-на-Дону-08), so split on the numeric branch index, not the
# first dash.
_CITY_RE = re.compile(r"^(.*?)-\d+\b")
_HOUSE_SUFFIXES = "абвгдежзийклмнопрстуфхцчшщэюя"

# Confidence ceiling when only the bare house number agrees, not its suffix.
_LOOSE_HOUSE_CAP = 0.75
# Awarded when city and house agree but neither side offers street evidence.
_NO_STREET_EVIDENCE = 0.55


@dataclass
class BranchMatch:
    """One branch and the organization it was matched to, if any."""

    branch: SpravBranch
    organization: Organization | None
    method: str | None  # "external_id" | "address" | None
    confidence: float


def normalize(text: str | None) -> str:
    """Casefold, unify ё/е, and reduce punctuation to single spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", " ", text).strip()


def street_tokens(text: str | None) -> set[str]:
    """Words that actually identify a street — no stop words, no bare numbers."""
    return {t for t in normalize(text).split() if t and t not in _STOP_WORDS and not t.isdigit()}


def house_numbers(text: str | None) -> set[str]:
    """House numbers as digit + optional letter, e.g. '2в', '37а'."""
    return {f"{digits}{suffix}" for digits, suffix in _HOUSE_RE.findall(normalize(text))}


def organization_city(org: Organization) -> str:
    """City from the 'Город-NN ...' name convention, falling back to the column."""
    match = _CITY_RE.match(org.name or "")
    if match:
        head = match.group(1)
    else:
        head = (org.name or "").split()[0] if org.name else ""
    return normalize(head) or normalize(org.city)


def score(branch: SpravBranch, org: Organization) -> float:
    """Confidence in 0..1 that this branch is this organization."""
    branch_city = normalize(branch.city)
    if not branch_city or branch_city != organization_city(org):
        return 0.0

    branch_houses = house_numbers(branch.address)
    org_houses = house_numbers(org.name)
    exact_house = bool(branch_houses & org_houses)
    # "32" vs "32/Б", "21А" vs "21" — the building agrees, the literal does not.
    loose_house = bool(
        {h.rstrip(_HOUSE_SUFFIXES) for h in branch_houses} & {h.rstrip(_HOUSE_SUFFIXES) for h in org_houses}
    )
    if not (exact_house or loose_house):
        return 0.0
    cap = 1.0 if exact_house else _LOOSE_HOUSE_CAP

    branch_words = street_tokens(branch.address) - {branch_city}
    org_words = street_tokens(org.name) - {organization_city(org)}
    if not branch_words or not org_words:
        return min(_NO_STREET_EVIDENCE, cap)
    overlap = len(branch_words & org_words) / len(org_words)
    return min(0.6 + 0.4 * overlap, cap)


def best_match(branch: SpravBranch, candidates: list[Organization]) -> tuple[Organization | None, float]:
    """Highest-scoring candidate, or (None, 0.0) when nothing scores or two tie."""
    ranked = sorted(((score(branch, org), org) for org in candidates), key=lambda pair: -pair[0])
    if not ranked or ranked[0][0] == 0.0:
        return None, 0.0
    top_score, top_org = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if runner_up >= top_score:  # ambiguous — refuse rather than guess
        return None, 0.0
    return top_org, top_score


@dataclass
class Calibration:
    """How the address fallback behaves on branches whose answer we already know."""

    checked: int = 0
    correct: int = 0
    refused: int = 0
    wrong: int = 0

    @property
    def is_trustworthy(self) -> bool:
        """A single wrong answer disqualifies it — refusals are the safe failure."""
        return self.wrong == 0


def calibrate(branches: list[SpravBranch], organizations: list[Organization]) -> Calibration:
    """Run the address fallback against the exactly-matched branches.

    Those branches have a known-correct answer via external_id, so any
    disagreement is a measured false positive rather than a guess about quality.
    """
    by_permalink = {str(o.external_id): o for o in organizations if o.external_id}
    result = Calibration()
    for branch in branches:
        expected = by_permalink.get(branch.permanent_id)
        if expected is None:
            continue
        result.checked += 1
        guess, _ = best_match(branch, organizations)
        if guess is None:
            result.refused += 1
        elif guess.id == expected.id:
            result.correct += 1
        else:
            result.wrong += 1
    return result


def match_branches(branches: list[SpravBranch], organizations: list[Organization]) -> list[BranchMatch]:
    """Match every branch: permalink first, then the address fallback.

    An organization is claimed at most once — once a branch takes it, later
    branches cannot, which stops one popular address from absorbing several.
    """
    by_permalink = {str(o.external_id): o for o in organizations if o.external_id}
    claimed = {o.id for o in by_permalink.values()}
    available = [o for o in organizations if o.id not in claimed]

    matches: list[BranchMatch] = []
    for branch in branches:
        exact = by_permalink.get(branch.permanent_id)
        if exact is not None:
            matches.append(BranchMatch(branch, exact, "external_id", 1.0))
            continue
        guess, confidence = best_match(branch, available)
        if guess is not None:
            available = [o for o in available if o.id != guess.id]
        matches.append(BranchMatch(branch, guess, "address" if guess else None, confidence))
    return matches
