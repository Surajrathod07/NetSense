import os

from netsense.agent import Agent
from netsense.api import create_app
from netsense.config import ROOT, load


def build_app():
    config_path = ROOT / "config" / "config.json"
    cfg = load(config_path)

    if os.getenv("VERCEL") == "1":
        cfg["database"] = "/tmp/netsense.sqlite"
        cfg["web_host"] = "127.0.0.1"
        cfg["listen_host"] = "127.0.0.1"
        cfg["peer_host"] = "127.0.0.1"

    node = Agent(cfg)
    node.start()

    flask_app = create_app(node)
    flask_app.netsense_node = node

    return flask_app


# This line must remain outside any if statement.
app = build_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
    )