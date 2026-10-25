from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo
import json
import sqlite3
import uuid

from .locations import validate_city_state

UTC = timezone.utc
ACTIVE = ("running", "stopping", "projecting")


def utcnow() -> datetime:
    return datetime.now(UTC)


def stamp(value: datetime | None = None) -> str:
    value = value or utcnow()
    if value.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(UTC).isoformat()


def next_occurrence(frequency: str, local_time: str, tz: str, weekday: int | None,
                    after: datetime) -> datetime:
    """Find a strictly future wall-clock occurrence; skip nonexistent DST times.

    Ambiguous times execute only once (fold=0). UTC timestamps are persisted so
    restarting the server or changing the host timezone cannot reinterpret them.
    """
    zone = ZoneInfo(tz)
    clock = time.fromisoformat(local_time)
    local = after.astimezone(zone)
    for offset in range(9):
        day = local.date() + timedelta(days=offset)
        if frequency == "weekly" and day.weekday() != weekday:
            continue
        candidate = datetime.combine(day, clock, tzinfo=zone)
        candidate_utc = candidate.astimezone(UTC)
        if candidate_utc.astimezone(zone).replace(tzinfo=None) != candidate.replace(tzinfo=None):
            continue
        if candidate_utc > after:
            return candidate_utc
    raise ValueError("no future schedule occurrence")


class AppStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.path = self.root / "app.sqlite"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
        finally:
            con.close()

    def init_schema(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS cities (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, uf TEXT NOT NULL,
                    created_at TEXT NOT NULL, snapshot TEXT, previous_snapshot TEXT,
                    snapshot_at TEXT, coverage_json TEXT
                );
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES cities(id),
                    name TEXT NOT NULL, frequency TEXT NOT NULL, local_time TEXT NOT NULL,
                    timezone TEXT NOT NULL, weekday INTEGER, window_days INTEGER NOT NULL,
                    next_due TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                    start_date TEXT, end_date TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES cities(id),
                    status TEXT NOT NULL, config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    owner TEXT, schedule_id TEXT REFERENCES schedules(id), scheduled_for TEXT,
                    error TEXT, result_json TEXT, available_at TEXT NOT NULL,
                    worker_failures INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(schedule_id, scheduled_for)
                );
                CREATE INDEX IF NOT EXISTS runs_queue ON runs(status, available_at, created_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT REFERENCES runs(id),
                    created_at TEXT NOT NULL, message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS request_gate (
                    id INTEGER PRIMARY KEY CHECK(id = 1), next_at REAL NOT NULL
                );
                INSERT OR IGNORE INTO request_gate VALUES (1, 0);
                CREATE TABLE IF NOT EXISTS service (
                    id INTEGER PRIMARY KEY CHECK(id = 1), instance TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in con.execute("PRAGMA table_info(runs)")}
            if "worker_failures" not in columns:
                con.execute("ALTER TABLE runs ADD COLUMN worker_failures INTEGER NOT NULL DEFAULT 0")

    def city_dir(self, city_id: str) -> Path:
        # IDs are not filesystem paths, even when called outside the HTTP boundary.
        if len(city_id) != 7 or not city_id.isascii() or not city_id.isdigit():
            raise ValueError("invalid IBGE code")
        return self.root / "cities" / city_id

    def add_city(self, city_id: str, name: str, uf: str) -> dict[str, Any]:
        self.city_dir(city_id)
        validate_city_state(city_id, uf)
        with self.connect() as con:
            existing = con.execute("SELECT name,uf FROM cities WHERE id=?", [city_id]).fetchone()
            if existing and (existing["name"] != name or existing["uf"] != uf):
                raise ValueError("o município já está cadastrado com outro nome ou UF")
            con.execute("INSERT OR IGNORE INTO cities(id,name,uf,created_at) VALUES (?,?,?,?)",
                        [city_id, name, uf, stamp()])
        return self.city(city_id)

    def city(self, city_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT * FROM cities WHERE id = ?", [city_id]).fetchone()
        if row is None:
            raise KeyError("município não cadastrado")
        return dict(row)

    def cities(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM cities ORDER BY name")]

    def enqueue(self, city_id: str, config: dict[str, Any], *, now: datetime | None = None) -> str:
        self.city(city_id)
        run_id = str(uuid.uuid4())
        created = stamp(now)
        with self.connect() as con:
            con.execute("INSERT INTO runs(id,city_id,status,config_json,created_at,available_at) VALUES (?,?,?,?,?,?)",
                        [run_id, city_id, "queued", json.dumps(config), created, created])
        return run_id

    def runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("""SELECT r.*, c.name city_name, c.uf FROM runs r
                JOIN cities c ON c.id = r.city_id ORDER BY r.created_at DESC LIMIT ?""", [limit]).fetchall()
        return [self.decode_run(row) for row in rows]

    @staticmethod
    def decode_run(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["config"] = json.loads(data.pop("config_json"))
        data["result"] = json.loads(data.pop("result_json") or "null")
        data.pop("owner", None)
        return data

    def run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT * FROM runs WHERE id = ?", [run_id]).fetchone()
        if row is None:
            raise KeyError("coleta não encontrada")
        return self.decode_run(row)

    def claim(self, owner: str, *, max_workers: int = 2, now: datetime | None = None) -> dict[str, Any] | None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            active = con.execute("SELECT count(*) FROM runs WHERE status IN ('running','stopping','projecting')").fetchone()[0]
            if active >= max_workers:
                con.execute("COMMIT")
                return None
            row = con.execute("""SELECT * FROM runs r WHERE status = 'queued' AND available_at <= ?
                AND NOT EXISTS (SELECT 1 FROM runs a WHERE a.city_id = r.city_id
                    AND a.status IN ('running','stopping','projecting'))
                ORDER BY created_at, id LIMIT 1""", [stamp(now)]).fetchone()
            if row is None:
                con.execute("COMMIT")
                return None
            con.execute("UPDATE runs SET status='running', owner=?, started_at=?, finished_at=NULL, error=NULL WHERE id=?",
                        [owner, stamp(now), row["id"]])
            con.execute("COMMIT")
        return self.run(row["id"])

    def request_stop(self, run_id: str) -> None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM runs WHERE id=?", [run_id]).fetchone()
            if row is None:
                raise KeyError("coleta não encontrada")
            if row[0] == "queued":
                con.execute("UPDATE runs SET status='stopped', finished_at=? WHERE id=?", [stamp(), run_id])
            elif row[0] == "running":
                con.execute("UPDATE runs SET status='stopping' WHERE id=?", [run_id])
            elif row[0] not in ("stopping", "stopped"):
                raise ValueError("esta coleta não pode ser parada neste estado")
            con.execute("COMMIT")

    def start_projection(self, run_id: str, owner: str) -> bool:
        with self.connect() as con:
            return bool(con.execute("UPDATE runs SET status='projecting' WHERE id=? AND owner=? AND status='running'",
                                    [run_id, owner]).rowcount)

    def resume(self, run_id: str) -> None:
        with self.connect() as con:
            changed = con.execute("""UPDATE runs SET status='queued', owner=NULL, finished_at=NULL,
                error=NULL, worker_failures=0, available_at=? WHERE id=? AND status IN ('stopped','failed','partial','interrupted')""",
                [stamp(), run_id]).rowcount
        if not changed:
            raise ValueError("esta coleta não pode ser retomada neste estado")

    def update_run(self, run_id: str, owner: str, status: str, *, result: Any = None,
                   error: str | None = None, delay: float = 0) -> bool:
        terminal = status not in ACTIVE and status != "queued"
        with self.connect() as con:
            changed = con.execute("""UPDATE runs SET status=?, result_json=?, error=?, finished_at=?, available_at=?
                WHERE id=? AND owner=?""", [status, json.dumps(result) if result is not None else None, error,
                stamp() if terminal else None, stamp(utcnow() + timedelta(seconds=delay)), run_id, owner]).rowcount
        return bool(changed)

    def recover_worker(self, run_id: str, owner: str) -> None:
        with self.connect() as con:
            con.execute("""UPDATE runs SET worker_failures=worker_failures+1,
                status=CASE WHEN worker_failures>=2 THEN 'failed' ELSE 'queued' END,
                error=CASE WHEN worker_failures>=2 THEN 'Worker encerrou inesperadamente três vezes; retome manualmente após revisar.'
                    ELSE 'Worker interrompido; retomada automática.' END, available_at=?,
                finished_at=CASE WHEN worker_failures>=2 THEN ? ELSE NULL END
                WHERE id=? AND owner=? AND status IN ('running','projecting','interrupted')""",
                [stamp(utcnow() + timedelta(seconds=5)), stamp(), run_id, owner])

    def begin_service(self, instance: str) -> None:
        # Caller must own the workspace flock before recovering workers.
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT OR REPLACE INTO service VALUES (1,?)", [instance])
            # A user-requested stop must NOT be automatically resumed after a crash.
            con.execute("UPDATE runs SET status='stopped', owner=NULL, finished_at=? WHERE status='stopping'", [stamp()])
            con.execute("""UPDATE runs SET status='queued', owner=NULL, available_at=?
                WHERE status IN ('running','projecting','interrupted')""", [stamp()])
            con.execute("COMMIT")

    def worker_status(self, run_id: str, owner: str) -> str | None:
        with self.connect() as con:
            row = con.execute("""SELECT r.status FROM runs r JOIN service s ON s.instance=r.owner
                WHERE r.id=? AND r.owner=?""", [run_id, owner]).fetchone()
        return row[0] if row else None

    def event(self, run_id: str, message: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO events(run_id,created_at,message) VALUES (?,?,?)", [run_id, stamp(), message[:4000]])
            con.execute("""DELETE FROM events WHERE run_id=? AND id NOT IN
                (SELECT id FROM events WHERE run_id=? ORDER BY id DESC LIMIT 2000)""", [run_id, run_id])

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self.connect() as con:
            if after == 0:
                query = "SELECT * FROM (SELECT * FROM events WHERE run_id=? ORDER BY id DESC LIMIT 500) ORDER BY id"
                return [dict(row) for row in con.execute(query, [run_id])]
            return [dict(row) for row in con.execute(
                "SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id LIMIT 500", [run_id, after])]

    def add_schedule(self, values: dict[str, Any], *, now: datetime | None = None) -> str:
        now = now or utcnow()
        self.city(values["city_id"])
        if values["frequency"] == "once":
            due = datetime.fromisoformat(values["due_at"].replace("Z", "+00:00"))
            if due <= now:
                raise ValueError("o agendamento pontual deve estar no futuro")
        else:
            due = next_occurrence(values["frequency"], values["local_time"], values["timezone"], values.get("weekday"), now)
        schedule_id = str(uuid.uuid4())
        with self.connect() as con:
            con.execute("""INSERT INTO schedules(id,city_id,name,frequency,local_time,timezone,weekday,
                window_days,next_due,start_date,end_date,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", [
                schedule_id, values["city_id"], values["name"], values["frequency"], values["local_time"],
                values["timezone"], values.get("weekday"), values["window_days"], stamp(due),
                values.get("start_date"), values.get("end_date"), stamp(now),
            ])
        return schedule_id

    def schedules(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [dict(row) for row in con.execute("""SELECT s.*, c.name city_name,
                EXISTS(SELECT 1 FROM runs r WHERE r.schedule_id=s.id) executed FROM schedules s
                JOIN cities c ON c.id=s.city_id ORDER BY created_at DESC""")]

    def enable_schedule(self, schedule_id: str, enabled: bool) -> None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            used = con.execute("""SELECT 1 FROM schedules s WHERE s.id=? AND s.frequency='once'
                AND EXISTS(SELECT 1 FROM runs r WHERE r.schedule_id=s.id)""", [schedule_id]).fetchone()
            if enabled and used:
                raise ValueError("agenda pontual já executada; crie uma nova agenda")
            changed = con.execute("UPDATE schedules SET enabled=? WHERE id=?", [int(enabled), schedule_id]).rowcount
            con.execute("COMMIT")
        if not changed:
            raise KeyError("agenda não encontrada")

    def tick_schedules(self, now: datetime | None = None) -> int:
        now = now or utcnow()
        created = 0
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for row in con.execute("SELECT * FROM schedules WHERE enabled=1 AND next_due<=?", [stamp(now)]).fetchall():
                pending = con.execute("SELECT 1 FROM runs WHERE schedule_id=? AND status IN ('queued','running','stopping','projecting')",
                                      [row["id"]]).fetchone()
                if pending is None:
                    today = now.astimezone(ZoneInfo(row["timezone"])).date()
                    config = dict(start_date=row["start_date"] or (today - timedelta(days=row["window_days"] - 1)).isoformat(),
                                  end_date=row["end_date"] or today.isoformat())
                    inserted = con.execute("""INSERT OR IGNORE INTO runs(id,city_id,status,config_json,created_at,
                        schedule_id,scheduled_for,available_at) VALUES (?,?,'queued',?,?,?,?,?)""", [
                        str(uuid.uuid4()), row["city_id"], json.dumps(config), stamp(now), row["id"], row["next_due"], stamp(now)])
                    created += inserted.rowcount
                if row["frequency"] == "once":
                    con.execute("UPDATE schedules SET enabled=0 WHERE id=?", [row["id"]])
                else:
                    due = next_occurrence(row["frequency"], row["local_time"], row["timezone"], row["weekday"], now)
                    con.execute("UPDATE schedules SET next_due=? WHERE id=?", [stamp(due), row["id"]])
            con.execute("COMMIT")
        return created

    def publish(self, city_id: str, snapshot: str, coverage: dict[str, Any],
                lease: tuple[str, str] | None = None) -> str | None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if lease:
                valid = con.execute("""SELECT 1 FROM runs r JOIN service s ON r.owner=s.instance
                    WHERE r.id=? AND r.owner=? AND r.status='projecting'""", list(lease)).fetchone()
                if valid is None:
                    raise RuntimeError("execution no longer owns publication")
            row = con.execute("SELECT snapshot,previous_snapshot FROM cities WHERE id=?", [city_id]).fetchone()
            if row is None:
                raise KeyError("município não cadastrado")
            con.execute("""UPDATE cities SET previous_snapshot=snapshot, snapshot=?, snapshot_at=?, coverage_json=?
                WHERE id=?""", [snapshot, stamp(), json.dumps(coverage), city_id])
            con.execute("COMMIT")
        return row[1]
