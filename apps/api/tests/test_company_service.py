"""CompanyService unit tests (feature 008): CRUD, delete-detaches-branches, grouping."""

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.company_service import UNASSIGNED_CITY, CompanyService


def _branch(company_id, *, name, city, url):
    return Organization(
        yandex_url=url,
        normalized_url=url,
        preferred_scrape_mode=ScrapeMode.public,
        name=name,
        city=city,
        company_id=company_id,
    )


def test_create_update_delete_and_branch_count(db_session):
    service = CompanyService(db_session)
    company = service.create(CompanyCreate(name="Coffee Co"))
    assert company.id is not None
    assert service.branch_count(company.id) == 0

    updated = service.update(company.id, CompanyUpdate(name="Coffee Co 2", is_active=False))
    assert updated.name == "Coffee Co 2"
    assert updated.is_active is False

    # Attach a branch → count reflects it.
    db_session.add(_branch(company.id, name="Tverskaya", city="Москва", url="https://yandex.ru/maps/org/a/1/"))
    db_session.commit()
    assert service.branch_count(company.id) == 1


def test_short_name_create_update_and_clear(db_session):
    service = CompanyService(db_session)
    company = service.create(CompanyCreate(name="Coffee Company", short_name="  Кофе  "))
    assert company.short_name == "Кофе"  # trimmed

    # Blank short_name still falls back to None on create.
    plain = service.create(CompanyCreate(name="Plain"))
    assert plain.short_name is None

    # Update sets it, and an explicit blank clears it back to None.
    service.update(plain.id, CompanyUpdate(short_name="Кратко"))
    assert service.get(plain.id).short_name == "Кратко"
    service.update(plain.id, CompanyUpdate(short_name=""))
    assert service.get(plain.id).short_name is None

    # Omitting short_name in a name-only update leaves it untouched.
    service.update(company.id, CompanyUpdate(name="Renamed"))
    assert service.get(company.id).short_name == "Кофе"


def test_delete_company_detaches_branches(db_session):
    service = CompanyService(db_session)
    company = service.create(CompanyCreate(name="Coffee Co"))
    branch = _branch(company.id, name="Nevsky", city="СПб", url="https://yandex.ru/maps/org/b/2/")
    db_session.add(branch)
    db_session.commit()
    branch_id = branch.id

    assert service.delete(company.id) is True
    assert service.get(company.id) is None

    # Branch survives, now unassigned.
    surviving = db_session.query(Organization).filter(Organization.id == branch_id).first()
    assert surviving is not None
    assert surviving.company_id is None


def test_list_branches_grouped_by_city(db_session):
    service = CompanyService(db_session)
    company = service.create(CompanyCreate(name="Coffee Co"))
    db_session.add_all([
        _branch(company.id, name="B", city="Москва", url="https://yandex.ru/maps/org/a/1/"),
        _branch(company.id, name="A", city="Москва", url="https://yandex.ru/maps/org/b/2/"),
        _branch(company.id, name="C", city="СПб", url="https://yandex.ru/maps/org/c/3/"),
        _branch(company.id, name="D", city=None, url="https://yandex.ru/maps/org/d/4/"),
    ])
    db_session.commit()

    groups = service.list_branches_grouped_by_city(company.id)
    cities = [city for city, _ in groups]
    # Moscow + SPb alphabetical, unassigned last.
    assert cities[-1] == UNASSIGNED_CITY
    assert set(cities[:-1]) == {"Москва", "СПб"}

    moscow = next(members for city, members in groups if city == "Москва")
    # Two Moscow branches, sorted by name (A before B).
    assert [b.name for b in moscow] == ["A", "B"]
