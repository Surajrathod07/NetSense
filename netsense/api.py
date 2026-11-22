import json
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from .config import ROOT

NORMAL = "Good morning. Today's maintenance meeting is scheduled for 3 PM."
CRITICAL = "EMERGENCY: Fire detected in factory block C. Evacuate immediately."


def create_app(agent):
    app = Flask(
        __name__,
        template_folder=str(ROOT / "dashboard/templates"),
        static_folder=str(ROOT / "dashboard/static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 12000

    def ok(data, status=200):
        return jsonify(data=data), status

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(ValueError)
    def bad_input(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(RuntimeError)
    def busy(e):
        return jsonify(error=str(e)), 503

    @app.get("/classic")
    def dashboard():
        return render_template("index.html", normal=NORMAL, critical=CRITICAL)

    @app.post("/api/messages/send")
    def send():
        value = body()
        return ok(agent.submit(value.get("text"), value.get("domain")), 202)

    @app.post("/api/test/load")
    def batch():
        count = body().get("count", 12)
        if type(count) is not int or not 1 <= count <= 48:
            raise ValueError("Count must be 1–48")
        result = []
        for i in range(count):
            try:
                result.append(
                    agent.submit(CRITICAL if i % 4 == 3 else NORMAL, "factory")
                )
            except RuntimeError as e:
                return jsonify(data=result, error=str(e)), 503
        return ok(result, 202)

    @app.get("/api/messages")
    def messages():
        return ok(agent.db.messages(request.args))

    @app.get("/api/outbound/<message_id>")
    def delivery(message_id):
        with agent.db.connect() as db:
            row = db.execute(
                "SELECT * FROM outbound WHERE id=?", (message_id,)
            ).fetchone()
        if row is None:
            return jsonify(error="Unknown outgoing message"), 404
        return ok(dict(row))

    @app.get("/api/metrics")
    def metrics():
        return ok(agent.db.metrics())

    @app.get("/api/activity")
    def activity():
        return ok(agent.db.activity())

    @app.get("/api/model/status")
    def model_status():
        return ok(dict(loaded=True, **json.loads((ROOT / "ml/model_metadata.json").read_text())))

    @app.get("/api/system/status")
    @app.get("/api/health")
    def status():
        with agent.db.connect() as db:
            db.execute("SELECT 1")
        running = agent.receiver.is_alive() and agent.worker.is_alive()
        return ok(
            dict(
                online=running,
                receiver=agent.receiver.is_alive(),
                sender=agent.worker.is_alive(),
                database="ready",
                model=agent.classifier.bundle["version"],
                queues=agent.scheduler.stats(),
                config={k: v for k, v in agent.cfg.items() if k != "database"},
            ),
            200 if running else 503,
        )

    from .console import install
    install(app, agent)
    return app
