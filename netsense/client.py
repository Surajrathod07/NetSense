import json
from typing import Protocol
from urllib.request import Request, urlopen


class MessageAdapter(Protocol):
    def send_message(self, text: str, domain: str) -> dict: ...


class Client:
    def __init__(self, url="http://127.0.0.1:5000"):
        self.url = url.rstrip("/")

    def send_message(self, text, domain):
        request = Request(
            self.url + "/api/messages/send",
            data=json.dumps(dict(text=text, domain=domain)).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=8) as response:
            return json.load(response)["data"]

    def received(self, **filters):
        from urllib.parse import urlencode

        with urlopen(
            self.url + "/api/messages?" + urlencode(filters), timeout=8
        ) as response:
            return json.load(response)["data"]
