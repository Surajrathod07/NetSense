import argparse
import signal
from netsense.config import load, ROOT
from netsense.agent import Agent
from netsense.api import create_app
from werkzeug.serving import make_server


def main():
    parser = argparse.ArgumentParser(description="Start a bidirectional NetSense node")
    parser.add_argument("--config", default=ROOT / "config/config.json")
    args = parser.parse_args()
    cfg = load(args.config)
    if not (ROOT / "artifacts/trained_model.joblib").exists():
        from ml.train_model import train_model
        train_model()
    node = Agent(cfg)
    app = create_app(node)
    server = make_server(cfg["web_host"], cfg["web_port"], app, threaded=True)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    node.start()
    try:
        print(
            f"NetSense {cfg['node']} listening at http://{cfg['web_host']}:{cfg['web_port']}",
            flush=True,
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        node.close()


if __name__ == "__main__":
    main()
