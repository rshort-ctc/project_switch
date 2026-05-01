import pytest
from sqlalchemy.orm import Session

from app.models.enums import SiteStatus
from app.services.exceptions import EntityNotFoundError
from app.services.sites import SiteService


def test_site_can_be_created_and_read(session: Session) -> None:
    service = SiteService(session)

    site = service.create_site(
        site_name="Test Facility Alpha",
        facility_type="test_facility",
        address_line_1="100 Test Example Road",
        address_line_2="Suite T",
        city="Test City",
        state="TS",
        zip_code="00000",
        county="Test County",
        timezone="America/Chicago",
        status=SiteStatus.ACTIVE,
        primary_contact_name="Test Contact",
        primary_contact_email="contact@example.test",
        primary_contact_phone="555-0100",
        notes="Synthetic test fixture only.",
    )

    loaded = service.get_site(site.id)

    assert loaded.id == site.id
    assert loaded.site_name == "Test Facility Alpha"
    assert loaded.facility_type == "test_facility"
    assert loaded.address_line_1 == "100 Test Example Road"
    assert loaded.address_line_2 == "Suite T"
    assert loaded.city == "Test City"
    assert loaded.state == "TS"
    assert loaded.zip_code == "00000"
    assert loaded.county == "Test County"
    assert loaded.timezone == "America/Chicago"
    assert loaded.status == SiteStatus.ACTIVE
    assert loaded.primary_contact_name == "Test Contact"
    assert loaded.primary_contact_email == "contact@example.test"
    assert loaded.primary_contact_phone == "555-0100"
    assert loaded.notes == "Synthetic test fixture only."
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


def test_site_defaults_to_unknown_status(session: Session) -> None:
    site = SiteService(session).create_site(site_name="Test Facility Unknown")

    assert site.facility_type == "unknown"
    assert site.status == SiteStatus.UNKNOWN


def test_sites_can_be_listed_and_filtered_by_status(session: Session) -> None:
    service = SiteService(session)
    active = service.create_site(
        site_name="Test Facility Active",
        status=SiteStatus.ACTIVE,
    )
    service.create_site(
        site_name="Test Facility Pending",
        status=SiteStatus.PENDING,
    )

    all_sites = service.list_sites()
    active_sites = service.list_sites(status=SiteStatus.ACTIVE)

    assert [site.site_name for site in all_sites] == [
        "Test Facility Active",
        "Test Facility Pending",
    ]
    assert [site.id for site in active_sites] == [active.id]


def test_site_can_be_updated(session: Session) -> None:
    service = SiteService(session)
    site = service.create_site(site_name="Test Facility Before")

    updated = service.update_site(
        site.id,
        site_name="Test Facility After",
        city="Updated Test City",
        status="inactive",
        notes=None,
    )

    assert updated.site_name == "Test Facility After"
    assert updated.city == "Updated Test City"
    assert updated.status == SiteStatus.INACTIVE
    assert updated.notes is None


def test_site_update_rejects_unknown_fields(session: Session) -> None:
    service = SiteService(session)
    site = service.create_site(site_name="Test Facility Guarded")

    with pytest.raises(ValueError, match="unsupported site update field"):
        service.update_site(site.id, circuit_id="not-in-phase-2a")


def test_get_missing_site_raises(session: Session) -> None:
    with pytest.raises(EntityNotFoundError):
        SiteService(session).get_site("missing-site-id")
