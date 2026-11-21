#!/usr/bin/env python3
"""Kvish 6 (Highway 6) open-invoice checker (Home Assistant app).

Logs in to the customer area with ID + password, reads the open invoices
(and invoices in legal process) and publishes them to Home Assistant as
sensor.kvish6_open_invoices. Read-only: never pays anything.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import traceback

import requests

BASE = "https://service.kvish6.co.il"
API = BASE + "/api"
SENSOR = "sensor.kvish6_open_invoices"
OPTIONS_FILE = "/data/options.json"
STATE_FILE = "/data/state.json"
HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- Home Assistant
def ha_post(path, payload):
    if not HA_TOKEN:
        log(f"(no SUPERVISOR_TOKEN) would POST {path}: {json.dumps(payload, ensure_ascii=False)[:500]}")
        return
    r = requests.post(f"{HA_URL}{path}",
                      headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=20)
    if r.status_code >= 300:
        log(f"HA POST {path} failed: {r.status_code} {r.text[:200]}")


def publish(state, attrs):
    base = {"friendly_name": "Kvish 6 open invoices", "icon": "mdi:highway"}
    if state != "error":
        base.update({"unit_of_measurement": "invoices", "state_class": "measurement"})
    ha_post(f"/states/{SENSOR}", {"state": state, "attributes": {**base, **attrs}})


def notify(service, title, message):
    if not service:
        return
    domain, _, name = service.partition(".")
    if not name:
        domain, name = "notify", service
    ha_post(f"/services/{domain}/{name}", {"title": title, "message": message})


# ---------------------------------------------------------------------- Kvish 6
def api(s, path, body):
    r = s.post(API + path, data="null" if body is None else json.dumps(body),
               headers={"Content-Type": "application/json;charset=UTF-8"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get("Success"):
        raise RuntimeError(f"{path}: {j.get('Message') or j}")
    return j.get("Payload") or {}


def number(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(v or ""))
    return float(m.group(0).replace(",", "")) if m else 0.0


def pick(d, *names):
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return low[n.lower()]
    return None


def summarize(inv, kind):
    return {
        "type": kind,
        "invoice_number": pick(inv, "invoiceNum", "InvoiceNum", "invoiceNumber"),
        "period": pick(inv, "invoicePeriod", "InvoicePeriod", "period"),
        "date": pick(inv, "invoicedate", "invoiceDate", "invoiceUnformattedDate"),
        "due_date": pick(inv, "dueDate", "paymentDueDate", "lastPaymentDate"),
        "amount": pick(inv, "invoiceAmount", "amount", "invoiceTotal", "total"),
        "raw": inv,
    }


def check(cfg):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                      "Origin": BASE, "Referer": BASE + "/"})
    s.get(BASE + "/", timeout=30)
    try:
        api(s, "/gen/getLovsAndParameters", None)
    except Exception as e:
        log(f"getLovsAndParameters: {e} (continuing)")

    log("Logging in")
    login = api(s, "/auth/login", {"IdNum": cfg["id_number"], "Password": cfg["password"],
                                   "PhoneNumber": "", "gRecaptchaResponse": ""})
    if login.get("IsCaptchaMandatory") and not login.get("isLoggedIn"):
        raise RuntimeError("Site requires a CAPTCHA for login right now")
    if not login.get("isLoggedIn"):
        raise RuntimeError(f"Login failed: {re.sub('<[^>]+>', ' ', login.get('invalidLoginMsg') or 'unknown reason').strip()}")
    if login.get("showRenewMsg"):
        raise RuntimeError("Site asks to renew the password - log in once on the website")

    log("Reading open invoices")
    token = api(s, "/Payment/PaymentNavigation", None).get("Token")
    data = api(s, "/Payment/getCustOpenInvoices", {"Token": token})
    invoices = [summarize(i, "open") for i in data.get("openInvoices") or []]
    invoices += [summarize(i, "legal_process") for i in data.get("legalProcessInvoices") or []]
    notes = [re.sub("<[^>]+>", " ", n.get("noteText") or "").strip()
             for n in data.get("notes") or [] if n.get("displayNote")]
    return invoices, notes


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def check_once(cfg):
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        invoices, notes = check(cfg)
    except Exception as e:
        log("Check failed:\n" + traceback.format_exc())
        publish("error", {"last_check": now, "error": str(e)[:250]})
        notify(cfg.get("notify_service"), "Kvish 6 check failed", str(e)[:200])
        return
    total = round(sum(number(i["amount"]) for i in invoices), 2)
    log(f"Open invoices: {len(invoices)}, total {total}")
    publish(str(len(invoices)), {"last_check": now, "invoices": invoices,
                                 "total_amount": total, "notes": notes, "error": None})

    st = load_state()
    keys = sorted(str(i["invoice_number"] or json.dumps(i["raw"], sort_keys=True)) for i in invoices)
    new = [i for i, k in zip(invoices, [str(i["invoice_number"] or json.dumps(i["raw"], sort_keys=True)) for i in invoices])
           if k not in st.get("keys", [])]
    if new:
        lines = [f'{i["invoice_number"] or "?"} | {i["period"] or i["date"] or ""} | {i["amount"]}' for i in new]
        notify(cfg.get("notify_service"), f"New Kvish 6 invoice ({len(new)})", "\n".join(lines))
    with open(STATE_FILE, "w") as f:
        json.dump({"keys": keys, "last_check": now}, f)


def main():
    with open(OPTIONS_FILE) as f:
        cfg = json.load(f)
    missing = [k for k in ("id_number", "password") if not str(cfg.get(k) or "").strip()]
    if missing:
        log(f"Missing settings: {', '.join(missing)} - fill them in the Configuration tab")
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
