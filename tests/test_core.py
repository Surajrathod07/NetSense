import concurrent.futures
import json
import socket
import struct
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from netsense.agent import Agent
from netsense.api import create_app, CRITICAL, NORMAL
from netsense.classifier import Classifier
from netsense.config import ROOT, load
from netsense.protocol import send_frame, read_frame, validate_frame
from netsense.scheduler import Scheduler
from netsense.storage import Storage
from scripts.compare import ports


class Core(unittest.TestCase):
    def test_classifier(self):
        c = Classifier(ROOT / "artifacts/trained_model.joblib")
        for s, y in [
            (CRITICAL, "CRITICAL"),
            ("Machine 7 failure alert. Conveyor stopped.", "CRITICAL"),
            ("Patient unresponsive. Emergency help required.", "CRITICAL"),
            ("Floodwater rising; evacuate immediately.", "CRITICAL"),
            (NORMAL, "NORMAL"),
        ]:
            self.assertEqual(c.predict(s)["label"], y)
        with self.assertRaises(ValueError):
            c.predict("  ")

    def test_priority_fifo_and_fcfs(self):
        for mode, expected in [("priority", [1, 3, 0, 2]), ("fcfs", [0, 1, 2, 3])]:
            q = Scheduler(mode)
            for i in range(4):
                q.put(dict(id=i, label="CRITICAL" if i % 2 else "NORMAL"))
            time.sleep(0.005)
            rows = [q.take() for _ in expected]
            self.assertEqual([m["id"] for m in rows], expected)
            self.assertTrue(all(m["wait_ms"] > 0 for m in rows))

    def test_concurrent(self):
        s = Scheduler()
        with concurrent.futures.ThreadPoolExecutor(12) as pool:
            list(pool.map(lambda i: s.put(dict(id=i, label="NORMAL")), range(100)))
        self.assertEqual({s.take()["id"] for _ in range(100)}, set(range(100)))

    def test_fragmented_and_adjacent(self):
        class Fragments:
            def __init__(self):
                self.data = bytearray()

            def sendall(self, value):
                self.data.extend(value)

            def recv(self, n):
                out = self.data[: min(n, 2)]
                del self.data[: len(out)]
                return bytes(out)

        f = Fragments()
        for body in [{"a": "नमस्कार"}, {"b": 2}]:
            send_frame(f, body, "key")
        self.assertEqual(read_frame(f, "key"), {"a": "नमस्कार"})
        self.assertEqual(read_frame(f, "key"), {"b": 2})
        self.assertIsNone(read_frame(f))

    def test_bad_frames(self):
        for payload in [b"null", b"{", b'{"body":1}', b'{"body":{},"mac":"wrong"}']:
            a, b = socket.socketpair()
            with a, b:
                a.sendall(struct.pack("!I", len(payload)) + payload)
                with self.assertRaises(ValueError):
                    read_frame(b, "secret")
        for header, body in [(1000000, b""), (15, b"x")]:
            a, b = socket.socketpair()
            with a, b:
                a.sendall(struct.pack("!I", header) + body)
                a.shutdown(socket.SHUT_WR)
                with self.assertRaises(ValueError):
                    read_frame(b)

    def test_storage_retry_clocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Storage(Path(tmp) / "node.db")
            m = dict(
                id=str(uuid.uuid4()),
                sender="a",
                text=NORMAL,
                label="NORMAL",
                domain="factory",
                enqueued=1,
                sent=2,
                wait_ms=10,
            )
            self.assertEqual(db.receive(m, 2.1, True), "received")
            self.assertEqual(db.receive(m, 2.2, True), "duplicate")
            self.assertAlmostEqual(db.messages({})[0]["total_ms"], 110)
            for synced, received in [(False, 3), (True, 1)]:
                m["id"] = str(uuid.uuid4())
                db.receive(m, received, synced)
                self.assertIsNone(db.messages({"id": m["id"]})[0]["latency_ms"])
            self.assertEqual(len(Storage(db.path).messages({})), 3)

    def test_api_and_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = ports(3)
            cfg = dict(
                load(ROOT / "config/config.json"),
                tcp_port=a,
                peer_port=b,
                web_port=c,
                retries=0,
                database=str(Path(tmp) / "db"),
            )
            node = Agent(cfg)
            node.start()
            try:
                client = create_app(node).test_client()
                for bad in [
                    {},
                    {"text": "a", "domain": []},
                    {"text": " ", "domain": "factory"},
                    {"text": "a" * 4097, "domain": "factory"},
                ]:
                    self.assertEqual(
                        client.post("/api/messages/send", json=bad).status_code, 400
                    )
                self.assertEqual(
                    client.post("/api/test/load", json={"count": False}).status_code,
                    400,
                )
                self.assertEqual(client.get("/api/messages?limit=-1").status_code, 400)
                self.assertEqual(client.get("/api/health").status_code, 200)
                self.assertEqual(
                    client.post(
                        "/api/messages/send", json={"text": NORMAL, "domain": "factory"}
                    ).status_code,
                    202,
                )
                for _ in range(80):
                    if node.db.metrics()["outbound"].get("failed"):
                        break
                    time.sleep(0.025)
                self.assertEqual(node.db.metrics()["outbound"]["failed"], 1)
                cfg["peer_port"] = a
                accepted = client.post("/api/test/load", json={"count": 4}).json["data"]
                for _ in range(80):
                    if len(node.db.messages({})) == 4:
                        break
                    time.sleep(0.025)
                self.assertEqual(len(accepted), 4)
                self.assertEqual(
                    len(client.get("/api/messages?label=CRITICAL").json["data"]), 1
                )
                self.assertTrue(client.get("/api/model/status").json["data"]["loaded"])
                self.assertIn(b"Message stream", client.get("/").data)
                self.assertTrue(client.get("/api/activity").json["data"])
            finally:
                node.close()
