"""4-byte big-endian length + authenticated JSON envelope (also used for ACKs)."""

import hashlib
import hmac
import json
import math
import struct
import uuid
from .classifier import validate


def signature(body, secret):
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest() if secret else ""


def send_frame(sock, body, secret="", limit=32768):
    raw = json.dumps(
        {"body": body, "mac": signature(body, secret)}, allow_nan=False
    ).encode()
    if len(raw) > limit:
        raise ValueError("Frame exceeds limit")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def read_exact(sock, n, header=False):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            if header and not buf:
                return None
            raise ValueError("Truncated frame")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(sock, secret="", limit=32768):
    header = read_exact(sock, 4, True)
    if header is None:
        return None
    (n,) = struct.unpack("!I", header)
    if not 0 < n <= limit:
        raise ValueError("Invalid frame length")
    env = json.loads(read_exact(sock, n))
    if not isinstance(env, dict) or not isinstance(env.get("body"), dict):
        raise ValueError("Invalid envelope")
    mac = env.get("mac")
    if (
        not isinstance(mac, str)
        or not mac.isascii()
        or not hmac.compare_digest(mac, signature(env["body"], secret))
    ):
        raise ValueError("Authentication failed")
    return env["body"]


def validate_frame(m):
    for key in (
        "id",
        "sender",
        "text",
        "domain",
        "label",
        "score_kind",
        "model_version",
    ):
        if not isinstance(m.get(key), str) or not m[key].strip():
            raise ValueError("Missing field " + key)
    validate(m["text"], m["domain"])
    if (
        str(uuid.UUID(m["id"])) != m["id"]
        or type(m.get("version")) is not int
        or m["version"] != 1
    ):
        raise ValueError("Unsupported version or identifier")
    if m["label"] not in ("CRITICAL", "NORMAL") or m["score_kind"] not in (
        "margin",
        "probability",
    ):
        raise ValueError("Invalid classification")
    for key in ("enqueued", "sent", "wait_ms", "classification_ms", "score"):
        v = m.get(key)
        if (
            type(v) not in (float, int)
            or not math.isfinite(v)
            or (key != "score" and v < 0)
        ):
            raise ValueError("Invalid number " + key)
    if m["score_kind"] == "probability" and not 0 <= m["score"] <= 1:
        raise ValueError("Invalid probability")
