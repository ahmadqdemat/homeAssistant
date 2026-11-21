#!/usr/bin/env python3
"""Jerusalem municipality parking-ticket checker (Home Assistant add-on).

Fills the ID-search form, picks the email OTP, reads the code from Gmail over
IMAP, then reads the "Active tickets" list and publishes it to Home Assistant
as sensor.jerusalem_parking_tickets. Read-only: never pays or submits requests.
"""
import datetime as dt
import email
import email.utils
import imaplib
import json
import os
import re
import subprocess
import sys
import time
import traceback

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = "https://jeronlineforms.jerusalem.muni.il/Parking?langId=3"
OTP_SENDER = "noreplyjeru@jerusalem.muni.il"
SENSOR = "sensor.jerusalem_parking_tickets"
OPTIONS_FILE = "/data/options.json"
STATE_FILE = "/data/state.json"
SHARE_DIR = "/share/jerusalem_parking"

HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- Home Assistant
def ha_post(path, payload):
    if not HA_TOKEN:
        log(f"(no SUPERVISOR_TOKEN) would POST {path}: {json.dumps(payload, ensure_ascii=False)[:500]}")
        return
    r = requests.post(
        f"{HA_URL}{path}",
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=20,
    )
    if r.status_code >= 300:
        log(f"HA POST {path} failed: {r.status_code} {r.text[:200]}")


def publish(state, attrs):
    attrs = {
        "friendly_name": "Jerusalem parking tickets",
        "icon": "mdi:car-brake-parking",
        "unit_of_measurement": "tickets",
        "state_class": "measurement",
        **attrs,
    }
    if state == "error":
        attrs.pop("unit_of_measurement")
        attrs.pop("state_class")
    ha_post(f"/states/{SENSOR}", {"state": state, "attributes": attrs})


def notify(service, title, message):
    if not service:
        return
    domain, _, name = service.partition(".")
    if not name:
        domain, name = "notify", service
    ha_post(f"/services/{domain}/{name}", {"title": title, "message": message})


