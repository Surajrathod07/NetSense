import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
import numpy as np


class Storage:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS messages(
                  id TEXT PRIMARY KEY, sender TEXT, text TEXT, domain TEXT, label TEXT,
                  received REAL, wait_ms REAL, latency_ms REAL, total_ms REAL, payload TEXT);
                CREATE INDEX IF NOT EXISTS arrival ON messages(received DESC);
                CREATE TABLE IF NOT EXISTS outbound(id TEXT PRIMARY KEY, label TEXT, status TEXT, wait_ms REAL);
                CREATE TABLE IF NOT EXISTS activity(seq INTEGER PRIMARY KEY, at REAL, event TEXT, detail TEXT);
            """)
            cols = {r[1] for r in db.execute("PRAGMA table_info(outbound)")}
            for name, kind in [("text","TEXT"), ("rtt_ms","REAL")]:
                if name not in cols:
                    db.execute(f"ALTER TABLE outbound ADD COLUMN {name} {kind}")
            db.execute("CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,text TEXT,label TEXT,domain TEXT)")
            db.execute("UPDATE outbound SET status='interrupted'  WHERE status='queued'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=8)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, kind, detail):
        with self.connect() as db:
            db.execute(
                "INSERT INTO activity(at,event,detail) VALUES(?,?,?)",
                (time.time(), kind, detail),
            )

    def queued(self, m):
        with self.connect() as db:
            db.execute(
                "INSERT INTO outbound(id,label,status,text) VALUES(?,?,'queued',?)", (m["id"], m["label"], m["text"])
            )
            db.executemany(
                "INSERT INTO activity(at,event,detail) VALUES(?,?,?)",
                [
                    (time.time(), e, m["label"] + " " + m["id"])
                    for e in ("intercepted", "classified", "queued")
                ],
            )

    def outcome(self, m, status):
        with self.connect() as db:
            db.execute(
                "UPDATE outbound SET status=?,wait_ms=?,rtt_ms=? WHERE id=?",
                (status, m["wait_ms"], m.get("rtt_ms"), m["id"]),
            )

    def receive(self, m, received, synced, elapsed=None):
        latency = (
            (received - m["sent"]) * 1000 if synced and received >= m["sent"] else None
        )
        if elapsed is not None:
            latency = elapsed
        with self.connect() as db:
            added = db.execute(
                "INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    m["id"],
                    m["sender"],
                    m["text"],
                    m["domain"],
                    m["label"],
                    received,
                    m["wait_ms"],
                    latency,
                    None if latency is None else latency + m["wait_ms"],
                    json.dumps(m),
                ),
            ).rowcount
            if not added:
                old = json.loads(
                    db.execute(
                        "SELECT payload FROM messages WHERE id=?", (m["id"],)
                    ).fetchone()[0]
                )
                if any(
                    old[k] != m[k]
                    for k in ("sender", "text", "label", "domain", "enqueued")
                ):
                    raise ValueError("Conflicting message ID")
            db.execute(
                "INSERT INTO activity(at,event,detail) VALUES(?,?,?)",
                (
                    received,
                    "received" if added else "duplicate",
                    m["label"] + " " + m["id"],
                ),
            )
        return "received" if added else "duplicate"

    def messages(self, args):
        clauses, params = [], []
        for key in ("label", "domain", "sender", "id"):
            if args.get(key):
                clauses.append(key + "=?")
                params.append(args[key])
        if args.get("q"):
            clauses.append("instr(lower(text),lower(?))>0")
            params.append(args["q"])
        for key, op in (("since", ">="), ("until", "<=")):
            if args.get(key):
                clauses.append("received" + op + "?")
                params.append(float(args[key]))
        limit = int(args.get("limit", 100))
        offset = int(args.get("offset", 0))
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Invalid page")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM messages"
                + where
                + " ORDER BY received DESC,id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            )
            return [
                dict(
                    json.loads(r["payload"]),
                    received=r["received"],
                    latency_ms=r["latency_ms"],
                    total_ms=r["total_ms"],
                    status="received",
                )
                for r in rows
            ]

    def activity(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM activity ORDER BY seq DESC LIMIT 50")
            ]

    def metrics(self):
        with self.connect() as db:
            counts = dict(
                db.execute("SELECT status,count(*) FROM outbound GROUP BY status")
            )
            result = {}
            for label in ("CRITICAL", "NORMAL"):
                row = db.execute(
                    "SELECT count(*) n,avg(wait_ms) avg_wait,max(wait_ms) max_wait,avg(latency_ms) avg_network,avg(total_ms) avg_total FROM messages WHERE label=?",
                    (label,),
                ).fetchone()
                delays = [
                    r[0]
                    for r in db.execute(
                        "SELECT latency_ms FROM messages WHERE label=? AND latency_ms IS NOT NULL",
                        (label,),
                    )
                ]
                result[label] = dict(
                    row,
                    p95_network=float(np.percentile(delays, 95)) if delays else None,
                )
            minute = int(time.time() // 60)
            bins = dict(
                db.execute(
                    "SELECT CAST(received/60 AS INTEGER),count(*) FROM messages WHERE received>=? GROUP BY 1",
                    ((minute - 14) * 60,),
                )
            )
            mean, avg_wait = db.execute(
                "SELECT avg(latency_ms),avg(wait_ms) FROM messages"
            ).fetchone()
            transmissions = db.execute(
                "SELECT count(*) FROM activity WHERE event='frame transmitted'"
            ).fetchone()[0]
            return dict(
                classes=result,
                outbound=counts,
                transmitted_frames=transmissions,
                avg_wait=avg_wait,
                avg_network=mean,
                minutes=[bins.get(x, 0) for x in range(minute - 14, minute + 1)],
            )
