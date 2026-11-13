"""Headless Chromium walkthrough for a local, disposable MindCare patient account.

Run: pip install -r requirements.txt playwright
     python -m playwright install chromium
     python tests/browser_smoke.py

This script starts Flask on loopback with a fresh temporary SQLite database.
It does not modify the production Render database or contact a real recipient.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

tempdir = tempfile.TemporaryDirectory(prefix="mindcare-browser-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tempdir.name) / "e2e.db")
os.environ["SECRET_KEY"] = "qa-only-never-production-strong-secret"
os.environ["SECURE_COOKIES"] = "0"
os.environ["FLASK_DEBUG"] = "0"

from app import app, db  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)

with app.app_context():
    db.drop_all()
    db.create_all()

server = make_server("127.0.0.1", 0, app, threaded=True)
port = server.socket.getsockname()[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{port}"
results: list[str] = []

def verify(condition, message: str):
    if not condition:
        raise AssertionError(message)
    results.append(message)


def no_horizontal_scroll(page, width):
    metrics = page.evaluate("""() => ({
       content: document.documentElement.scrollWidth,
       viewport: window.innerWidth,
       body: document.body.scrollWidth
    })""")
    verify(metrics["content"] <= metrics["viewport"] + 3,
           f"No horizontal overflow at {width}px (measured {metrics})")


def click_confirmation(page, locator):
    page.once("dialog", lambda dialog: dialog.accept())
    locator.click()


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 860},
                                  reduced_motion="reduce", device_scale_factor=1)
        page = ctx.new_page()
        page.set_default_timeout(13000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/register")
        page.locator('input[name="name"]').fill("Patient Browser QA")
        page.locator('input[name="email"]').fill("browser-patient-qa@example.org")
        page.locator('input[name="password"]').fill("QA-only-test-password-1234")
        page.get_by_role("button", name=re.compile("Create my space")).click()
        page.wait_for_url("**/dashboard")
        verify(page.locator(".patient-mode-shortcut").count() == 1, "Full dashboard offers Simple View")
        verify(page.get_by_text("Your activity", exact=True).count() == 1, "Full dashboard loads activity")

        page.locator(".patient-mode-shortcut button").click()
        page.wait_for_selector(".simple-dashboard")
        verify(page.locator(".simple-action-card").count() == 4, "Simple View has four action cards")
        verify(page.locator('.simple-bottom-actions a[href="tel:112"]').count() == 1,
               "Simplified view retains emergency 112 dialer")
        for width, height in [(320, 780), (375, 812), (768, 1024), (1280, 900)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(200)
            no_horizontal_scroll(page, width)
            visible = page.locator(".simple-action-card .button").first
            box = visible.bounding_box()
            verify(box is not None and box["height"] >= 44,
                   f"Primary action remains a large touch target at {width}px")
        page.set_viewport_size({"width": 1280, "height": 860})
        page.locator(".simple-bottom-actions form button").click()
        page.wait_for_selector(".patient-mode-shortcut")

        page.goto(base + "/settings")
        page.locator('select[name="language"]').select_option("hi")
        page.locator('input[name="simplified_mode"]').check()
        page.locator('.settings-form button[type="submit"]').click()
        page.wait_for_url("**/settings")
        page.goto(base + "/dashboard")
        verify(page.locator(".simple-dashboard").count() == 1, "Simple View setting persists")
        verify("मेरी याद दिलाने वाली बातें" in page.locator("body").inner_text(),
               "Hindi patient labels are rendered")

        page.goto(base + "/settings")
        page.locator('select[name="language"]').select_option("kn")
        page.locator('.settings-form button[type="submit"]').click()
        page.wait_for_url("**/settings")
        page.goto(base + "/dashboard")
        verify("ನನ್ನ ಮುಂದಿನ ಜ್ಞಾಪನೆ" in page.locator("body").inner_text(),
               "Kannada patient labels are rendered")

        page.goto(base + "/settings")
        page.locator('select[name="language"]').select_option("en")
        page.locator('input[name="simplified_mode"]').uncheck()
        page.locator('.settings-form button[type="submit"]').click()
        page.wait_for_url("**/settings")
        page.goto(base + "/reminders")
        verify(page.locator("#reminder-notify-button").count() == 1,
               "Reminders exposes explicit browser-notification opt-in")
        form = page.locator(".add-panel form")
        form.locator('input[name="title"]').fill("QA breakfast practice")
        form.locator('select[name="category"]').select_option("meal")
        form.locator('input[name="scheduled_time"]').fill("09:15")
        form.locator('button[type="submit"]').click()
        page.wait_for_selector(".reminder-row")
        verify("QA breakfast practice" in page.locator(".reminder-row").inner_text(),
               "Reminder can be created")
        page.locator(".reminder-row .reminder-edit-details summary").click()
        page.locator('.reminder-row .reminder-edit-form input[name="title"]').fill("QA breakfast updated")
        page.locator('.reminder-row .reminder-edit-form input[name="scheduled_time"]').fill("09:20")
        page.locator('.reminder-row .reminder-edit-form button[type="submit"]').click()
        page.wait_for_selector(".reminder-row")
        verify("QA breakfast updated" in page.locator(".reminder-row").inner_text(),
               "Reminder can be edited")
        click_confirmation(page, page.locator(".reminder-row .delete-link").first)
        page.wait_for_url("**/reminders*")
        verify("QA breakfast updated" not in page.locator("body").inner_text(),
               "Test reminder can be removed")

        page.goto(base + "/help")
        verify(page.locator(".whatsapp-howto").count() == 1, "WhatsApp guide remains visible")
        verify(page.locator('a[href="tel:112"]').count() >= 1, "112 dialer remains visible")
        verify(page.locator(".guest-voice-contact").count() == 0, "Removed guest links remain absent")
        contact = page.locator(".contact-add-form")
        contact.locator('input[name="name"]').fill("QA family helper")
        contact.locator('input[name="relation"]').fill("Friend")
        contact.locator('input[name="phone"]').fill("0000000000")
        contact.locator('button[type="submit"]').click()
        page.wait_for_selector(".contact-edit-details")
        verify(page.locator('a.whatsapp-open-button[href^="https://wa.me/"]').count() == 1,
               "Saved contact retains WhatsApp chat link")
        page.locator(".contact-edit-details summary").click()
        edit = page.locator(".contact-edit-form")
        edit.locator('input[name="name"]').fill("QA family edited")
        edit.locator('button[type="submit"]').click()
        page.wait_for_selector(".contact-edit-details")
        verify("QA family edited" in page.locator(".contact-row").inner_text(),
               "Trusted contact can be edited")
        page.goto(base + "/dashboard")
        page.locator('input[name="feeling"][value="need_help"]').check()
        page.locator('.wellbeing-form button[type="submit"]').click()
        page.wait_for_url("**/dashboard*")
        verify(page.locator(".support-help-box").count() == 1,
               "Need support displays manual contact actions")
        verify(page.locator(".support-help-box a.whatsapp-open-button").count() == 1,
               "Need support offers a WhatsApp contact action")

        page.goto(base + "/games/cards")
        verify(page.locator("#begin-game").count() == 1, "Memory games remain playable")
        page.locator("#begin-game").click()
        verify(page.locator(".memory-card").count() >= 6, "Memory game loads interactive cards")
        verify(len(errors) == 0, "No unhandled browser JavaScript exceptions: " + repr(errors[:3]))

        # Moderate network conditions, in a browser where CDP supports emulation.
        try:
            cdp = ctx.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": 180,
                "downloadThroughput": 90000,
                "uploadThroughput": 45000
            })
            page.goto(base + "/dashboard", wait_until="domcontentloaded", timeout=30000)
            verify(page.locator(".patient-mode-shortcut").count() == 1,
                   "Dashboard renders under simulated slow connection")
        except Exception as exc:
            results.append("Slow connection simulation unsupported: " + str(exc)[:160])
        print(json.dumps({"status": "passed", "checks": len(results), "details": results}, ensure_ascii=False))
        browser.close()
finally:
    server.shutdown()
    server.server_close()
    tempdir.cleanup()
