#!/usr/bin/env python3
"""JDECo (Jerusalem District Electricity) bills checker - Home Assistant app.

Uses the customer-area refresh token (cookie `jdeco_customer_refresh`) to get a
short-lived access token, reads the account's bills and details, and publishes:
  sensor.jdeco_amount_due          total of unpaid bills (₪) + list of unpaid bills
  sensor.jdeco_last_meter_reading  last meter reading (kWh) + reading date
The refresh token is renewed on every check and saved in /data, so the login
stays valid as long as the app runs at least once every 30 days.
Read-only: never pays anything.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import traceback

import requests

BASE = "https://www.jdeco.net"
REFRESH_COOKIE = "jdeco_customer_refresh"
OPTIONS_FILE = "/data/options.json"
TOKEN_FILE = "/data/token.json"
STATE_FILE = "/data/state.json"
DUMP_DIR = "/share/jdeco_bills"
HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")


class LoginExpired(Exception):
    pass


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- Home Assistant
def ha_post(path, payload):
    if not HA_TOKEN:
        log(f"(no SUPERVISOR_TOKEN) would POST {path}: {json.dumps(payload, ensure_ascii=False)[:600]}")
        return
    r = requests.post(f"{HA_URL}{path}",
                      headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
                      data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"), timeout=20)
    if r.status_code >= 300:
        log(f"HA POST {path} failed: {r.status_code} {r.text[:200]}")


def set_state(entity, state, attrs):
    ha_post(f"/states/{entity}", {"state": state, "attributes": attrs})


def notify(service, title, message):
    if not service:
        return
    domain, _, name = service.partition(".")
    if not name:
        domain, name = "notify", service
    ha_post(f"/services/{domain}/{name}", {"title": title, "message": message})


# ------------------------------------------------------------------ token store
def sha(s):
    return hashlib.sha256((s or "").encode()).hexdigest()


def load_token(cfg):
    """Use the token pasted in the config if it changed, else the saved (rotated) one."""
    cfg_tok = (cfg.get("refresh_token") or "").strip()
    try:
        with open(TOKEN_FILE) as f:
            saved = json.load(f)
    except Exception:
        saved = {}
    if cfg_tok and saved.get("config_hash") != sha(cfg_tok):
        return cfg_tok, sha(cfg_tok)
    return saved.get("refresh") or cfg_tok, saved.get("config_hash") or sha(cfg_tok)


def save_token(tok, config_hash):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"refresh": tok, "config_hash": config_hash,
                   "saved": dt.datetime.now().isoformat(timespec="seconds")}, f)


# --------------------------------------------------------------------- helpers
def find_token(obj):
    """Find an access token in the refresh response."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and len(v) > 20 and re.search(r"access.?token|^token$|jwt", k, re.I):
                return v
        for v in obj.values():
            t = find_token(v)
            if t:
                return t
    elif isinstance(obj, list):
        for v in obj:
            t = find_token(v)
            if t:
                return t
    return None


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(v or ""))
    return float(m.group(0).replace(",", "")) if m else None


def key_of(d, *patterns, exclude=None):
    for k, v in d.items():
        if exclude and re.search(exclude, k, re.I):
            continue
        if any(re.search(p, k, re.I) for p in patterns) and v not in (None, ""):
            return k, v
    return None, None


def find_list(obj):
    """Largest list of dicts inside obj (the bills list)."""
    best = []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        best = obj
    if isinstance(obj, dict):
        for v in obj.values():
            c = find_list(v)
            if len(c) > len(best):
                best = c
    elif isinstance(obj, list):
        for v in obj:
            c = find_list(v)
            if len(c) > len(best):
                best = c
    return best


