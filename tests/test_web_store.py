from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from compras_crawler.web.store import AppStore, next_occurrence, utcnow

UTC = timezone.utc
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    store = AppStore(tmp_path)
    store.init_schema()
    store.add_city("4205407", "Florianópolis", "SC")
    store.add_city("4202909", "Brusque", "SC")
    return store


def test_queue_claims_are_atomic_and_isolated_by_city(store):
    for city in ("4205407", "4205407", "4202909"):
        store.enqueue(city, {"start_date": "2026-01-01", "end_date": "2026-01-31"}, now=NOW)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(lambda _: store.claim("owner", now=NOW), range(4)))
    active = [r for r in claimed if r]
    assert len(active) == 2
    assert {r["city_id"] for r in active} == {"4205407", "4202909"}
    assert store.claim("owner", now=NOW) is None


def test_user_stop_survives_service_recovery(store):
    run_id = store.enqueue("4205407", {}, now=NOW)
    other_id = store.enqueue("4202909", {}, now=NOW)
    store.begin_service("old")
    first = store.claim("old", now=NOW)
    second = store.claim("old", now=NOW)
    store.request_stop(first["id"])
    store.begin_service("new")
    assert store.run(first["id"])["status"] == "stopped"
    assert store.run(second["id"])["status"] == "queued"
    assert not store.update_run(second["id"], "old", "finished")
    store.resume(first["id"])
    assert store.run(first["id"])["status"] == "queued"


def test_daily_schedule_coalesces_missed_dates(store):
    values = dict(city_id="4205407", name="Rotina", frequency="daily", local_time="02:00",
                  timezone="America/Sao_Paulo", weekday=None, window_days=90)
    store.add_schedule(values, now=datetime(2026, 8, 1, tzinfo=UTC))
    assert store.tick_schedules(NOW) == 1
    assert store.tick_schedules(NOW) == 0
    assert len(store.runs()) == 1
    config = store.runs()[0]["config"]
    assert config["end_date"] == "2026-08-24"
    assert config["start_date"] == "2026-05-27"
    assert store.schedules()[0]["next_due"] == "2026-08-25T05:00:00+00:00"


def test_once_schedule_disables_after_enqueue(store):
    store.add_schedule(dict(city_id="4202909", name="Única", frequency="once", due_at="2026-08-24T11:00:00+00:00",
                            local_time="02:00", timezone="UTC", window_days=30),
                       now=datetime(2026, 8, 1, tzinfo=UTC))
    assert store.tick_schedules(NOW) == 1
    assert store.tick_schedules(NOW) == 0
    assert not store.schedules()[0]["enabled"]
    with pytest.raises(ValueError, match="já executada"):
        store.enable_schedule(store.schedules()[0]["id"], True)


def test_dst_nonexistent_time_is_skipped():
    after = datetime(2026, 3, 8, 5, tzinfo=UTC)
    assert next_occurrence("daily", "02:30", "America/New_York", None, after) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)


def test_weekly_future_occurrence():
    assert next_occurrence("weekly", "09:00", "UTC", 0, NOW) == datetime(2026, 8, 31, 9, tzinfo=UTC)


def test_worker_crashes_are_bounded(store):
    run_id = store.enqueue("4205407", {})
    for _ in range(3):
        assert store.claim("owner", now=utcnow() + timedelta(days=1))["id"] == run_id
        store.recover_worker(run_id, "owner")
    assert store.run(run_id)["status"] == "failed"
    store.resume(run_id)
    assert store.run(run_id)["worker_failures"] == 0


def test_publication_owner_is_checked_in_same_transaction(store):
    run_id = store.enqueue("4205407", {})
    store.begin_service("old")
    store.claim("old")
    assert store.start_projection(run_id, "old")
    store.begin_service("new")
    with pytest.raises(RuntimeError, match="owns publication"):
        store.publish("4205407", "not-published.duckdb", {}, lease=(run_id, "old"))
    assert store.city("4205407")["snapshot"] is None


def test_paths_do_not_accept_traversal(store):
    with pytest.raises(ValueError):
        store.city_dir("../../outside")
