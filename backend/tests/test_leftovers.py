from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import event as sqlalchemy_event, func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.leftovers import router as leftovers_router
from app.core.database import get_db
from app.core.time import household_today
from app.models.household import Household
from app.models.leftover import Leftover, LeftoverEvent, LeftoverEventType
from app.models.location import StorageLocation
from app.models.recipe import Recipe
from app.models.user import User
from app.schemas.leftover import LeftoverCreate


def _local_client(db, user):
    app = FastAPI()
    app.include_router(leftovers_router, prefix="/leftovers")

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def _create_payload(**overrides):
    payload = {
        "name": "Adobo portions",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "quantity": "2",
        "unit": "g",
    }
    payload.update(overrides)
    return payload


def test_use_by_date_requires_verification_and_preparation_time_must_be_aware():
    base = {
        "name": "Adobo portions",
        "prepared_at": datetime.now(timezone.utc),
        "quantity": "2",
        "unit": "portion",
    }
    with pytest.raises(ValidationError):
        LeftoverCreate(**{**base, "use_by_date": household_today()})
    with pytest.raises(ValidationError):
        LeftoverCreate(**{**base, "prepared_at": datetime.now()})

    verified = LeftoverCreate(
        **{
            **base,
            "use_by_date": household_today(),
            "use_by_date_verified": True,
        }
    )
    assert verified.use_by_date_verified is True


def test_leftover_consumption_and_discard_are_separate_scoped_events(
    db, auth_household, auth_user
):
    with _local_client(db, auth_user) as client:
        created = client.post("/leftovers", json=_create_payload())
        assert created.status_code == 201, created.text
        leftover_id = created.json()["id"]

        consumed = client.post(
            f"/leftovers/{leftover_id}/consume",
            json={"expected_revision": 1, "quantity": "0.5"},
        )
        assert consumed.status_code == 200, consumed.text
        assert consumed.json()["event"]["event_type"] == "CONSUMED"
        assert Decimal(consumed.json()["leftover"]["remaining_quantity"]) == Decimal("1.5")
        assert consumed.json()["leftover"]["revision"] == 2

        discarded = client.post(
            f"/leftovers/{leftover_id}/discard",
            json={"expected_revision": 2, "quantity": "1.5"},
        )
        assert discarded.status_code == 200, discarded.text
        assert discarded.json()["event"]["event_type"] == "DISCARDED"
        assert Decimal(discarded.json()["leftover"]["remaining_quantity"]) == Decimal("0")
        assert discarded.json()["leftover"]["revision"] == 3
        assert discarded.json()["leftover"]["archived_at"] is not None

        active = client.get("/leftovers")
        history = client.get("/leftovers?include_archived=true")

    assert active.status_code == 200 and active.json() == []
    assert history.status_code == 200 and len(history.json()) == 1
    assert [event["event_type"] for event in history.json()[0]["events"]] == [
        "CONSUMED",
        "DISCARDED",
    ]
    events = db.scalars(
        select(LeftoverEvent)
        .where(LeftoverEvent.leftover_id == leftover_id)
        .order_by(LeftoverEvent.id)
    ).all()
    assert [event.event_type for event in events] == [
        LeftoverEventType.CONSUMED.value,
        LeftoverEventType.DISCARDED.value,
    ]
    assert all(event.household_id == auth_household.id for event in events)
    assert _count(db, Leftover) == 1


