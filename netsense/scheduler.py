from collections import Counter, deque
from threading import Condition
import time


class Scheduler:
    def __init__(self, mode="priority"):
        self.mode = mode
        self.condition = Condition()
        self.queues = {label: deque() for label in ("CRITICAL", "NORMAL")}
        self.counts = Counter()
        self.sequence = 0
        self.closed = False

    def put(self, message, record=lambda m: None):
        with self.condition:
            if self.closed or sum(map(len, self.queues.values())) >= 2048:
                raise RuntimeError("Sender is stopping or queue is full")
            message["enqueued"] = time.time()
            started = time.monotonic()
            record(message)
            self.sequence += 1
            label = message["label"]
            self.queues[label].append((self.sequence, started, message))
            self.counts[label] += 1
            self.condition.notify()

    def take(self):
        with self.condition:
            self.condition.wait_for(lambda: self.closed or any(self.queues.values()))
            available = [q for q in self.queues.values() if q]
            if not available:
                return None
            q = (
                available[0]
                if self.mode == "priority"
                else min(available, key=lambda q: q[0][0])
            )
            _, started, msg = q.popleft()
            msg["wait_ms"] = (time.monotonic() - started) * 1000
            return msg

    def stats(self):
        with self.condition:
            return {
                k: dict(waiting=len(q), queued=self.counts[k], previews=[item[2]["text"] for item in list(q)[:4] if "text" in item[2]])
                for k, q in self.queues.items()
            }

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
