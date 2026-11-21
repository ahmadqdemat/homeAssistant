# JDECo Electricity Bills

Reads your Jerusalem District Electricity (jdeco.net) account and publishes:

| sensor | state | attributes |
|---|---|---|
| `sensor.jdeco_amount_due` | total of unpaid bills (₪) | `unpaid_bills` (invoice_number, amount, date, due_date), `unpaid_count`, `last_check`, `error` |
| `sensor.jdeco_last_meter_reading` | last meter reading (kWh) – "آخر قراءة للعداد" | `reading_date`, `last_check` |
| `sensor.jdeco_prepaid_balance` | prepaid balance (kWh) – field `prepaidBalanceKwh` | `last_check` |

Read-only: it never pays anything.

## Why a token instead of a password
The jdeco.net login has a "verify you are human" check that an app can't pass.
So you log in once yourself and give the app your login's **refresh token**. The app
renews it on every check, so it stays valid as long as the app runs at least once
every 30 days. If it ever expires, the sensor shows `error` and you get a notification
(if `notify_service` is set) – just repeat the steps below.

## Get the refresh token
Use a **separate** browser session so your normal login isn't affected:
1. In Chrome open a new **Incognito window** (Ctrl+Shift+N) and log in at https://www.jdeco.net.
2. Open your meter's bills page and note the number in the address:
   `https://www.jdeco.net/account/meters/`**`132`**`?view=bills` → `account_id` = `132`.
3. Press **F12** → **Application** → **Storage → Cookies** → `https://www.jdeco.net`.
4. Click the cookie **`jdeco_customer_refresh`** and copy its **Value**.
5. Close the Incognito window **without logging out** (logging out cancels the token).

## Configure
| option | meaning |
|---|---|
| `refresh_token` | the `jdeco_customer_refresh` cookie value |
| `account_id` | the number from the bills page address (e.g. `132`) |
| `check_interval_minutes` | how often to check, in minutes – default `720` (12 h), min `5`, max `43200` (30 days) |
| `notify_service` | optional, e.g. `notify.mobile_app_my_phone` – new bills, errors, expired login |

Start the app and check the **Log** tab. The raw data of the last check is saved in
`/share/jdeco_bills/` (useful if a value is missing).

Pasting a new `refresh_token` later makes the app use it on the next start.
