"""Optional browser acceptance test. Install Playwright and its Chromium browser first."""

import os
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright, expect
from netsense.config import load, ROOT
from scripts.compare import running, ports

with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
    a, b, x, y = ports(4)
    base = load(ROOT / "config/config.example.json")
    rx = dict(
        base,
        node="demo-rx",
        tcp_port=b,
        peer_port=a,
        web_port=y,
        database=tmp + "/rx.sqlite",
    )
    tx = dict(
        base,
        node="demo-tx",
        tcp_port=a,
        peer_port=b,
        web_port=x,
        database=tmp + "/tx.sqlite",
    )
    with running(Path(tmp) / "rx.json", rx), running(Path(tmp) / "tx.json", tx):
        browser = p.chromium.launch(
            executable_path=os.getenv("NETSENSE_TEST_BROWSER") or None,
            args=os.getenv("NETSENSE_BROWSER_ARGS", "").split(),
        )
        context = browser.new_context(viewport=dict(width=1360, height=900))
        page = context.new_page()
        receiver = context.new_page()
        errors = []
        for tab, port in [(page, x), (receiver, y)]:
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.goto(f"http://127.0.0.1:{port}/classic")
            expect(tab.locator("#connection")).to_contain_text("Online")
        for kind, label in [("Routine", "NORMAL"), ("Emergency", "CRITICAL")]:
            page.get_by_role("button", name=kind + " sample").click()
            page.get_by_role("button", name="Send →").click()
            expect(page.locator("#feedback")).to_contain_text("Queued " + label)
        expect(receiver.locator("#total")).to_have_text("2")
        receiver.locator("[name=label]").select_option("CRITICAL")
        expect(receiver.locator("#rows tr")).to_have_count(1)
        receiver.locator("#rows button").first.click()
        expect(receiver.locator("dialog")).to_be_visible()
        expect(receiver.locator("#fields")).to_contain_text("demo-tx")
        receiver.locator("#close").click()
        page.get_by_role("button", name="Queue 12 mixed messages").click()
        expect(receiver.locator("#total")).to_have_text("14", timeout=12000)
        receiver.set_viewport_size(dict(width=390, height=844))
        assert receiver.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        print(
            "PASS: two agents, both samples, receiver counters and filters, message details, batch, mobile width, zero JavaScript errors."
        )
        browser.close()