def test_leftover_get_reads_balance_and_events_from_one_snapshot(
    db, engine, auth_household, auth_user
):
    with _local_client(db, auth_user) as client:
        created = client.post("/leftovers", json=_create_payload(quantity="2"))
        assert created.status_code == 201, created.text
        leftover_id = created.json()["id"]

        parent_reads = 0
        interleaved = False

        def commit_event_after_parent_read(_conn, _cursor, statement, _params, _context, _many):
            nonlocal parent_reads, interleaved
            normalized = statement.casefold()
            if not normalized.lstrip().startswith("select") or "from leftovers" not in normalized:
                return
            parent_reads += 1
            if parent_reads != 2 or interleaved:
                return
            interleaved = True
            with Session(engine, autoflush=False) as writer:
                row = writer.scalar(
                    select(Leftover)
                    .where(Leftover.household_id == auth_household.id, Leftover.id == leftover_id)
                    .with_for_update()
                )
                row.remaining_quantity = Decimal("1")
                row.revision = 2
                writer.add(
                    LeftoverEvent(
                        household_id=auth_household.id,
                        leftover_id=leftover_id,
                        event_type=LeftoverEventType.CONSUMED.value,
                        quantity=Decimal("1"),
                        unit="g",
                        occurred_at=datetime.now(timezone.utc),
                        reason="Concurrent consumption",
                    )
                )
                writer.commit()

        sqlalchemy_event.listen(engine, "after_cursor_execute", commit_event_after_parent_read)
        try:
            response = client.get(f"/leftovers/{leftover_id}")
        finally:
            sqlalchemy_event.remove(engine, "after_cursor_execute", commit_event_after_parent_read)

    assert interleaved is True
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    assert Decimal(response.json()["remaining_quantity"]) == Decimal("2")
    assert response.json()["events"] == []
    db.rollback()
    current = db.scalar(select(Leftover).where(Leftover.id == leftover_id))
    assert current.revision == 2
    assert Decimal(str(current.remaining_quantity)) == Decimal("1")
    assert _count(db, LeftoverEvent) == 1


def test_expired_leftover_cannot_be_consumed_but_can_be_discarded(
    db, auth_user
):
    with _local_client(db, auth_user) as client:
        created = client.post(
            "/leftovers",
            json=_create_payload(
                use_by_date=(household_today() - timedelta(days=1)).isoformat(),
                use_by_date_verified=True,
            ),
        )
        assert created.status_code == 201, created.text
        leftover_id = created.json()["id"]
        consume = client.post(
            f"/leftovers/{leftover_id}/consume",
            json={"expected_revision": 1, "quantity": "1"},
        )
        discard = client.post(
            f"/leftovers/{leftover_id}/discard",
            json={"expected_revision": 1, "quantity": "1"},
        )

    assert consume.status_code == 409
    assert consume.json()["detail"] == "LEFTOVER_EXPIRED"
    assert discard.status_code == 200, discard.text
    assert discard.json()["event"]["event_type"] == "DISCARDED"
    assert _count(db, LeftoverEvent) == 1


def test_leftover_create_rejects_foreign_location_and_recipe_and_list_stays_scoped(
    db, auth_household, auth_user
):
    foreign = Household(name="Other home", slug=f"other-leftover-{auth_user.id}")
    db.add(foreign)
    db.flush()
    location = StorageLocation(household_id=foreign.id, name="Foreign freezer")
    db.add(location)
    foreign_recipe = Recipe(
        household_id=foreign.id,
        title="Foreign recipe",
        cuisine="Filipino",
        content={},
        revision=1,
        is_active=True,
        created_by_user_id=auth_user.id,
    )
    db.add(foreign_recipe)
    db.flush()
    hidden_leftover = Leftover(
        household_id=foreign.id,
        name="Other household leftover",
        prepared_at=datetime.now(timezone.utc),
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        unit="g",
        revision=1,
    )
    db.add(hidden_leftover)
    db.commit()

    with _local_client(db, auth_user) as client:
        foreign_location_response = client.post(
            "/leftovers",
            json=_create_payload(storage_location_id=location.id),
        )
        foreign_recipe_response = client.post(
            "/leftovers",
            json=_create_payload(recipe_id=foreign_recipe.id, recipe_revision=1),
        )
        listed = client.get("/leftovers?include_archived=true")

    assert foreign_location_response.status_code == 404
    assert foreign_recipe_response.status_code == 404
    assert listed.status_code == 200
    assert all(item["household_id"] == auth_household.id for item in listed.json())
    assert all(item["id"] != hidden_leftover.id for item in listed.json())
    assert _count(db, Leftover) == 1


def test_portions_and_quantity_must_reach_zero_together_without_partial_event(
    db, auth_user
):
    with _local_client(db, auth_user) as client:
        created = client.post(
            "/leftovers",
            json=_create_payload(quantity="2", portions="2"),
        )
        assert created.status_code == 201, created.text
        leftover_id = created.json()["id"]
        invalid = client.post(
            f"/leftovers/{leftover_id}/consume",
            json={"expected_revision": 1, "quantity": "2", "portions": "1"},
        )

    assert invalid.status_code == 422
    assert _count(db, LeftoverEvent) == 0
    leftover = db.scalar(select(Leftover).where(Leftover.id == leftover_id))
    assert Decimal(str(leftover.remaining_quantity)) == Decimal("2")
    assert leftover.revision == 1
