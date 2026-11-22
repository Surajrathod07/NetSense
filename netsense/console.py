import csv
import io
import ipaddress
import json
import socket
import time
from threading import Lock
from urllib.parse import urlparse
from flask import Response, abort, jsonify, render_template, request
from ml.train_model import evaluate, train_model
from .classifier import Classifier
from .config import ROOT
from .lab import Lab, SAMPLES, integer

PAGES = {"":"Overview","monitor":"Live monitoring","send":"Send message","traffic-lab":"Traffic simulator","analytics":"Analytics","nodes":"Network nodes","model":"ML model","architecture":"Architecture","about":"About project"}

def install(app, agent):
    cfg = agent.cfg
    lab = Lab(agent)
    model_file = ROOT/"ml/model_metadata.json"
    model_lock = Lock()
    try:
        demo = ipaddress.ip_address(cfg["peer_host"]).is_loopback
    except ValueError:
        demo = cfg["peer_host"]=="localhost"
    demo = demo and cfg["peer_port"]==cfg["tcp_port"] and cfg["listen_host"] in ("localhost","127.0.0.1","::1")
    def view(page=""):
        if page not in PAGES: abort(404)
        return render_template("console.html", page=page, pages=PAGES, samples=SAMPLES)
    app.add_url_rule("/", "overview", view)
    app.add_url_rule("/<page>", "pages", view)

    @app.before_request
    def local_controls():
        if request.method=="POST":
            if request.headers.get("Origin") and urlparse(request.headers["Origin"]).netloc != request.host:
                abort(403)
            if request.path.startswith("/api/control/") and (not ipaddress.ip_address(request.remote_addr).is_loopback or request.host.split(":")[0] not in ("localhost","127.0.0.1")):
                abort(403)

    @app.get("/api/console")
    def console():
        with agent.db.connect() as db:
            history=[dict(r) for r in db.execute("SELECT * FROM outbound ORDER BY rowid DESC LIMIT 15")]
            last=dict(db.execute("SELECT event,max(at) FROM activity GROUP BY event"))
            sent=db.execute("SELECT count(*) FROM outbound WHERE status='acknowledged'").fetchone()[0]
            errors=db.execute("SELECT count(*) FROM activity WHERE event='attempt failed'").fetchone()[0]
        return jsonify(data=dict(demo=demo,history=history,last=last,sent=sent,errors=errors,run=lab.status,comparison=lab.result))
    @app.post("/api/control/lab/<action>")
    def traffic(action):
        opts=request.get_json()
        if not isinstance(opts,dict): raise ValueError("Expected settings")
        if action=="stop":
            lab.stop.set()
            return jsonify(data=True)
        if action not in ("run","compare"): abort(404)
        return jsonify(data=lab.run(opts,action=="compare"))
    @app.get("/api/export/<kind>")
    def export(kind):
        out=io.StringIO()
        writer=csv.writer(out)
        with agent.db.connect() as db:
            if kind=="messages":
                cur=db.execute("SELECT id,text,label,sender,domain,received,wait_ms,latency_ms,total_ms FROM messages ORDER BY received DESC")
                writer.writerow([col[0] for col in cur.description])
                for row in cur:
                    writer.writerow(["'"+v if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")) else v for v in row])
            elif kind=="evaluation":
                writer.writerow(["metric","value"])
                writer.writerows(json.loads(model_file.read_text())["test"].items())
            else: abort(404)
        return Response(out.getvalue(),mimetype="text/csv",headers={"Content-Disposition":f"attachment; filename=netsense-{kind}.csv"})
    @app.post("/api/control/clear")
    def clear():
        if not demo: abort(403)
        with agent.db.connect() as db:
            # Limit the deletion to records explicitly stamped as loopback demo.
            db.execute("""DELETE FROM messages WHERE json_extract(payload,'$.demo')=1""")
        return jsonify(data=True)
    @app.post("/api/control/peer")
    def peer():
        with socket.create_connection((cfg["peer_host"],cfg["peer_port"]),timeout=cfg["timeout"]):
            pass
        return jsonify(data="TCP connection succeeded")
    @app.errorhandler(OSError)
    def os_error(exc):
        return jsonify(error=str(exc)),503
    @app.post("/api/control/feedback")
    def feedback():
        body=request.get_json()
        rows=agent.db.messages({"id":body.get("id","?")})
        label=body.get("label")
        if len(rows)!=1 or label not in ("NORMAL","CRITICAL"): raise ValueError("Choose a received message and valid correction")
        m=rows[0]
        with agent.db.connect() as db:
            db.execute("INSERT OR REPLACE INTO feedback VALUES(?,?,?,?)",(m["id"],m["text"],label,m["domain"]))
        return jsonify(data="Correction recorded for the next training run.")
    @app.post("/api/control/model/<action>")
    def model(action):
        with model_lock:
            if action=="retrain":
                with agent.db.connect() as db:
                    feedback=[dict(r) for r in db.execute("SELECT * FROM feedback ORDER BY rowid")]
                report=train_model(feedback=feedback)
                agent.classifier=Classifier(ROOT/"artifacts/trained_model.joblib")
            elif action=="threshold":
                t=request.get_json().get("threshold")
                if type(t) not in (int,float) or not 0<t<1: raise ValueError("Threshold must be between 0 and 1")
                report=json.loads(model_file.read_text())
                if report["score_kind"]!="probability": raise ValueError("Requires a probability model")
                import numpy as np
                result=evaluate(report["validation_labels"],np.array(report["validation_scores"]),t)
                agent.classifier.bundle["threshold"]=t
                return jsonify(data=dict(threshold=t,validation=result))
            else: abort(404)
        return jsonify(data=report)
    @app.get("/api/settings")
    def settings():
        return jsonify(data=dict(threshold=agent.classifier.bundle["threshold"],mode=agent.scheduler.mode))
    @app.get("/api/config/download")
    def download_config():
        draft = dict(cfg)
        if request.args:
            name=request.args.get("node","").strip()
            if not 1<=len(name)<=80: raise ValueError("Invalid node name")
            draft["node"]=name
            for field in ("listen_host","peer_host"):
                ip=ipaddress.IPv4Address(request.args.get(field))
                if ip.is_multicast or ip.is_unspecified: raise ValueError("Enter a unicast interface address")
                draft[field]=str(ip)
            draft["peer_port"]=integer({"port":int(request.args.get("peer_port","0"))},"port",1,65535)
        return Response(json.dumps(draft,indent=2),mimetype="application/json",headers={"Content-Disposition":"attachment; filename=config.json"})

    @app.get("/api/events")
    def events():
        def changes():
            cursor = 0
            with agent.db.connect() as db:
                cursor=db.execute("SELECT coalesce(max(seq),0) FROM activity").fetchone()[0]
            yield ": ready\n\n"
            while not agent.stopping.wait(.25):
                with agent.db.connect() as db:
                    rows=db.execute("SELECT seq,event,detail FROM activity WHERE seq>? ORDER BY seq LIMIT 128",(cursor,)).fetchall()
                if rows:
                    cursor=rows[-1]["seq"]
                    yield "data: "+json.dumps([dict(r) for r in rows])+"\n\n"
                else:
                    yield ": heartbeat\n\n"
        return Response(changes(),mimetype="text/event-stream",headers={"Cache-Control":"no-cache"})
