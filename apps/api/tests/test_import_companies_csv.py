from app.models.organization import Organization


def test_organization_persists_with_null_urls(db_session):
    org = Organization(name="Сочи-04", city="Адлер", yandex_url=None, normalized_url=None)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    assert org.id is not None
    assert org.yandex_url is None
    assert org.normalized_url is None
