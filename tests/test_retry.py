"""Lose the first ACK after commit. The next connection must confirm one delivery."""

import socket
import tempfile
import threading
import unittest
from pathlib import Path
from netsense.agent import Agent
from netsense.api import NORMAL
from netsense.config import load, ROOT
from netsense.protocol import read_frame, send_frame
from scripts.compare import ports
import time


class Retry(unittest.TestCase):
    def test_lost_ack(self):
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as peer:
            a, b, c = ports(3)
            cfg = dict(
                load(ROOT / "config/config.example.json"),
                tcp_port=a,
                peer_port=b,
                web_port=c,
                database=str(Path(tmp) / "node.db"),
                retries=1,
            )
            agent = Agent(cfg)
            peer.bind(("127.0.0.1", b))
            peer.listen()
            peer.settimeout(5)
            results = []

            def receive_twice():
                for attempt in range(2):
                    conn, _ = peer.accept()
                    with conn:
                        m = read_frame(conn, agent.secret)
                        status = agent.db.receive(m, time.time(), True)
                        results.append(status)
                        if attempt:
                            send_frame(
                                conn, dict(id=m["id"], status=status), agent.secret
                            )

            t = threading.Thread(target=receive_twice)
            t.start()
            agent.start()
            try:
                agent.submit(NORMAL, "factory")
                t.join(6)
            finally:
                agent.close()
            self.assertEqual(results, ["received", "duplicate"])
            self.assertEqual(agent.db.metrics()["outbound"], {"acknowledged": 1})
            self.assertEqual(len(agent.db.messages({})), 1)
