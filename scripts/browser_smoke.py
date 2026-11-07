"""Exercise authenticated Gradio through Chromium with deterministic public-provider fixtures."""

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import bcrypt
import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def fixture_server():
    import app
    from ensembl_uniprot_mcp import runtime
    from ensembl_uniprot_mcp.research import ResearchService

    def respond(req):
        host = req.url.host
        if host == "mygene.info":
            data = {
                "hits": [
                    {
                        "symbol": "TP53",
                        "ensembl": {"gene": "ENSG1"},
                        "uniprot": {"Swiss-Prot": "P04637"},
                    }
                ]
            }
        elif host == "rest.ensembl.org":
            data = {"id": "ENSG1", "assembly_name": "GRCh38"}
        elif host == "rest.uniprot.org":
            data = {"primaryAccession": "P04637", "sequence": {"value": "MEE", "length": 3}}
        elif host == "www.proteinatlas.org":
            data = {"Gene": "TP53", "RNA tissue specific nTPM": {"brain": 0, "kidney": 5}}
        elif host == "api.platform.opentargets.org":
            data = {"data": {"target": None}}
        elif host == "search.clinicalgenome.org":
            return httpx.Response(
                200, text="GENE SYMBOL,DISEASE LABEL,MOI,CLASSIFICATION,ONLINE REPORT\n"
            )
        else:
            data = {"esearchresult": {"idlist": []}}
        return httpx.Response(200, json=data)

    runtime._service = ResearchService(transport=httpx.MockTransport(respond))
    app.main()


def run():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    password = secrets.token_hex(16)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "BIOMCP_USER": "tester",
        "BIOMCP_PORT": str(port),
        "BIOMCP_PASSWORD_HASH": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "GRADIO_ANALYTICS_ENABLED": "False",
    }
    proc = subprocess.Popen([sys.executable, __file__, "--fixture"], env=env, cwd=ROOT)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                if httpx.get(url, timeout=1).status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(0.25)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("BIOMCP_CHROME") or None)
            page = browser.new_page()
            page.set_default_timeout(20000)
            page.goto(url)
            page.locator("input[type=text]").first.fill("tester")
            page.locator("input[type=password]").fill(password)
            page.locator("input[type=password]").press("Enter")
            page.get_by_label("Gene symbol, alias, Ensembl ID, or protein name").fill("TP53")
            page.get_by_role("button", name="Search", exact=True).click()
            page.get_by_role("heading", name="TP53", exact=True).wait_for()
            page.get_by_role("tab", name="Evidence explorer", exact=True).click()
            page.locator(".js-plotly-plot").first.wait_for()
            page.get_by_label("Find a tissue, disease or drug").fill("kidney")
            page.get_by_role("tab", name="What supports the finding?", exact=True).click()
            page.get_by_role("heading", name="kidney", exact=True).wait_for()
            page.get_by_label("Find a tissue, disease or drug").fill("")
            page.get_by_role("tab", name="Sources", exact=True).click()
            page.get_by_role("button", name="Refresh selected section").click()
            page.get_by_role("tab", name="Sequences", exact=True).click()
            page.get_by_role("tab", name="Protein FASTA", exact=True).click()
            file_link = page.locator('a[href*=".fasta"]').first
            file_link.wait_for()
            response = page.request.get(file_link.get_attribute("href"))
            assert response.ok and "MEE" in response.text()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=15)
    print("Authenticated search, explorer, refresh and FASTA download passed.")


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        fixture_server()
    else:
        run()
