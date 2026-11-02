"""Apply a maintainer's explicit source review JSON. No HTTP or fetch operations."""
import argparse
from pathlib import Path
import sys

from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.schemas.recipe_source import SourceReviewInput
from app.services.recipe_sources import write_source_review


MAX_REVIEW_BYTES = 65536


def _read_review_file(parser: argparse.ArgumentParser, path: Path) -> SourceReviewInput:
    try:
        with path.open("rb") as review_file:
            contents = review_file.read(MAX_REVIEW_BYTES + 1)
    except FileNotFoundError:
        parser.error("Review file does not exist.")
    except OSError:
        parser.error("Review file could not be read.")

    if len(contents) > MAX_REVIEW_BYTES:
        parser.error("Review files must be no larger than 64 KiB.")

    try:
        return SourceReviewInput.model_validate_json(contents)
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_context=False)
        if any(error.get("type") == "json_invalid" for error in errors):
            parser.error("Review file is not valid JSON.")

        # Only emit field names from the schema. Never print Pydantic messages or
        # values, since a review can contain private permission documents.
        safe_fields = {
            "expected_revision",
            "canonical_host",
            "publisher_name",
            "reviewed_by",
            "policy",
            "review_status",
            "tier",
            "enabled",
            "allowed_hosts",
            "allowed_redirect_hosts",
            "access_mode",
            "extraction_methods",
            "cuisine_tags",
            "terms_reference",
            "terms_reviewed_at",
            "robots_reference",
            "robots_reviewed_at",
            "license_reference",
            "last_audited_at",
            "review_expires_at",
            "disabled_reason",
        }
        locations = []
        for error in errors[:5]:
            parts = [str(part) if isinstance(part, int) else part for part in error.get("loc", ())]
            safe_parts = [part if isinstance(part, int) or part in safe_fields else "field" for part in parts]
            locations.append(".".join(str(part) for part in safe_parts) or "review")
        suffix = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        parser.error("Review fields are missing or invalid: " + ", ".join(locations) + suffix + ".")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_file", type=Path)
    args = parser.parse_args()
    request = _read_review_file(parser, args.review_file)
    with SessionLocal() as db:
        try:
            result = write_source_review(db, request)
        except HTTPException as exc:
            if exc.status_code == 409:
                parser.error(
                    "Review conflicts with the current revision or a registered host. No changes were applied."
                )
            if exc.status_code == 422:
                parser.error("Review policy or evidence was rejected. No changes were applied.")
            parser.error(f"Review was rejected by the registry (HTTP {exc.status_code}).")
        print(f"Source {result.id}, revision {result.revision}: {result.review_status}")


if __name__ == "__main__":
    main()
