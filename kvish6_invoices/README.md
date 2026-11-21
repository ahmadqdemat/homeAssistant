# Kvish 6 Invoices

Logs in to the Highway 6 (Kvish 6) customer area (https://service.kvish6.co.il) with
your ID and password, reads your **open invoices** (and any in legal process), and
publishes them as `sensor.kvish6_open_invoices`. Read-only: it never pays anything.

## Configure
| option | meaning |
|---|---|
| `id_number` | ID / company number used to log in |
| `password` | customer-area password (the "זיהוי באמצעות סיסמה" login) |
| `check_interval_hours` | default `24`; `0` = check once and stop |
| `notify_service` | optional, e.g. `notify.mobile_app_my_phone` – alert on new invoices / errors |

Then **Start** and watch the **Log** tab. To check now, restart the app.

## Sensor
`sensor.kvish6_open_invoices`
- state: number of open invoices (or `error`)
- attributes: `invoices` (type, invoice_number, period, date, due_date, amount, raw),
  `total_amount`, `notes` (messages shown by the site), `last_check`, `error`

Find it in Developer tools → States (search `kvish6`).
