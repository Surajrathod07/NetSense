"""End-to-end browser check of the nine-page console, with an isolated database."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright, expect
from netsense.config import ROOT,load
from scripts.compare import ports,running

with TemporaryDirectory() as tmp, sync_playwright() as pw:
    tcp,web=ports(2)
    config=dict(load(ROOT/"config/config.json"),tcp_port=tcp,peer_port=tcp,web_port=web,database=tmp+"/node.db")
    with running(Path(tmp)/"cfg.json",config):
        browser=pw.chromium.launch(executable_path=os.getenv("NETSENSE_TEST_BROWSER") or None,args=["--no-sandbox"])
        page=browser.new_page()
        errors=[]
        page.on("pageerror",lambda e: errors.append(str(e)))
        url=f"http://127.0.0.1:{web}/"
        def visit(route):
            page.goto(url+route)
            expect(page.locator("#online")).to_contain_text("Online")
        visit("")
        visit("send")
        for i,label in [(0,"CRITICAL"),(1,"NORMAL")]:
            page.locator(".sample").nth(i).click()
            page.get_by_role("button",name="Send message").click()
            expect(page.locator("#receipt")).to_contain_text(label)
            expect(page.locator("#deliveryStatus")).to_have_text("acknowledged")
        visit("monitor")
        page.locator("#label").select_option("CRITICAL")
        expect(page.locator("#stream tbody tr")).to_have_count(1)
        page.locator("#stream button").click()
        expect(page.locator("#fields")).to_contain_text("Local monotonic")
        page.locator("#fix").click()
        expect(page.locator("#correct")).to_contain_text("recorded")
        page.locator("#close").click()
        page.locator("#pause").click()
        page.locator("#query").fill("absent example")
        expect(page.locator("#stream")).to_contain_text("No matching")
        assert "text/csv" in page.request.get(url+"api/export/messages").headers["content-type"]
        visit("traffic-lab")
        page.locator("#compare").click()
        expect(page.locator("#comparison")).to_contain_text("Throughput")
        page.locator("#start").click()
        expect(page.locator("#runstatus")).to_have_text("Finished",timeout=15000)
        visit("analytics")
        expect(page.locator("#evaluation")).to_contain_text("LogisticRegression")
        visit("nodes")
        page.locator("#probe").click()
        expect(page.locator("#probeResult")).to_contain_text("succeeded")
        visit("model")
        page.locator("#threshold").fill(".41")
        page.locator("#apply").click()
        expect(page.locator("#modelresult")).to_contain_text("Applied 0.41")
        visit("architecture")
        page.locator("summary").first.click()
        visit("about")
        page.set_viewport_size({"width":390,"height":844})
        for route in ["","monitor","send","traffic-lab","analytics","nodes","model","architecture","about"]:
            visit(route)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),route
        assert not errors,errors
        browser.close()
        print("PASS: nine routes, mobile layouts, real critical/normal deliveries, feedback, filters, exports, pacing, comparison, threshold and TCP probe.")
