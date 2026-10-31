from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.product import Product
from app.models.user import User
from app.api.v1.dependencies import get_current_household_id_for_write
from app.core.security import hash_password
from app.schemas.event import ConsumeRequest
from app.services.household_writes import (
    bump_inventory_revision,
    bump_shopping_revision,
    lock_household_write,
)
from app.services.inventory import InventoryService


def _inventory_revision(db, household_id: int) -> int:
    household = db.scalar(
        select(Household)
        .where(Household.id == household_id)
        .execution_options(populate_existing=True)
    )
    return household.inventory_revision


def test_inventory_revision_bump_is_transactional(db, engine, auth_household):
    observer_factory = sessionmaker(bind=engine, expire_on_commit=False)
    household_id = auth_household.id
    initial_revision = auth_household.inventory_revision
    initial_shopping_revision = auth_household.shopping_revision
    auth_household.name = "Staged household name"
    auth_household.inventory_revision = initial_revision + 1
    auth_household.shopping_revision = initial_shopping_revision + 1

    assert bump_inventory_revision(db, household_id) == initial_revision + 2
    assert bump_shopping_revision(db, household_id) == initial_shopping_revision + 2
    assert auth_household.name == "Staged household name"
    with observer_factory() as observer:
        observed = observer.get(Household, household_id)
        assert observed.inventory_revision == initial_revision
        assert observed.shopping_revision == initial_shopping_revision

    db.rollback()
    with observer_factory() as observer:
        observed = observer.get(Household, household_id)
        assert observed.inventory_revision == initial_revision
        assert observed.shopping_revision == initial_shopping_revision

    assert bump_inventory_revision(db, household_id) == initial_revision + 1
    assert bump_shopping_revision(db, household_id) == initial_shopping_revision + 1
    db.commit()
    with observer_factory() as observer:
        observed = observer.get(Household, household_id)
        assert observed.inventory_revision == initial_revision + 1
        assert observed.shopping_revision == initial_shopping_revision + 1


def test_guarded_api_stock_writes_advance_inventory_revision(client, db, auth_household):
    household_id = auth_household.id
    initial_revision = _inventory_revision(db, household_id)

    product = client.post("/api/v1/products/", json={"name": "Guarded rice"})
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]
    assert _inventory_revision(db, household_id) == initial_revision + 1

    batch = client.post(
        "/api/v1/batches/",
        json={"product_id": product_id, "original_quantity": 5},
    )
    assert batch.status_code == 201, batch.text
    assert _inventory_revision(db, household_id) == initial_revision + 2

    consumed = client.post(
        "/api/v1/inventory/consume",
        json={"product_id": product_id, "quantity": 2},
    )
    assert consumed.status_code == 200, consumed.text
    assert _inventory_revision(db, household_id) == initial_revision + 3


def test_competing_stock_consumptions_serialize_without_losing_quantity(
    db, engine, auth_household
):
    household_id = auth_household.id
    product = Product(household_id=household_id, name="Concurrent rice")
    db.add(product)
    db.flush()
    batch = InventoryBatch(
        household_id=household_id,
        product_id=product.id,
        purchased_at=datetime.now(timezone.utc),
        original_quantity=5,
        remaining_quantity=5,
    )
    db.add(batch)
    db.commit()
    product_id = product.id
    batch_id = batch.id

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    start = Barrier(3)

    def consume():
        with session_factory() as session:
            cached_batch = session.scalar(
                select(InventoryBatch).where(InventoryBatch.id == batch_id)
            )
            assert cached_batch.remaining_quantity == 5
            start.wait(timeout=5)
            try:
                result = InventoryService.consume_product_fefo(
                    session,
                    household_id,
                    ConsumeRequest(product_id=product_id, quantity=4),
                )
                return ("consumed", result.total_consumed)
            except ValueError as exc:
                return ("rejected", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(consume) for _ in range(2)]
        start.wait(timeout=5)
        results = [future.result(timeout=10) for future in futures]

    assert sorted(result[0] for result in results) == ["consumed", "rejected"]
    assert sum(result[1] == 4 for result in results if result[0] == "consumed") == 1
    refreshed_batch = db.scalar(
        select(InventoryBatch)
        .where(InventoryBatch.id == batch_id)
        .execution_options(populate_existing=True)
    )
    assert refreshed_batch.remaining_quantity == 1
    assert db.scalar(
        select(func.count(InventoryEvent.id)).where(
            InventoryEvent.batch_id == batch_id,
            InventoryEvent.event_type == EventType.CONSUMED,
        )
    ) == 1
    refreshed_household = db.scalar(
        select(Household)
        .where(Household.id == household_id)
        .execution_options(populate_existing=True)
    )
    assert refreshed_household.inventory_revision == 1