def is_unpaid(b):
    for k, v in b.items():
        kl = k.lower()
        if isinstance(v, bool) and re.search(r"paid|settled", kl):
            return (not v) if not re.search(r"unpaid|notpaid|open", kl) else v
    for k, v in b.items():
        if isinstance(v, str) and re.search(r"status|state", k, re.I):
            s = v.lower()
            if re.search(r"unpaid|not.?paid|open|due|overdue|pending|غير", s):
                return True
            if re.search(r"paid|settled|closed|مسدد|مدفوع", s):
                return False
    k, v = key_of(b, r"remain|balance|outstanding|due.?amount|amount.?due")
    if k is not None and num(v) is not None:
        return num(v) > 0
    return None


def bill_summary(b):
    def first(*names):
        for n in names:
            if b.get(n) not in (None, ""):
                return b[n]
        return None
    _, number = key_of(b, r"voucher.?no|bill.?(no|num)|invoice.?(no|num)", exclude=r"service|account|meter|ref")
    _, date = key_of(b, r"voucher.?date|bill.?date|invoice.?date|issue", exclude=r"due|pay|read")
    amount = first("netAmount", "totalAmount", "billAmount", "amount")
    remaining = first("remainingAmount", "balance", "outstandingAmount")
    return {"invoice_number": number, "date": str(date)[:10] if date else None,
            "due_date": str(first("dueDate") or "")[:10] or None,
            "amount": amount, "remaining": remaining,
            "consumption_kwh": first("consumptionKwh"), "late_days": first("lateDays")}


def reading_candidates(*objs):
    """(value, date, where) for every meter reading found: a numeric 'reading' field
    paired with a date field in the same object. Previous readings are skipped."""
    out = []

    def visit(o, path):
        if isinstance(o, dict):
            dates = [(k, v) for k, v in o.items() if isinstance(v, str)
                     and re.search(r"date|time|at$", k, re.I) and re.match(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", v)]
            rd = [d for d in dates if re.search(r"read", d[0], re.I)] or dates
            for k, v in o.items():
                if re.search(r"read", k, re.I) and not re.search(r"prev|old|count|can|type|date|time|id$|status", k, re.I):
                    n = num(v)
                    if n is not None and rd:
                        out.append((n, rd[0][1], f"{path}.{k}"))
            for k, v in o.items():
                visit(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                visit(v, f"{path}[{i}]")

    for idx, o in enumerate(objs):
        visit(o, f"src{idx}")
    return out


def to_date(s):
    s = str(s)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s[:10], fmt)
        except ValueError:
            pass
    return dt.datetime.min


def find_reading(details, bills=None, accounts=None):
    """Latest meter reading (value, date) across details, bills and accounts."""
    cands = reading_candidates(details, bills, accounts)
    if not cands:
        return None, None, []
    best = max(cands, key=lambda c: (to_date(c[1]), c[0]))
    return best[0], str(best[1])[:10], cands


# ------------------------------------------------------------------------ main
def digits(v):
    return re.sub(r"\D", "", str(v or ""))


def login(cfg):
    tok, cfg_hash = load_token(cfg)
    if not tok:
        raise LoginExpired("refresh_token is empty")
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                      "Accept-Language": "ar,en;q=0.8", "Origin": BASE,
                      "Referer": f"{BASE}/account"})
    s.cookies.set(REFRESH_COOKIE, tok, domain="www.jdeco.net", path="/api/customer")

    log("Refreshing login")
    r = s.post(f"{BASE}/api/customer/token/refresh", json={}, timeout=30)
    if r.status_code in (400, 401, 403):
        if "challenge" in r.text.lower() and "cloudflare" in r.text.lower():
            raise RuntimeError("Blocked by Cloudflare challenge")
        raise LoginExpired(f"refresh rejected ({r.status_code})")
    r.raise_for_status()
    try:
        body = r.json()
    except ValueError:
        body = {}
    new_tok = next((c.value for c in s.cookies if c.name == REFRESH_COOKIE and c.value != tok), None)
    save_token(new_tok or tok, cfg_hash)
    if new_tok:
        log("Login renewed (new refresh token saved)")
    access = find_token(body)
    if access:
        s.headers["Authorization"] = f"Bearer {access}"
    else:
        log("No access token in refresh response - relying on cookies")
    return s


