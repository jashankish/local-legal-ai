"""Capture README screenshots from a running, seeded instance.

Usage:
    .venv/bin/python scripts/seed_demo.py --backend http://127.0.0.1:8000
    .venv/bin/python scripts/capture_screenshots.py --ui http://127.0.0.1:8501 --api http://127.0.0.1:8000

Requires `pip install playwright && python -m playwright install chromium`.
Writes PNGs to docs/screenshots/.
"""

import argparse
import os
import time

from playwright.sync_api import Page, sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "docs", "screenshots")
WIDTH = 1440


def settle(page: Page, extra: float = 1.5):
    """Wait until Streamlit has finished rerunning and charts have drawn."""
    time.sleep(0.5)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')"
        " || getComputedStyle(document.querySelector('[data-testid=\"stStatusWidget\"]')).visibility === 'hidden'"
        " || document.querySelector('[data-testid=\"stStatusWidget\"]').innerText.trim() === ''",
        timeout=120_000,
    )
    page.wait_for_load_state("networkidle")
    time.sleep(extra)


def shot(page: Page, name: str, height: int = 900):
    page.set_viewport_size({"width": WIDTH, "height": height})
    settle(page, 1.0)
    path = os.path.join(OUT, f"{name}.png")
    page.screenshot(path=path)
    print("saved", os.path.relpath(path, ROOT))


def navigate(page: Page, label: str):
    page.locator('[data-testid="stSidebar"]').get_by_role("combobox").first.click()
    page.get_by_role("option").filter(has_text=label).first.click()
    settle(page)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", default="http://127.0.0.1:8501")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "LegalDemo-2025"),
                        help="admin password (seed_demo.py sets LegalDemo-2025 by default)")
    args = parser.parse_args()
    os.makedirs(OUT, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # First sign-in with a temporary password (seeded user "new.hire"); not completed,
        # so the capture can be repeated.
        first = browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=1)
        first.goto(args.ui)
        first.get_by_role("textbox", name="Username").wait_for(timeout=60_000)
        first.get_by_role("textbox", name="Username").fill("new.hire")
        first.get_by_role("textbox", name="Password").fill("Welcome-temp-1")
        first.get_by_role("button", name="Sign in").click()
        first.get_by_text("Choose a new password").wait_for(timeout=60_000)
        shot(first, "13_first_sign_in_password_change", 900)
        first.close()

        page = browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=1)

        # Sign-in
        page.goto(args.ui)
        page.get_by_label("Username").wait_for(timeout=60_000)
        settle(page)
        page.get_by_role("textbox", name="Username").fill("admin")
        page.get_by_role("textbox", name="Password").fill(args.password)
        shot(page, "01_login", 820)
        page.get_by_role("button", name="Sign in").click()
        page.get_by_text("Recently added").wait_for(timeout=60_000)
        shot(page, "02_dashboard", 1000)

        # Upload
        navigate(page, "Upload Documents")
        page.locator('input[type="file"]').set_input_files(
            os.path.join(ROOT, "samples", "employment_agreement.txt"))
        shot(page, "03_upload", 900)

        # Ask a question
        navigate(page, "Ask Documents")
        page.get_by_label("Your question").fill("Can the tenant terminate the lease early, and what does it cost?")
        page.get_by_role("button", name="Submit Query").click()
        page.get_by_text("Key Terms in the Cited Passages").wait_for(timeout=120_000)
        shot(page, "04_ask_answer", 1500)

        # Document library
        navigate(page, "Document Library")
        shot(page, "05_document_library", 1100)

        # Analytics tabs
        navigate(page, "Analytics Dashboard")
        for index, (tab, name, height) in enumerate([
            ("Usage Analytics", "06_analytics_usage", 1300),
            ("Performance", "07_analytics_performance", 1250),
            ("Similarity Analysis", "08_analytics_similarity", 950),
            ("User Activity", "09_analytics_activity", 1350),
        ]):
            page.get_by_role("tab", name=tab).click()
            settle(page, 2.0)
            shot(page, name, height)

        # Audit log with integrity check
        navigate(page, "Audit Log")
        page.get_by_role("button", name="Verify chain").click()
        page.get_by_text("Intact").wait_for(timeout=60_000)
        shot(page, "10_audit_log", 1250)

        # User administration
        navigate(page, "Users")
        page.get_by_text("Add a user").wait_for(timeout=60_000)
        shot(page, "12_user_admin", 1150)

        # Integrations (inbox + notifications)
        navigate(page, "Integrations")
        page.get_by_text("Watched inbox folder").wait_for(timeout=60_000)
        shot(page, "14_integrations", 1150)

        # Interactive API documentation
        page.goto(f"{args.api}/docs")
        page.get_by_text("Local Legal AI").first.wait_for(timeout=60_000)
        time.sleep(1.5)
        page.set_viewport_size({"width": WIDTH, "height": 1100})
        page.screenshot(path=os.path.join(OUT, "11_api_docs.png"))
        print("saved docs/screenshots/11_api_docs.png")

        browser.close()


if __name__ == "__main__":
    main()