# ---------------------------------------------------------------------- Gmail
def find_otp(cfg, since_utc):
    """Return the newest OTP code emailed after since_utc, or None."""
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(cfg["gmail_address"], cfg["gmail_app_password"].replace(" ", ""))
        imap.select("INBOX", readonly=True)
        day = since_utc.strftime("%d-%b-%Y")
        typ, data = imap.search(None, f'(FROM "{OTP_SENDER}" SINCE {day})')
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        best = None
        for mid in reversed(ids[-10:]):
            typ, msg_data = imap.fetch(mid, "(BODY.PEEK[])")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            try:
                sent = email.utils.parsedate_to_datetime(msg["Date"]).astimezone(dt.timezone.utc)
            except Exception:
                continue
            if sent < since_utc:
                continue
            text = ""
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    payload = part.get_payload(decode=True) or b""
                    text += payload.decode(part.get_content_charset() or "utf-8", "ignore")
            text = re.sub(r"<[^>]+>", " ", text)
            m = re.search(r"\bis\s+(\d{4,8})\b", text) or re.search(r"\b(\d{6})\b", text)
            if m and (best is None or sent > best[0]):
                best = (sent, m.group(1))
        return best[1] if best else None
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def wait_for_otp(cfg, since_utc, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        code = find_otp(cfg, since_utc)
        if code:
            return code
        time.sleep(5)
    return None


# ------------------------------------------------------------------- Browser
def field(page, label):
    """Visible PrimeNG .p-field whose label text equals `label`."""
    rx = re.compile(rf"^\s*{re.escape(label)}\s*\*?\s*$")
    return page.locator("div.p-field:visible").filter(
        has=page.locator("label.field-label", has_text=rx)
    ).first


def click_continue(scope):
    scope.locator("button:visible", has_text=re.compile(r"^\s*Continue\s*$")).last.click()


def pick_dropdown(page, fld, option_label, filter_text=None):
    fld.locator(".p-dropdown").first.click()
    if filter_text:
        flt = page.locator(".p-dropdown-filter:visible").first
        flt.fill(filter_text)
        page.wait_for_timeout(1500)
    opt = page.locator(f'li[role="option"][aria-label="{option_label}"]:visible')
    if opt.count() == 0:
        opt = page.get_by_role("option", name=option_label, exact=True)
    opt.first.click()
    page.wait_for_timeout(400)


def check_captcha(page):
    for fr in page.frames:
        if "recaptcha" in fr.url and "bframe" in fr.url:
            try:
                if page.locator('iframe[src*="bframe"]').first.is_visible():
                    raise RuntimeError("reCAPTCHA challenge appeared - site blocked the automated browser")
            except PWTimeout:
                pass


def parse_tickets(page):
    tickets = []
    for table in page.locator("table:visible").all():
        headers = [h.inner_text().strip() for h in table.locator("th").all()]
        for row in table.locator("tr").all():
            cells = [c.inner_text().strip() for c in row.locator("td").all()]
            if len(cells) < 3 or not any(cells):
                continue
            rec = dict(zip(headers, cells)) if headers else {"cells": cells}
            tickets.append(rec)
    return tickets


def money(v):
    m = re.search(r"[\d,.]+", v or "")
    return float(m.group(0).replace(",", "")) if m else 0.0


def normalize(t):
    def g(*keys):
        for k, v in t.items():
            if any(key.lower() in k.lower() for key in keys):
                return v
        return ""
    return {
        "date": g("date of the ticket", "date"),
        "ticket_number": g("ticket number"),
        "offense": g("offense"),
        "address": g("address"),
        "vehicle": g("vehicle"),
        "status": g("status"),
        "amount": g("ticket amount"),
        "interest": g("ריבית", "interest"),
        "balance_due": g("balance"),
    }


def run_check(cfg):
    os.makedirs(SHARE_DIR, exist_ok=True)
    xvfb = None
    if not cfg.get("headless", False):
        xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1366x900x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ["DISPLAY"] = ":99"
        time.sleep(1.5)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=cfg.get("headless", False),
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                locale="he-IL",
                timezone_id="Asia/Jerusalem",
                viewport={"width": 1366, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"),
            )
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()
            page.set_default_timeout(30000)
            try:
                return _flow(page, cfg)
            except Exception:
                try:
                    page.screenshot(path=f"{SHARE_DIR}/last_error.png", full_page=True)
                    with open(f"{SHARE_DIR}/last_error.html", "w", encoding="utf-8") as f:
                        f.write(page.content())
                except Exception:
                    pass
                raise
            finally:
                browser.close()
    finally:
        if xvfb:
            xvfb.terminate()


def _flow(page, cfg):
    log("Opening site")
    page.goto(URL, wait_until="networkidle")
    page.get_by_role("menuitem", name="English").click()
    page.get_by_role("radio", name="ID no.").wait_for(state="visible")
    page.get_by_role("radio", name="ID no.").click()

    log("Step 1: ID")
    field(page, "ID number").locator("input").first.fill(cfg["id_number"])
    click_continue(page)
    field(page, "First Name").wait_for(state="visible")

    log("Step 1: personal details")
    field(page, "First Name").locator("input").first.fill(cfg["first_name"])
    field(page, "Last Name").locator("input").first.fill(cfg["last_name"])

    phone = field(page, "Mobile Phone")
    pick_dropdown(page, phone, cfg["phone_prefix"])
    phone.locator("input#cellphone, input[type=tel]").first.fill(cfg["phone_number"])

    field(page, "Email").locator("input").first.fill(cfg["email"])

    dob = field(page, "Date of birth").locator("input").first
    dob.click()
    dob.press("Home")
    page.keyboard.type(cfg["date_of_birth"].replace("/", ""), delay=60)
    if dob.input_value() != cfg["date_of_birth"]:
        raise RuntimeError(f"Date of birth not accepted (got {dob.input_value()!r})")

    search = cfg["street"].split(" - ")[0].split()[0]
    pick_dropdown(page, field(page, "Street"), cfg["street"], search)

    house = field(page, "House number").locator("input").first
    house.click()
    page.keyboard.type(str(cfg["house_number"]), delay=60)
    page.keyboard.press("Tab")

    page.screenshot(path=f"{SHARE_DIR}/step1.png")
    click_continue(page)

    log("Step 2: two-step verification")
    email_btn = page.get_by_text(re.compile(r"^\s*Email\s+notification\s*$")).first
    try:
        email_btn.wait_for(state="visible", timeout=30000)
    except PWTimeout:
        check_captcha(page)
        raise RuntimeError("Two-step verification dialog did not appear")
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=20)
    email_btn.click()

    code = wait_for_otp(cfg, since, timeout=90)
    if not code:
        log("No code yet - asking the site to resend")
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=20)
        page.get_by_text(re.compile("Not received", re.I)).first.click()
        code = wait_for_otp(cfg, since, timeout=90)
    if not code:
        raise RuntimeError("Verification code email not found in Gmail")
    log("Got verification code")

    dialog = page.locator(".p-dialog:visible").last
    code_field = field(page, "The identification code")
    code_input = code_field.locator("input").first if code_field.count() else dialog.locator("input:visible").first
    code_input.click()
    page.keyboard.type(code, delay=60)
    click_continue(dialog if dialog.count() else page)

    log("Step 3: reading active tickets")
    active = page.get_by_role("radio", name="Active tickets")
    active.wait_for(state="visible", timeout=60000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    if active.get_attribute("aria-checked") != "true":
        active.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

    page.screenshot(path=f"{SHARE_DIR}/last_result.png", full_page=True)
    return [normalize(t) for t in parse_tickets(page)]


# ----------------------------------------------------------------------- main
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)