def api_get(s, path):
    resp = s.get(BASE + path, timeout=30)
    if resp.status_code == 401:
        raise LoginExpired(f"{path} returned 401")
    resp.raise_for_status()
    return resp.json()


def dump(name, path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    os.makedirs(DUMP_DIR, exist_ok=True)
    with open(f"{DUMP_DIR}/{name}.json", "w", encoding="utf-8") as f:
        f.write(text)
    log(f"===== {name.upper()} ({BASE}{path}) =====\n{text}")


def resolve_services(cfg, accounts):
    """[(service_number, account_id, account_dict)] for the configured service numbers."""
    lst = find_list(accounts) if accounts is not None else []
    wanted = [digits(x) for x in (cfg.get("service_numbers") or []) if digits(x)]
    out = []
    if wanted:
        for sn in wanted:
            acc = next((a for a in lst if any(digits(v) == sn for k, v in a.items()
                                              if not isinstance(v, (dict, list)))), None)
            if acc is None:
                log(f"WARNING: service number {sn} not found in your accounts")
                continue
            _, aid = key_of(acc, r"^id$|^accountId$|^account_id$")
            if aid is None:
                _, aid = key_of(acc, r"id$")
            out.append((sn, str(aid), acc))
    elif cfg.get("account_id"):
        aid = str(cfg["account_id"])
        acc = next((a for a in lst if any(str(v) == aid for k, v in a.items() if re.search(r"id$", k, re.I))), None)
        _, sn = key_of(acc or {}, r"service.?(no|num)")
        out.append((digits(sn) or aid, aid, acc))
    return out


def process_service(s, sn, aid, acc, now, svc):
    today = dt.date.today()
    details = api_get(s, f"/api/customer/me/accounts/{aid}/details")
    bills = api_get(s, f"/api/customer/me/accounts/{aid}/bills?months=24")
    try:
        payments = api_get(s, f"/api/customer/me/accounts/{aid}/payments?from={today.replace(year=today.year - 1)}&to={today}")
    except Exception as e:
        log(f"payments: {e}")
        payments = None
    dump(f"details_{sn}", f"/api/customer/me/accounts/{aid}/details", details)
    dump(f"bills_{sn}", f"/api/customer/me/accounts/{aid}/bills?months=24", bills)
    dump(f"payments_{sn}", f"/api/customer/me/accounts/{aid}/payments", payments)

    unpaid = []
    for b in find_list(bills):
        if is_unpaid(b):
            u = bill_summary(b)
            u["service_number"] = sn
            unpaid.append(u)
    total = round(sum((num(u["remaining"]) if num(u["remaining"]) else num(u["amount"]) or 0) for u in unpaid), 2)
    value, date, cands = find_reading(details, bills, acc)
    prepaid = None
    for src in (acc, details):
        for path, v in walk(src or {}):
            if path.split(".")[-1].lower() == "prepaidbalancekwh" and num(v) is not None:
                prepaid = num(v)
                break
        if prepaid is not None:
            break

    base = f"sensor.jdeco_{sn}"
    set_state(f"{base}_amount_due", str(total), {
        "friendly_name": f"JDECo {sn} amount due", "icon": "mdi:flash", "unit_of_measurement": "₪",
        "device_class": "monetary", "service_number": sn, "unpaid_count": len(unpaid),
        "unpaid_bills": unpaid, "last_check": now})
    set_state(f"{base}_last_meter_reading", "unknown" if value is None else str(value), {
        "friendly_name": f"JDECo {sn} last meter reading", "icon": "mdi:meter-electric",
        "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
        "service_number": sn, "reading_date": date, "last_check": now})
    set_state(f"{base}_prepaid_balance", "unknown" if prepaid is None else str(prepaid), {
        "friendly_name": f"JDECo {sn} prepaid balance", "icon": "mdi:battery-charging-medium",
        "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "measurement",
        "service_number": sn, "last_check": now})

    log(f"===== RESULT {sn} (account {aid}) =====")
    log(f"Amount due: {total} ₪ ({len(unpaid)} unpaid bill(s))")
    for u in unpaid:
        log(f"  Unpaid: #{u['invoice_number']} | date {u['date']} | due {u['due_date']} | "
            f"amount {u['amount']} | remaining {u['remaining']} | {u['consumption_kwh']} kWh")
    log(f"Last meter reading: {value} kWh on {date}")
    log(f"Prepaid balance: {prepaid} kWh")
    return {"service_number": sn, "total": total, "unpaid": unpaid,
            "reading": value, "reading_date": date, "prepaid": prepaid}


def error_state(now, msg, svc, title):
    set_state("sensor.jdeco_amount_due", "error", {"friendly_name": "JDECo amount due",
              "icon": "mdi:flash-alert", "error": msg, "last_check": now})
    notify(svc, title, msg)


def check_once(cfg):
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    svc = cfg.get("notify_service")
    try:
        s = login(cfg)
        accounts = api_get(s, "/api/customer/me/accounts")
        dump("accounts", "/api/customer/me/accounts", accounts)
        services = resolve_services(cfg, accounts)
        if not services:
            raise RuntimeError("No service found - check service_numbers in the configuration")
        results = [process_service(s, sn, aid, acc, now, svc) for sn, aid, acc in services]
    except LoginExpired as e:
        log(f"Login expired: {e}")
        error_state(now, "JDECo login expired - log in on jdeco.net and paste a new "
                    "jdeco_customer_refresh cookie into the app's refresh_token option",
                    svc, "JDECo login expired")
        return
    except Exception as e:
        log("Check failed:\n" + traceback.format_exc())
        error_state(now, str(e)[:250], svc, "JDECo check failed")
        return

    all_unpaid = [u for r in results for u in r["unpaid"]]
    total = round(sum(r["total"] for r in results), 2)
    set_state("sensor.jdeco_amount_due", str(total), {
        "friendly_name": "JDECo amount due", "icon": "mdi:flash", "unit_of_measurement": "₪",
        "device_class": "monetary", "unpaid_count": len(all_unpaid), "unpaid_bills": all_unpaid,
        "services": [r["service_number"] for r in results], "last_check": now, "error": None})
    first = results[0]
    set_state("sensor.jdeco_last_meter_reading", "unknown" if first["reading"] is None else str(first["reading"]), {
        "friendly_name": "JDECo last meter reading", "icon": "mdi:meter-electric",
        "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
        "service_number": first["service_number"], "reading_date": first["reading_date"], "last_check": now})
    set_state("sensor.jdeco_prepaid_balance", "unknown" if first["prepaid"] is None else str(first["prepaid"]), {
        "friendly_name": "JDECo prepaid balance", "icon": "mdi:battery-charging-medium",
        "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "measurement",
        "service_number": first["service_number"], "last_check": now})
    log(f"===== TOTAL: {total} ₪ due across {len(results)} service(s) =====")

    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except Exception:
        st = {}
    keys = sorted(str(u["invoice_number"]) for u in all_unpaid)
    new = [u for u in all_unpaid if str(u["invoice_number"]) not in st.get("unpaid", [])]
    if new:
        notify(svc, f"New electricity bill ({len(new)})",
               "\n".join(f'{u["service_number"]} | {u["date"]} | {u["amount"]} ₪' for u in new))
    with open(STATE_FILE, "w") as f:
        json.dump({"unpaid": keys, "last_check": now}, f)


def main():
    with open(OPTIONS_FILE) as f:
        cfg = json.load(f)
    if not (cfg.get("refresh_token") or "").strip() and not os.path.exists(TOKEN_FILE):
        log("refresh_token is empty - fill it in the Configuration tab (see Documentation)")
        sys.exit(1)
    minutes = int(cfg.get("check_interval_minutes") or 720)
    while True:
        check_once(cfg)
        log(f"Next check in {minutes} min")
        time.sleep(minutes * 60)


if __name__ == "__main__":
    main()
