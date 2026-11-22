"""Create two peer configurations without overwriting earlier files."""

import argparse
import ipaddress
import json
from netsense.config import ROOT, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", default="127.0.0.1", type=ipaddress.IPv4Address)
    parser.add_argument("--b", default="127.0.0.1", type=ipaddress.IPv4Address)
    args = parser.parse_args()
    for name, local, peer, port, remote, web in [
        ("A", args.a, args.b, 7201, 7202, 5001),
        ("B", args.b, args.a, 7202, 7201, 5002),
    ]:
        path = ROOT / f"config/node-{name}.json"
        cfg = dict(
            load(ROOT / "config/config.example.json"),
            node=f"node-{name}",
            listen_host=str(local),
            peer_host=str(peer),
            tcp_port=port,
            peer_port=remote,
            web_port=web,
            database=f"runtime/node-{name}.sqlite",
            demo_delay_ms=80,
        )
        if path.exists():
            print(f"Already exists: {path}. Edit it manually to change addresses.")
        else:
            path.write_text(json.dumps(cfg, indent=2))
            print(path)


if __name__ == "__main__":
    main()
