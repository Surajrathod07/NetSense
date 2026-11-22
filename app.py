import os

from netsense.agent import Agent
from netsense.api import create_app
from netsense.config import ROOT, load


def create_vercel_app():
    config_path = ROOT / "config" / "config.json"
    cfg = load(config_path)

    # Vercel functions cannot reliably persist SQLite files.
    # /tmp is writable during one function instance.
    cfg["database"] = "/tmp/netsense.sqlite"
    cfg["web_host"] = "127.0.0.1"
    cfg["listen_host"] = "127.0.0.1"
    cfg["peer_host"] = "127.0.0.1"

    node = Agent(cfg)
    node.start()

    flask_app = create_app(node)

    # Keep the Agent alive for the lifetime of this function instance.
    flask_app.netsense_node = node

    return flask_app


if os.getenv("VERCEL") == "1":
    app = create_vercel_app()
else:
    app = None


if __name__ == "__main__":
    from run import main

    main()