def check_once(cfg):
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        tickets = run_check(cfg)
    except Exception as e:
        log("Check failed:\n" + traceback.format_exc())
        publish("error", {"last_check": now, "error": str(e)[:250]})
        notify(cfg.get("notify_service"), "Parking check failed", str(e)[:200])
        return
    total = round(sum(money(t["balance_due"]) for t in tickets), 2)
    log(f"Active tickets: {len(tickets)}, balance due {total}")
    publish(str(len(tickets)), {"last_check": now, "tickets": tickets,
                                "total_balance_due": total, "error": None})

    st = load_state()
    ids = sorted(t["ticket_number"] for t in tickets)
    new = [t for t in tickets if t["ticket_number"] not in st.get("ids", [])]
    if new:
        lines = [f'{t["date"]} | {t["ticket_number"]} | {t["balance_due"] or t["amount"]}' for t in new]
        notify(cfg.get("notify_service"), f"New parking ticket ({len(new)})", "\n".join(lines))
    save_state({"ids": ids, "last_check": now})


def main():
    with open(OPTIONS_FILE) as f:
        cfg = json.load(f)
    required = ["id_number", "first_name", "last_name", "phone_prefix", "phone_number", "email",
                "date_of_birth", "street", "house_number",
                "gmail_address", "gmail_app_password"]
    missing = [k for k in required if not str(cfg.get(k) or "").strip() or cfg.get(k) == "05X"]
    if missing:
        log(f"Missing settings: {', '.join(missing)} - fill them in the add-on Configuration tab")
        publish("error", {"error": f"missing settings: {', '.join(missing)}"})
        sys.exit(1)
    hours = int(cfg.get("check_interval_hours") or 0)
    while True:
        check_once(cfg)
        if hours <= 0:
            log("check_interval_hours is 0 - single run, exiting")
            return
        log(f"Next check in {hours}h")
        time.sleep(hours * 3600)


if __name__ == "__main__":
    main()
