import ipaddress
import logging
import os
import socket
import socketserver
import threading
import time
import uuid

from .classifier import Classifier, validate
from .config import ROOT
from .protocol import send_frame, read_frame, validate_frame
from .scheduler import Scheduler
from .storage import Storage


class Listener(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = False

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, address)

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Connection(socketserver.BaseRequestHandler):
    def handle(self):
        agent = self.server.agent
        cfg = agent.cfg
        ip = self.client_address[0]
        self.request.settimeout(cfg["timeout"])
        agent.db.event("connected", ip)
        try:
            while not agent.stopping.is_set():
                m = read_frame(self.request, agent.secret, cfg["max_frame"])
                if m is None:
                    break
                arrived = time.time()
                validate_frame(m)
                synced = ipaddress.ip_address(ip).is_loopback or cfg["clocks_synced"]
                local = ipaddress.ip_address(ip).is_loopback
                m["demo"] = local and m.get("sender")==cfg["node"] and cfg["tcp_port"]==cfg["peer_port"]
                m["receiver"] = cfg["node"]
                m["measurement"] = "Local monotonic" if local and "sent_ns" in m else ("UTC estimate" if synced else "Unsynchronised")
                elapsed = None
                if local and type(m.get("sent_ns")) is int:
                    elapsed = max(0, (time.monotonic_ns() - m["sent_ns"]) / 1e6)
                status = agent.db.receive(m, arrived, synced, elapsed)
                send_frame(
                    self.request,
                    dict(id=m["id"], status=status),
                    agent.secret,
                    cfg["max_frame"],
                )
        except (ValueError, OSError, OverflowError, RecursionError) as e:
            agent.db.event("rejected / disconnected", str(e)[:200])
        finally:
            agent.db.event("disconnected", ip)


class Agent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.secret = os.getenv("NETSENSE_SECRET", "")
        self.classifier = Classifier(ROOT / "artifacts/trained_model.joblib")
        self.db = Storage(ROOT / cfg["database"])
        self.scheduler = Scheduler(cfg["mode"])
        self.stopping = threading.Event()
        self.listener = Listener((cfg["listen_host"], cfg["tcp_port"]), Connection)
        self.listener.agent = self
        self.listener.slots = threading.BoundedSemaphore(32)
        self.receiver = threading.Thread(
            target=self.listener.serve_forever, name="receiver"
        )
        self.worker = threading.Thread(target=self.work, name="sender")

    def start(self):
        self.receiver.start()
        self.worker.start()
        self.db.event("model loaded", self.classifier.bundle["version"])
        self.db.event("agent started", self.cfg["node"])

    def submit(self, text, domain):
        validate(text, domain)
        message = dict(
            self.classifier.predict(text),
            text=text,
            domain=domain,
            id=str(uuid.uuid4()),
            version=1,
            sender=self.cfg["node"],
            destination=f'{self.cfg["peer_host"]}:{self.cfg["peer_port"]}',
        )
        self.scheduler.put(message, self.db.queued)
        return {
            k: message[k]
            for k in (
                "id",
                "label",
                "score",
                "score_kind",
                "classification_ms",
                "model_version",
            )
        }

    def transmit(self, m):
        cfg = self.cfg
        for attempt in range(cfg["retries"] + 1):
            try:
                with socket.create_connection(
                    (cfg["peer_host"], cfg["peer_port"]), cfg["timeout"]
                ) as conn:
                    m["sent"] = time.time()
                    m["sent_ns"] = time.monotonic_ns()
                    send_frame(conn, m, self.secret, cfg["max_frame"])
                    self.db.event("frame transmitted", m["id"])
                    ack = read_frame(conn, self.secret, cfg["max_frame"])
                    if (
                        not ack
                        or ack.get("id") != m["id"]
                        or ack.get("status") not in ("received", "duplicate")
                    ):
                        raise ValueError("Invalid acknowledgement")
                m["rtt_ms"] = (time.monotonic_ns() - m["sent_ns"]) / 1e6
                self.db.event("transmitted", m["id"])
                return "acknowledged"
            except (ValueError, OSError, RecursionError, OverflowError) as e:
                self.db.event("attempt failed", f"{m['id']} / {attempt+1}: {e}")
                if attempt < cfg["retries"]:
                    time.sleep(0.1 * (attempt + 1))
        self.db.event("delivery unconfirmed", m["id"])
        return "failed"

    def work(self):
        while True:
            m = self.scheduler.take()
            if m is None:
                break
            try:
                self.db.outcome(m, self.transmit(m))
            except Exception:
                logging.exception("Sender failed for %s", m["id"])
                self.db.outcome(m, "failed")
            time.sleep(self.cfg["demo_delay_ms"] / 1000)

    def close(self):
        self.scheduler.close()
        self.worker.join()
        self.stopping.set()
        self.listener.shutdown()
        self.listener.server_close()
        self.receiver.join()
        self.db.event("agent stopped", self.cfg["node"])
