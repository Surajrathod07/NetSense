"""Controlled arrival schedules replayed by both non-preemptive policies."""
import random
from collections import deque
from threading import Event, Lock, Thread
import numpy as np

SAMPLES = {
    "hospital": ("Emergency: patient in bed 4, heart rate critical.", "Good morning, shift handover at 9 AM."),
    "disaster": ("Fire reported in block C, evacuate immediately.", "Please send the weekly supply report."),
    "factory": ("Machine 7 failure alert, conveyor stopped.", "Routine temperature log: 36.5 C."),
}

def integer(options, name, low, high):
    value = options.get(name)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}.")
    return value

def simulate(labels, interval, service, priority):
    queues = [deque(), deque()]
    index = clock = 0
    delays = {"CRITICAL": [], "NORMAL": []}
    while index < len(labels) or any(queues):
        if not any(queues):
            clock = max(clock, index * interval)
        while index < len(labels) and index * interval <= clock:
            queues[int(priority and labels[index] == "NORMAL")].append(index)
            index += 1
        job = (queues[0] or queues[1]).popleft()
        clock += service
        delays[labels[job]].append(clock - job * interval)
    result = {"Throughput (msg/s)": len(labels)*1000/clock}
    for label, values in delays.items():
        result[label+" mean delay (ms)"] = float(np.mean(values)) if values else None
        result[label+" p95 delay (ms)"] = float(np.percentile(values,95)) if values else None
    result["NORMAL maximum wait (ms)"] = max(delays["NORMAL"])-service if delays["NORMAL"] else None
    return result

class Lab:
    def __init__(self, agent):
        self.agent = agent
        self.lock = Lock()
        self.stop = Event()
        self.thread = None
        self.result = {}
        self.status = "Idle"

    def run(self, opts, compare=False):
        count = integer(opts,"count",1,200)
        pct = integer(opts,"critical",0,100)
        interval = integer(opts,"interval",0,2000)
        service = integer(opts,"service",1,1000)
        domain = opts.get("domain")
        mode = opts.get("mode")
        if domain not in [*SAMPLES,"mixed"] or mode not in ["priority","fcfs"]:
            raise ValueError("Invalid traffic settings")
        rng = random.Random(42)
        kinds = [0]*round(count*pct/100)
        kinds += [1]*(count-len(kinds))
        rng.shuffle(kinds)
        workload = []
        for kind in kinds:
            d = rng.choice(list(SAMPLES)) if domain=="mixed" else domain
            workload.append((SAMPLES[d][kind],d))
        if compare:
            labels = [self.agent.classifier.predict(t)["label"] for t,d in workload]
            self.result = {p:simulate(labels, interval, service, p=="priority") for p in ["fcfs","priority"]}
            return self.result
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("A traffic run is already active")
            self.stop.clear()
            self.status = "Generating"
            def generate():
                old = self.agent.scheduler.mode, self.agent.cfg["demo_delay_ms"]
                self.agent.scheduler.mode, self.agent.cfg["demo_delay_ms"] = mode, service
                try:
                    for text, domain in workload:
                        if self.stop.is_set() or self.agent.stopping.is_set(): break
                        self.agent.submit(text,domain)
                        self.stop.wait(interval/1000)
                    self.status = "Draining queue"
                    while any(v["waiting"] for v in self.agent.scheduler.stats().values()):
                        if self.agent.stopping.wait(.05): break
                    self.status = "Finished"
                except Exception as exc:
                    self.status = str(exc)
                finally:
                    self.agent.scheduler.mode,self.agent.cfg["demo_delay_ms"] = old
            self.thread = Thread(target=generate,daemon=True)
            self.thread.start()
        return {"status":self.status}
