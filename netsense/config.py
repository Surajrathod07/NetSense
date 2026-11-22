from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    base = json.loads((ROOT / "config/config.example.json").read_text())
    values = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(values, dict) or set(values) - set(base):
        raise ValueError("Unknown configuration fields")
    base.update(values)
    for key in ("listen_host", "peer_host", "web_host", "node", "database"):
        if not isinstance(base[key], str) or not 0 < len(base[key].strip()) <= 255:
            raise ValueError(key)
    for key, lo, hi in [
        ("tcp_port", 1, 65535),
        ("peer_port", 1, 65535),
        ("web_port", 1, 65535),
        ("timeout", 1, 30),
        ("retries", 0, 5),
        ("max_frame", 8192, 1048576),
        ("demo_delay_ms", 0, 2000),
    ]:
        if type(base[key]) is not int or not lo <= base[key] <= hi:
            raise ValueError(key)
    if type(base["clocks_synced"]) is not bool or base["mode"] not in (
        "priority",
        "fcfs",
    ):
        raise ValueError("Invalid clock policy or scheduling mode")
    return base
