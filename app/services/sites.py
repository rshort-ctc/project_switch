from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories import SiteRepository
from app.models.entities import Site
from app.models.enums import SiteStatus
from app.services.exceptions import EntityNotFoundError

SITE_UPDATE_FIELDS = {
    "site_name",
    "facility_type",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "zip_code",
    "county",
    "timezone",
    "status",
    "primary_contact_name",
    "primary_contact_email",
    "primary_contact_phone",
    "notes",
}


class SiteService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sites = SiteRepository(session)

    def create_site(
        self,
        *,
        site_name: str,
        facility_type: str = "unknown",
        address_line_1: str | None = None,
        address_line_2: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        county: str | None = None,
        timezone: str | None = None,
        status: SiteStatus = SiteStatus.UNKNOWN,
        primary_contact_name: str | None = None,
        primary_contact_email: str | None = None,
        primary_contact_phone: str | None = None,
        notes: str | None = None,
    ) -> Site:
        site = self.sites.create(
            site_name=site_name,
            facility_type=facility_type,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            state=state,
            zip_code=zip_code,
            county=county,
            timezone=timezone,
            status=status,
            primary_contact_name=primary_contact_name,
            primary_contact_email=primary_contact_email,
            primary_contact_phone=primary_contact_phone,
            notes=notes,
        )
        self.session.flush()
        return site

    def get_site(self, site_id: str) -> Site:
        site = self.sites.get(site_id)
        if site is None:
            raise EntityNotFoundError(f"site not found: {site_id}")
        return site

    def list_sites(self, *, status: SiteStatus | None = None) -> Sequence[Site]:
        return self.sites.list(status=status)

    def update_site(self, site_id: str, **updates: Any) -> Site:
        unknown_fields = set(updates) - SITE_UPDATE_FIELDS
        if unknown_fields:
            fields = ", ".join(sorted(unknown_fields))
            raise ValueError(f"unsupported site update field(s): {fields}")

        site = self.get_site(site_id)
        for field, value in updates.items():
            next_value = SiteStatus(value) if field == "status" and value is not None else value
            setattr(site, field, next_value)
        self.session.flush()
        return site
