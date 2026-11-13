"""Isolated Chromium E2E smoke test of Caregiver Dashboard 2.0.

Uses local Flask and a temporary SQLite database — does not touch production
patient information, WhatsApp contacts or the Render PostgreSQL service.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory(prefix="mindcare-caregiver-e2e-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(scratch.name) / "caregiver-e2e.db")
os.environ["SECRET_KEY"] = "isolated-browser-qa-only-not-production"
os.environ["SECURE_COOKIES"] = "0"
os.environ["FLASK_DEBUG"] = "0"

from app import app, db  # noqa:E402
from playwright.sync_api import sync_playwright  # noqa:E402
from werkzeug.serving import make_server  # noqa:E402

app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
with app.app_context():
    db.drop_all()
    db.create_all()
server = make_server("127.0.0.1", 0, app, threaded=True)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = "http://127.0.0.1:" + str(server.socket.getsockname()[1])
results = []


def verify(condition, message):
    if not condition:
        raise AssertionError(message)
    results.append(message)


def register(page, role, name, email):
    page.goto(url + "/register")
    page.locator('input[name="name"]').fill(name)
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="password"]').fill("safe-e2e-only-test-password-1234")
    page.locator(f'input[name="role"][value="{role}"]').check()
    page.locator('button[type="submit"]').click()
    page.wait_for_url("**/dashboard")


def overflow_check(page, width):
    metrics = page.evaluate("""() => ({
      content:document.documentElement.scrollWidth,
      viewport:window.innerWidth,
      offenders: [...document.querySelectorAll('body *')]
        .map(el => {const r=el.getBoundingClientRect();
          return {tag:el.tagName,cls:typeof el.className==='string'?el.className.slice(0,80):'',
            left:Math.round(r.left),right:Math.round(r.right)};})
        .filter(x=>x.right>window.innerWidth+4 || x.left < -5).slice(0,12)
    })""")
    verify(metrics["content"] <= metrics["viewport"] + 3,
           f"Caregiver dashboard has no horizontal overflow at {width}px: {metrics}")


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        patient_context = browser.new_context(viewport={"width": 1280, "height": 800},
                                              reduced_motion="reduce")
        caregiver_context = browser.new_context(viewport={"width": 1280, "height": 800},
                                                reduced_motion="reduce")
        patient = patient_context.new_page()
        caregiver = caregiver_context.new_page()
        patient.set_default_timeout(12000)
        caregiver.set_default_timeout(12000)
        exceptions = []
        caregiver.on("pageerror", lambda error: exceptions.append(str(error)))
        register(patient, "patient", "Patient Leela", "qa-leela-caregiver@example.org")
        invite = patient.locator("#invite-code").inner_text().strip()
        verify(len(invite) == 8, "Patient can share approved connection code")

        patient.locator('input[type="radio"][name="feeling"][value="need_help"]').check()
        patient.locator('textarea[name="note"]').fill("Please call me when you can.")
        patient.locator('.wellbeing-form button[type="submit"]').click()
        patient.wait_for_url("**/dashboard*")
        verify(patient.locator(".support-help-box").count() == 1,
               "Patient receives explicit contact guidance, no false alert")

        patient.goto(url + "/reminders")
        form = patient.locator(".add-panel form")
        form.locator('input[name="title"]').fill("Breakfast medicine")
        form.locator('select[name="category"]').select_option("medicine")
        form.locator('input[name="scheduled_time"]').fill("00:00")
        form.locator('button[type="submit"]').click()
        patient.wait_for_selector(".reminder-row")

        register(caregiver, "caregiver", "Caregiver Maya", "qa-maya-caregiver@example.org")
        verify(caregiver.locator(".caregiver-v2").count() == 1,
               "Caregiver 2.0 overview loads")
        verify(caregiver.locator(".caregiver-patient-card").count() == 0,
               "No private patient data appears before approval")
        caregiver.locator('#caregiver-invite-code').fill(invite)
        caregiver.get_by_role("button", name="Request access").click()
        caregiver.wait_for_url("**/dashboard")
        verify(caregiver.locator(".caregiver-patient-card").count() == 0,
               "Pending caregiver cannot view patient check-ins")

        patient.goto(url + "/dashboard")
        patient.locator('.pending-requests form[action*="/approve/"] button').click()
        patient.wait_for_url("**/dashboard")
        caregiver.reload()
        card = caregiver.locator(".caregiver-patient-card")
        verify(card.count() == 1 and "Patient Leela" in card.inner_text(),
               "Approved caregiver sees one patient card")
        verify("Please call me when you can." in caregiver.locator(".caregiver-support-list").inner_text(),
               "Support queue shows voluntary Need Support message")
        verify(card.locator(".caregiver-overdue-note").count() == 1,
               "Overdue reminder status appears with safe self-report wording")

        caregiver.locator('[data-care-filter="support"]').click()
        verify(card.is_visible(), "Needs-follow-up filter works")
        caregiver.locator("#caregiver-patient-search").fill("someone else")
        verify(card.is_hidden() and caregiver.locator("#caregiver-no-results").is_visible(),
               "Patient name search hides unmatched records")
        caregiver.locator("#caregiver-patient-search").fill("Leela")
        verify(card.is_visible(), "Patient name search restores matching record")
        caregiver.locator('[data-care-filter="all"]').click()
        caregiver.locator("#caregiver-patient-search").fill("")

        for width,height in [(320,780),(375,812),(768,1024),(1280,800)]:
            caregiver.set_viewport_size({"width":width,"height":height})
            caregiver.wait_for_timeout(150)
            overflow_check(caregiver, width)
            bounds = card.locator('a[href^="/caregiver/patient/"]').bounding_box()
            verify(bounds and bounds["height"] >= 40, f"Patient detail control remains tappable at {width}px")
        caregiver.set_viewport_size({"width":1280,"height":800})

        detail_url = card.locator('a[href^="/caregiver/patient/"]').first.get_attribute("href")
        caregiver.goto(url + detail_url)
        verify(caregiver.locator(".caregiver-wellbeing-entry").count() >= 1,
               "Patient detail includes wellbeing timeline")
        verify("Please call me when you can." in caregiver.locator("#wellbeing").inner_text(),
               "Support note accessible only after approval")
        caregiver.locator("#wellbeing form button").click()
        caregiver.wait_for_url("**/caregiver/patient/**")
        verify(caregiver.locator(".caregiver-reviewed-label").count() == 1,
               "Review action is explicit and visible")
        caregiver.goto(url + "/dashboard")
        verify(caregiver.locator(".caregiver-support-item").count() == 0,
               "Reviewed support entry leaves outstanding queue")

        patient.goto(url + "/dashboard")
        patient.locator('input[type="radio"][name="feeling"][value="need_help"]').check()
        patient.locator('textarea[name="note"]').fill("Updated support request")
        patient.locator('.wellbeing-form button[type="submit"]').click()
        patient.wait_for_url("**/dashboard*")
        caregiver.reload()
        verify(caregiver.locator(".caregiver-support-item").count() == 1,
               "Updated patient request reopens caregiver review")

        patient.goto(url + "/dashboard")
        patient.once("dialog", lambda dialog: dialog.accept())
        patient.locator('.pending-requests form[action*="/revoke/"] button').click()
        patient.wait_for_url("**/dashboard")
        caregiver.reload()
        verify(caregiver.locator(".caregiver-patient-card").count() == 0,
               "Revoking access removes patient from caregiver dashboard")
        verify(caregiver.goto(url + detail_url).status == 403,
               "Revoking access blocks previously available patient detail")
        verify(not exceptions, "Caregiver UI has no unhandled browser exceptions: " + str(exceptions[:3]))
        print(json.dumps({"status":"passed","checks":len(results),"details":results},ensure_ascii=False))
        browser.close()
finally:
    server.shutdown()
    server.server_close()
    scratch.cleanup()
