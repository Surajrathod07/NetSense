"""Two independent agent processes per mode, identical workload and service pacing."""

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from netsense.config import ROOT, load
from netsense.api import CRITICAL, NORMAL
from netsense.client import Client


def ports(n):
    with ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket()) for _ in range(n)]
        for s in sockets:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in sockets]


def get(port, path):
    with urlopen(f"http://127.0.0.1:{port}/api/{path}", timeout=3) as r:
        return json.load(r)["data"]


@contextmanager
def running(path, cfg):
    path.write_text(json.dumps(cfg))
    with path.with_suffix(".log").open("a") as logfile:
        proc = subprocess.Popen(
            [sys.executable, "run.py", "--config", str(path)],
            cwd=ROOT,
            stdout=logfile,
            stderr=logfile,
        )
        try:
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError(path.with_suffix(".log").read_text())
                try:
                    if get(cfg["web_port"], "health")["online"]:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise TimeoutError("Node startup")
            yield
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def workload(mode, n=32):
    a, b, x, y = ports(4)
    cfg = load(ROOT / "config/config.example.json")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        rx = dict(
            cfg,
            node="receiver",
            tcp_port=b,
            peer_port=a,
            web_port=y,
            database=str(d / "rx.sqlite"),
            mode=mode,
        )
        tx = dict(
            cfg,
            node="sender",
            tcp_port=a,
            peer_port=b,
            web_port=x,
            database=str(d / "tx.sqlite"),
            mode=mode,
            demo_delay_ms=25,
        )
        with running(d / "rx.json", rx):
            with running(d / "tx.json", tx):
                client = Client(f"http://127.0.0.1:{x}")
                accepted = [
                    client.send_message(CRITICAL if i % 4 == 3 else NORMAL, "factory")
                    for i in range(n)
                ]
                for _ in range(200):
                    if get(x, "metrics")["outbound"].get("acknowledged", 0) == n:
                        break
                    time.sleep(0.05)
                rows = get(y, "messages")
                assert len(rows) == n and {m["id"] for m in rows} == {
                    m["id"] for m in accepted
                }
                assert all(
                    m["sender"] == "sender"
                    and m["text"] == (CRITICAL if m["label"] == "CRITICAL" else NORMAL)
                    for m in rows
                )
                metrics = get(y, "metrics")
                sender_metrics = get(x, "metrics")
                for key in ("outbound", "transmitted_frames"):
                    metrics[key] = sender_metrics[key]
                assert metrics["transmitted_frames"] == n and metrics["outbound"] == {"acknowledged": n}
                order = [m["label"][0] for m in reversed(rows)]
        with running(d / "rx.json", rx):
            assert len(get(y, "messages")) == n
        return dict(mode=mode, delivery_order="".join(order), **metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = [workload(mode) for mode in ("fcfs", "priority")]
    out = json.dumps(results, indent=2)
    if args.output:
        args.output.write_text(out)
    print(out)
