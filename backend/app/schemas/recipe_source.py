from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from app.schemas.ingredients import StrictSchema
from app.services.source_urls import normalize_host

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ReviewStatus = Literal["candidate", "approved", "suspended", "rejected"]
SourceTier = Literal["filipino_priority", "reviewed_general", "broad_web"]
AccessMode = Literal["search_link_only", "metadata_only", "structured_recipe_fetch", "licensed_full"]


class SourcePolicy(StrictSchema):
    review_status: ReviewStatus = "candidate"
    tier: SourceTier = "filipino_priority"
    enabled: bool = False
    allowed_hosts: list[str] = Field(min_length=1, max_length=20)
    allowed_redirect_hosts: list[str] = Field(default_factory=list, max_length=20)
    access_mode: AccessMode = "search_link_only"
    extraction_methods: list[Literal["json_ld", "api_json", "full_text"]] = Field(default_factory=list, max_length=3)
    cuisine_tags: list[Text] = Field(default_factory=lambda: ["Filipino"], max_length=30)
    terms_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None
    terms_reviewed_at: AwareDatetime | None = None
    robots_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None
    robots_reviewed_at: AwareDatetime | None = None
    license_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None
    last_audited_at: AwareDatetime | None = None
    review_expires_at: AwareDatetime | None = None
    disabled_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None

    @field_validator("allowed_hosts", "allowed_redirect_hosts")
    @classmethod
    def hosts(cls, values):
        normalized = [normalize_host(item) for item in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Host allowlists cannot contain duplicates")
        return normalized

    @model_validator(mode="after")
    def approval_evidence(self):
        if self.review_status != "approved" and self.enabled:
            raise ValueError("Only an approved source may be enabled")
        if self.access_mode in {"search_link_only", "metadata_only"} and self.extraction_methods:
            raise ValueError("Link and metadata approval do not permit recipe extraction")
        if "full_text" in self.extraction_methods and self.access_mode != "licensed_full":
            raise ValueError("Full text requires explicit licensed access")
        if self.review_status == "approved":
            if not all([self.terms_reference, self.terms_reviewed_at, self.last_audited_at, self.review_expires_at]):
                raise ValueError("Approval requires dated terms and audit evidence with expiry")
            if self.terms_reviewed_at > self.last_audited_at:
                raise ValueError("The audit must include the current terms review")
            if self.review_expires_at <= self.last_audited_at:
                raise ValueError("Review expiry must follow the audit")
            if self.access_mode in {"structured_recipe_fetch", "licensed_full"}:
                if not all([self.robots_reference, self.robots_reviewed_at, self.license_reference, self.extraction_methods]):
                    raise ValueError("Fetch requires robots, permission and method evidence")
                if self.robots_reviewed_at > self.last_audited_at:
                    raise ValueError("The audit must include the current robots review")
        for date in (self.terms_reviewed_at, self.robots_reviewed_at, self.last_audited_at):
            if date is not None and date > datetime.now(timezone.utc):
                raise ValueError("A review date cannot be in the future")
        return self


class SourceReviewInput(StrictSchema):
    expected_revision: int | None = Field(default=None, ge=1)
    canonical_host: str
    publisher_name: Text
    reviewed_by: Text
    policy: SourcePolicy

    @field_validator("canonical_host")
    @classmethod
    def host(cls, value):
        return normalize_host(value)

    @model_validator(mode="after")
    def canonical_is_allowed(self):
        if self.canonical_host not in self.policy.allowed_hosts:
            raise ValueError("Canonical host must be explicitly allowed")
        return self


class SourceRead(StrictSchema):
    id: int
    publisher_name: str
    canonical_host: str
    revision: int
    review_status: ReviewStatus
    tier: SourceTier
    access_mode: AccessMode
    currently_approved: bool
    live_fetch_enabled: Literal[False] = False


class SourceReferenceInput(StrictSchema):
    expected_revision: int | None = Field(default=None, ge=1)
    expected_recipe_revision: int = Field(ge=1)
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    author: Text | None = None
    allow_broader_web: bool = False


class SourceReferenceRead(StrictSchema):
    recipe_id: int
    revision: int
    is_active: bool
    canonical_url: str
    author: str | None
    publisher_name: str
    source_label: str
    currently_allowed: bool
    copied_publisher_content: Literal[False] = False
    live_fetch_enabled: Literal[False] = False
    linked_at: datetime
