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
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
       body: document.body.scrollWidth,
       overflowing: [...document.querySelectorAll('*')].map(el => {
         const rect=el.getBoundingClientRect();
         return {tag:el.tagName,className:typeof el.className==='string'?el.className.slice(0,90):'',
                 right:Math.round(rect.right),width:Math.round(rect.width)};
       }).filter(row=>row.right>window.innerWidth+4).sort((a,b)=>b.right-a.right).slice(0,8)
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
        # Dark, original public landing page: real Chromium tests at mobile/tablet/desktop.
        page.goto(base + "/")
        verify(page.locator(".mc-world-hero").count() == 1,
               "MindCare's immersive public hero renders")
        verify(page.locator(".mc-world-nav").count() == 1,
               "Public landing has exactly one sticky section navigation")
        verify(page.locator(".site-header").count() == 0,
               "Public page does not duplicate the authenticated header")
        verify(page.locator(".site-footer").count() == 0,
               "Public page has its own complete footer")
        verify(page.locator(".mc-gallery-card").count() == 6,
               "Two rows of six original feature illustrations render")
        verify(page.locator('.mc-hero-enter[href="/register"]').count() == 1,
               "Hero CTA opens real existing account registration")
        verify(page.locator('.mc-hero-signin[href="/login"]').count() == 1,
               "Existing account login remains available")
        page.wait_for_function(
            "() => document.querySelector('.mc-hero-art').complete && document.querySelector('.mc-hero-art').naturalWidth > 0"
        )
        verify(page.locator('.mc-hero-art').count() == 1,
               "Original immersive world artwork loads correctly")

        page.locator("#mc-tab-routine").click()
        verify(page.locator("#mc-panel-routine").is_visible() and
               page.locator("#mc-panel-memory").is_hidden(),
               "Capability tabs swap visible descriptions")
        verify(page.locator("#mc-tab-routine").get_attribute("aria-selected") == "true",
               "Active tab exposes accessible selection state")
        page.locator("#mc-tab-routine").focus()
        page.keyboard.press("ArrowRight")
        verify(page.locator("#mc-tab-together").get_attribute("aria-selected") == "true",
               "Keyboard arrows navigate capability tabs")
        page.keyboard.press("Home")
        verify(page.locator("#mc-tab-memory").get_attribute("aria-selected") == "true",
               "Home key returns to first capability")

        page.locator('[data-mc-slide="1"]').click()
        verify(page.locator("#mc-product-caregiver").is_visible() and
               page.locator("#mc-product-patient").is_hidden(),
               "Carousel switches to simulated caregiver screen")
        page.locator('[data-mc-slide="0"]').click()
        verify(page.locator("#mc-product-patient").is_visible(),
               "Carousel switches back to simulated patient screen")

        for width, height in [(320, 780), (375, 812), (768, 1024), (1280, 900)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(100)
            no_horizontal_scroll(page, width)
            verify(page.locator(".mc-hero-enter").is_visible() and
                   page.locator(".mc-world-nav-links").is_visible(),
                   f"CTA and section links remain visible at {width}px")
            verify(page.locator("#mc-capabilities-heading").count() == 1,
                   f"Capabilities heading remains present at {width}px")
        page.set_viewport_size({"width": 1280, "height": 860})
        page.locator('.mc-world-nav-links a[href="#capabilities"]').click()
        page.wait_for_timeout(300)
        verify(page.url.endswith("#capabilities"), "Sticky nav scrolls to real section anchor")
        sticky_top = page.locator(".mc-world-nav").evaluate(
            "(element) => Math.round(element.getBoundingClientRect().top)"
        )
        verify(abs(sticky_top) < 4,
               "Chapter navigation stays pinned when scrolling long landing page")
        verify(page.locator("#privacy-note").count() == 1 and
               page.locator("#terms-note").count() == 1,
               "Footer privacy and terms anchors lead to visible notices")

        page.goto(base + "/register")
        verify(page.locator(".auth-v2").count() == 1, "Professional registration page renders")
        verify(page.locator("#auth-title").inner_text().strip() == "YOU MATTER.", 
               "MindCare account heading uses the new YOU MATTER message")
        verify(page.locator(".auth-v2-form-panel").evaluate(
            "(el) => getComputedStyle(el).order") == "0",
            "Form panel is ordered first for the premium editorial layout")
        verify(page.locator(".auth-v2-story").evaluate(
            "(el) => getComputedStyle(el).order") == "1",
            "Original MindCare illustration follows the form")
        verify(page.locator(".auth-v2-story .auth-story-main p").count() == 1,
               "MindCare artwork includes a concise care-focused caption")

        glow = page.locator(".auth-v2-form-panel").evaluate("""(el) => ({
            before: getComputedStyle(el, '::before').backgroundImage,
            animation: getComputedStyle(el, '::before').animationName,
            pointerEvents: getComputedStyle(el, '::before').pointerEvents,
            after: getComputedStyle(el, '::after').backgroundImage
        })""")
        verify("radial-gradient" in glow["before"] and "radial-gradient" in glow["after"],
               "Original CSS blue bloom decorates both auth layouts")
        verify(glow["pointerEvents"] == "none",
               "Animated glow cannot intercept login or registration interactions")
        verify(glow["animation"] == "none",
               "Reduced-motion preference stops the atmospheric animation")

        expanded = page.locator(".auth-v2").evaluate("""(el) => ({
            stageWidth: el.getBoundingClientRect().width,
            glowWidth: getComputedStyle(el, '::before').width,
            background: getComputedStyle(el, '::before').backgroundImage,
            motion: getComputedStyle(el, '::before').animationName,
            pointerEvents: getComputedStyle(el, '::before').pointerEvents
        })""")
        verify(float(expanded["glowWidth"].replace("px","")) >=
               .74 * expanded["stageWidth"],
               "Blue aura covers at least 75 percent of the desktop auth stage")
        verify("radial-gradient" in expanded["background"] and
               expanded["pointerEvents"] == "none",
               "Bright decorative bloom cannot block auth inputs")
        verify(expanded["motion"] == "none",
               "Expanded bloom respects reduced motion")
        page.emulate_media(reduced_motion="no-preference")
        animated_aura = page.locator(".auth-v2").evaluate("""(el) => ({
            name: getComputedStyle(el, '::before').animationName,
            duration: getComputedStyle(el, '::before').animationDuration,
            pointerEvents: getComputedStyle(el, '::before').pointerEvents
        })""")
        verify(animated_aura["name"] == "mindcare-aura-expand" and
               animated_aura["duration"] == "22s",
               "Blue aura expands continuously over a slow 22-second cycle")
        verify(animated_aura["pointerEvents"] == "none",
               "Expanding blue animation cannot block the login form")
        page.emulate_media(reduced_motion="reduce")

        web_corner = page.locator(".auth-v2-story").evaluate("""(el) => ({
            background: getComputedStyle(el, '::before').backgroundImage,
            pointerEvents: getComputedStyle(el, '::before').pointerEvents
        })""")
        verify("data:image/svg+xml" in web_corner["background"] and
               web_corner["pointerEvents"] == "none",
               "Decorative corner web is present and cannot block forms")



        verify(page.locator('link[href*="auth-world.css"]').count() == 1,
               "Real registration screen loads the matching dark visual theme")
        verify(page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(10, 10, 10)",
               "Real registration page has near-black design background")
        verify("mindcare-world.svg" in page.locator(".auth-v2-story").evaluate(
            "(el) => getComputedStyle(el).backgroundImage"),
            "Real login and registration story uses original illustrated MindCare artwork")
        verify(page.locator(".auth-method-tabs").count() == 1, "Email and phone sign-in tabs visible")
        for width, height in [(320, 780), (375, 812), (768, 1024), (1280, 900)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(100)
            no_horizontal_scroll(page, width)
            verify(page.locator(".auth-v2-email-form").is_visible(),
                   f"Email registration available at {width}px")
        page.set_viewport_size({"width": 1280, "height": 860})
        verify(page.locator(".auth-v2-form-panel").bounding_box()["x"] <
               page.locator(".auth-v2-story").bounding_box()["x"],
               "Desktop auth form appears to the left of the illustration")
        page.locator('[data-auth-tab="phone"]').click()
        verify(page.locator(".auth-phone-not-ready").is_visible(),
               "SMS option explains required provider setup instead of fake sign-in")
        page.locator("[data-auth-return-email]").click()
        verify(page.locator(".auth-v2-email-form").is_visible(), "Returning to email sign-in works")
        page.locator(".auth-password-visibility").click()
        verify(page.locator('input[name="password"]').get_attribute("type") == "text",
               "Show password toggles visibility")
        page.locator(".auth-password-visibility").click()
        verify(page.locator('input[name="password"]').get_attribute("type") == "password",
               "Hide password toggles back")
        page.locator('input[name="name"]').fill("Patient Browser QA")
        page.locator('input[name="email"]').fill("browser-patient-qa@example.org")
        page.locator('input[name="password"]').fill("QA-only-test-password-1234")
        page.get_by_role("button", name=re.compile("Create my account")).click()
        page.wait_for_url("**/dashboard")
        verify(page.locator(".patient-mode-shortcut").count() == 1, "Full dashboard offers Simple View")
        verify(page.locator("[data-bounce-stack]").count() >= 3,
               "Patient dashboard groups functional cards into bounce stacks")
        page.emulate_media(reduced_motion="no-preference")
        page.reload()
        page.wait_for_function("""() => document.querySelector('.patient-top-tiles')?.dataset.stackState === 'stacked'""")
        verify(page.locator(".patient-top-tiles .dashboard-stack-open").is_visible(),
               "Patient card stack can be spread from a clear button")
        verify(page.locator(".patient-top-tiles [data-bounce-card]").first.evaluate("(el) => el.inert"),
               "Stacked card form controls are inert until revealed")
        page.locator(".patient-top-tiles .dashboard-stack-open").click()
        verify(page.locator(".patient-top-tiles").get_attribute("data-stack-state") == "expanded",
               "Patient cards fly back into their normal grid")
        verify(not page.locator(".patient-top-tiles [data-bounce-card]").first.evaluate("(el) => el.inert"),
               "Patient actions are reachable after spreading cards")
        page.emulate_media(reduced_motion="reduce")
        page.reload()
        verify(page.locator(".patient-top-tiles").get_attribute("data-stack-state") != "stacked",
               "Reduced-motion patients see normal accessible dashboard layout")
        verify(page.locator('link[href*="app-world.css"]').count() == 1,
               "Signed-in patient dashboard loads the new design system")
        verify("mc-app-shell" in page.locator("body").get_attribute("class"),
               "New authenticated theme is applied to the actual patient interface")
        verify(page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(10, 10, 10)",
               "Real patient dashboard has near-black background")
        verify(page.locator(".mc-app-hero-art").count() == 1,
               "Patient dashboard contains the illustrated immersive hero")
        page.wait_for_function("() => document.querySelector('.mc-app-hero-art').complete && document.querySelector('.mc-app-hero-art').naturalWidth > 0")
        verify(page.locator(".welcome-banner").evaluate(
               "(el) => getComputedStyle(el).backgroundImage.includes('gradient')"),
               "Patient welcome card uses the new atmospheric scene treatment")
        verify(page.locator("[data-quick-support-button]").count() == 1,
               "Important patient Need Support button survives full visual transformation")
        for route,selector in [
            ("/games",".games-catalog"),
            ("/reminders",".reminders-layout"),
            ("/family",".family-layout"),
            ("/help",".sos-callout"),
            ("/settings",".settings-form")
        ]:
            page.goto(base + route)
            verify(page.locator(selector).count() > 0, f"{route} functionality preserved")
            verify("mc-app-shell" in page.locator("body").get_attribute("class"),
                   f"{route} uses actual new app theme")
            verify(page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(10, 10, 10)",
                   f"{route} dark background is actually rendered")
        page.goto(base + "/dashboard")


        verify(page.locator("#milo-roamer").count() == 1, "Milo appears on signed-in patient pages")
        verify(page.locator("#milo-nav-toggle").count() == 1, "Milo show/hide control remains accessible")
        page.locator("#milo-character").click()
        verify(page.locator("#milo-panel").is_visible(), "Tap Milo to open friendly contextual guidance")
        page.locator("#milo-explain").click()
        verify(page.locator("#milo-tip").is_visible(), "Milo explains the current page on request")
        verify(page.locator("#milo-speak").is_visible(), "Read-aloud button appears only after requesting guidance")
        verify(page.locator("#milo-motion-toggle").is_disabled(), "Reduced-motion preference prevents autonomous roaming")
        page.locator("#milo-hide").click()
        verify(page.locator("#milo-roamer").is_hidden(), "Patient can hide Milo")
        verify(page.locator("#milo-nav-toggle").get_attribute("aria-pressed") == "false",
               "Milo is recoverable using a visible navigation control")
        page.reload()
        verify(page.locator("#milo-roamer").is_hidden(), "Hide preference survives refresh on same device")
        page.locator("#milo-nav-toggle").click()
        verify(page.locator("#milo-roamer").is_visible(), "Patient can restore Milo")
        verify(page.locator("[data-quick-support-button]").count() == 1, "Full dashboard has a prominent Need Support button")
        verify(page.get_by_text("Your activity", exact=True).count() == 1, "Full dashboard loads activity")
        verify(page.locator(".stats-row .stat-card").count() == 3,
               "Patient activity totals remain visible")
        verify(page.locator(".trend-chart, .empty-chart").count() == 0,
               "Activity-over-time graph and empty placeholder are removed")
        verify(page.get_by_text("Activity over time", exact=True).count() == 0,
               "Patient dashboard omits complex activity-over-time heading")

        page.locator(".patient-mode-shortcut button").click()
        page.wait_for_selector(".simple-dashboard")
        verify(page.locator(".simple-action-card").count() == 4, "Simple View has four action cards")
        verify(page.locator(".simple-actions > .simple-checkin").count() == 1,
               "Wellbeing check-in is the fifth card in Simple View's stack")
        verify(page.locator(".simple-actions > .simple-checkin").evaluate(
               "(el) => getComputedStyle(el).gridColumnStart === '1'"),
               "Wellbeing card spans both columns after it expands")
        verify(page.locator(".simple-actions[data-bounce-stack]").count() == 1,
               "Simple View action cards use the bounce stack")
        page.set_viewport_size({"width": 1280, "height": 860})
        page.emulate_media(reduced_motion="no-preference")
        page.reload()
        page.wait_for_function("""() => document.querySelector('.simple-actions')?.dataset.stackState === 'stacked'""")
        verify(page.locator(".simple-actions .dashboard-stack-open").is_visible(),
               "Simple View shows the touch-to-spread control")
        verify(page.locator(".simple-action-card").first.evaluate("(el) => el.inert"),
               "Simple View stacked controls are not accidentally interactive")
        verify(page.locator(".simple-checkin").evaluate("(el) => el.inert"),
               "Wellbeing check-in cannot accidentally submit while stacked")
        page.locator(".simple-actions .dashboard-stack-open").click()
        verify(page.locator(".simple-actions").get_attribute("data-stack-state") == "expanded",
               "Simple View cards spring back to their original positions")
        verify(not page.locator(".simple-action-card").first.evaluate("(el) => el.inert"),
               "Simple View cards are usable after expanding")
        verify(not page.locator(".simple-checkin").evaluate("(el) => el.inert"),
               "Wellbeing check-in can be used after the cards spread")
        verify(page.locator(".simple-checkin-form input[name='feeling']").count() == 4,
               "All four feeling options remain available")
        verify(page.locator(".simple-checkin-form button[type='submit']").is_visible(),
               "Save check-in remains visible after animation")
        verify(page.locator(".simple-actions .dashboard-stack-open").is_hidden(),
               "Simple View expand control disappears after use")
        page.emulate_media(reduced_motion="reduce")
        page.reload()
        verify(page.locator(".simple-actions").get_attribute("data-stack-state") != "stacked",
               "Reduced-motion Simple View retains a static, accessible layout")
        verify(page.locator(".simple-checkin-form input[name='feeling']").count() == 4,
               "Reduced-motion users can still choose a feeling")
        verify(page.locator(".simple-banner .mc-app-hero-art").count() == 1,
               "Simplified dashboard has the original illustrated hero")
        verify(page.locator(".simple-game").evaluate(
               "(el) => getComputedStyle(el).backgroundImage.includes('gradient')"),
               "Simplified patient cards retain vivid high-contrast visual differentiation")

        verify(page.locator("[data-quick-support-button]").count() == 1, "Simple View also has a prominent Need Support button")
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
        page.locator("[data-quick-support-button]").click()
        page.wait_for_url("**/dashboard*")
        verify(page.locator(".support-help-box").count() == 1,
               "Need support displays manual contact actions")
        verify(page.locator(".patient-support-quick-saved").count() == 1,
               "One-tap Need Support acknowledgement appears without a second submit")
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

        # A separate, ordinary-motion tab proves Milo really travels by itself.
        walking_tab = ctx.new_page()
        walking_tab.emulate_media(reduced_motion="no-preference")
        walking_tab.goto(base + "/dashboard")
        walking_tab.evaluate("""() => {
          localStorage.setItem('mindcare-milo-hidden-v1','0');
          localStorage.setItem('mindcare-milo-paused-v1','0');
        }""")
        walking_tab.reload()
        verify(walking_tab.locator("#milo-roamer").is_visible(), "Milo is visible with standard motion")
        walking_tab.wait_for_function(
          "() => document.getElementById('milo-roamer')?.dataset.miloState === 'walking'",
          timeout=24000
        )
        verify(walking_tab.locator("#milo-roamer").get_attribute("data-milo-state") == "walking",
               "Milo autonomously walks between clear spots on the patient dashboard")
        walking_tab.locator("#milo-character").dispatch_event("click")
        verify(walking_tab.locator("#milo-panel").is_visible(),
               "Milo stops roaming when the patient asks for help")
        walking_tab.locator("#milo-motion-toggle").click()
        verify(walking_tab.locator("#milo-motion-toggle").get_attribute("aria-pressed") == "true",
               "Pause walking is an explicit patient control")
        walking_tab.locator("#milo-close").click()
        walking_tab.reload()
        verify(walking_tab.locator("#milo-motion-toggle").get_attribute("aria-pressed") == "true",
               "Pause walking preference persists across refresh")
        verify(walking_tab.locator("#milo-roamer").get_attribute("data-milo-state") == "resting",
               "Paused Milo remains stationary")
        walking_tab.close()

        print(json.dumps({"status": "passed", "checks": len(results), "details": results}, ensure_ascii=False))
        browser.close()
finally:
    server.shutdown()
    server.server_close()
    tempdir.cleanup()