@pytest.mark.parametrize(
    ("revocation", "expected_status"),
    [("membership", 403), ("account", 401)],
)
def test_waiting_write_guard_rechecks_membership_and_account(
    engine, auth_user, auth_household, revocation, expected_status
):
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    household_id = auth_household.id
    actor_id = auth_user.id
    lock_held = Event()
    allow_revoker_commit = Event()
    check_started = Event()
    check_finished = Event()
    checker_pid: list[int] = []

    def revoke_access():
        with session_factory() as session:
            lock_household_write(session, household_id)
            if revocation == "membership":
                membership = session.scalar(
                    select(HouseholdMembership).where(
                        HouseholdMembership.household_id == household_id,
                        HouseholdMembership.user_id == actor_id,
                    )
                )
                session.delete(membership)
            else:
                user = session.scalar(
                    select(User)
                    .where(User.id == actor_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                user.is_active = False
            session.flush()
            lock_held.set()
            if not allow_revoker_commit.wait(timeout=5):
                raise TimeoutError("test did not release the household lock")
            session.commit()

    def check_access():
        with session_factory() as session:
            checker_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
            check_started.set()
            try:
                lock_household_write(session, household_id, actor_id=actor_id)
                return None
            except HTTPException as exc:
                return exc.status_code
            finally:
                check_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        revoke_future = executor.submit(revoke_access)
        assert lock_held.wait(timeout=5)
        check_future = executor.submit(check_access)
        try:
            assert check_started.wait(timeout=5)
            deadline = monotonic() + 5
            waiting_on_household_lock = False
            while monotonic() < deadline:
                with engine.connect() as connection:
                    waiting_on_household_lock = connection.scalar(
                        text(
                            "SELECT EXISTS ("
                            "SELECT 1 FROM pg_stat_activity "
                            "WHERE pid = :pid AND wait_event_type = 'Lock')"
                        ),
                        {"pid": checker_pid[0]},
                    )
                if waiting_on_household_lock:
                    break
                sleep(0.01)
            assert waiting_on_household_lock
            assert not check_finished.is_set()
        finally:
            allow_revoker_commit.set()

        revoke_future.result(timeout=5)
        assert check_future.result(timeout=5) == expected_status


def test_foreign_household_context_does_not_wait_for_its_row_lock(
    db, engine, auth_user, auth_household
):
    actor_id = auth_user.id
    authorized_household_id = auth_household.id
    foreign_user = User(
        email="foreign-household-owner@provision.test",
        hashed_password=hash_password("test-password"),
        is_active=True,
    )
    db.add(foreign_user)
    db.flush()
    foreign_household = Household(
        name="Foreign home",
        slug=f"foreign-home-{foreign_user.id}",
    )
    db.add(foreign_household)
    db.flush()
    db.add(
        HouseholdMembership(
            household_id=foreign_household.id,
            user_id=foreign_user.id,
            role=HouseholdRole.OWNER.value,
            is_default=True,
        )
    )
    db.commit()
    foreign_household_id = foreign_household.id

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    locker = session_factory()
    locker.scalar(
        select(Household.id)
        .where(Household.id == foreign_household_id)
        .with_for_update()
    )

    def request_guard():
        with session_factory() as session:
            try:
                get_current_household_id_for_write(
                    current_user=SimpleNamespace(id=actor_id),
                    db=session,
                    x_household_id=foreign_household_id,
                )
            except HTTPException as exc:
                return exc.status_code
            return 200

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(request_guard)
    try:
        assert future.result(timeout=2) == 403
        with session_factory() as session:
            with pytest.raises(HTTPException) as missing_context:
                get_current_household_id_for_write(
                    current_user=SimpleNamespace(id=actor_id),
                    db=session,
                    x_household_id=foreign_household_id + 1000000,
                )
            assert missing_context.value.status_code == 403
        with session_factory() as session:
            assert get_current_household_id_for_write(
                current_user=SimpleNamespace(id=actor_id),
                db=session,
                x_household_id=authorized_household_id,
            ) == authorized_household_id
    finally:
        locker.rollback()
        locker.close()
        executor.shutdown(wait=True)
