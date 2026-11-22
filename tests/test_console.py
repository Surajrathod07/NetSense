import tempfile
import time
import unittest
from pathlib import Path

from netsense.agent import Agent
from netsense.api import create_app
from netsense.config import ROOT, load
from netsense.console import PAGES
from netsense.lab import SAMPLES, simulate
from scripts.compare import ports

class Console(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tcp, web = ports(2)
        self.node = Agent(dict(load(ROOT/"config/config.json"),tcp_port=tcp,peer_port=tcp,web_port=web,database=str(Path(self.tmp.name)/"demo.db")))
        self.node.start()
        self.client = create_app(self.node).test_client()

    def tearDown(self):
        self.node.close()
        self.tmp.cleanup()

    def post(self, route, body):
        res = self.client.post("/api/"+route,json=body)
        self.assertLess(res.status_code,300,res.data)
        return res.json["data"]

    def test_six_examples_and_controls(self):
        for page in PAGES:
            res=self.client.get("/"+page)
            self.assertEqual(res.status_code,200)
            self.assertIn(b'aria-current="page"',res.data)
        for domain,pair in SAMPLES.items():
            for text,label in zip(pair,("CRITICAL","NORMAL")):
                msg=self.post("messages/send",dict(text=text,domain=domain))
                self.assertEqual(msg["label"],label)
        for _ in range(100):
            if self.node.db.metrics()["outbound"].get("acknowledged")==6: break
            time.sleep(.015)
        rows=self.node.db.messages({})
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r["latency_ms"]>=0 and r["measurement"]=="Local monotonic" for r in rows))
        self.assertEqual(len(self.client.get("/api/messages?label=NORMAL").json["data"]),3)
        self.assertIn(rows[0]["id"].encode(),self.client.get("/api/export/messages").data)
        self.assertIn(b"precision",self.client.get("/api/export/evaluation").data)
        self.post("control/feedback",dict(id=rows[0]["id"],label="NORMAL"))
        self.assertEqual(self.post("control/model/threshold",{"threshold":.4})["threshold"],.4)
        self.assertIn("succeeded",self.post("control/peer",{}))
        self.post("control/clear",{})
        self.assertEqual(self.node.db.messages({}),[])

    def test_generator_and_simulation(self):
        opts=dict(count=18,critical=33,interval=1,service=10,mode="priority",domain="mixed")
        result=self.post("control/lab/compare",opts)
        self.assertLess(result["priority"]["CRITICAL mean delay (ms)"],result["fcfs"]["CRITICAL mean delay (ms)"])
        self.post("control/lab/run",opts)
        for _ in range(200):
            if self.node.db.metrics()["outbound"].get("acknowledged")==18: break
            time.sleep(.01)
        self.assertEqual(self.node.db.metrics()["outbound"].get("acknowledged"),18)
        self.post("control/lab/stop",{})
        # An in-flight normal job completes first. The critical arrival then
        # waits 8 ms and receives its own 10 ms of service.
        result=simulate(["NORMAL","NORMAL","CRITICAL"],1,10,True)
        self.assertEqual(result["CRITICAL mean delay (ms)"],18)
        self.assertEqual(result["NORMAL maximum wait (ms)"],19)
