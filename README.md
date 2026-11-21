# Jerusalem Parking Tickets – Home Assistant app

Checks **active** parking tickets for an ID on the Jerusalem municipality site
(https://jeronlineforms.jerusalem.muni.il/Parking), reads the email verification
code from Gmail, and publishes the result as `sensor.jerusalem_parking_tickets`.
It only reads tickets: it never pays, appeals or submits anything.

Requires Home Assistant OS (apps support), amd64.

## 1. Gmail app password
1. Google Account → Security → turn on **2-Step Verification** (if not already).
2. Open https://myaccount.google.com/apppasswords → create one named `Home Assistant`.
3. Copy the 16-character password.

## 2. Install
1. Settings → **Apps** → **Install app** (the App store).
2. ⋮ (top right) → **Repositories** → add
   `https://github.com/ahmadqdemat/ha-jerusalem-parking` → **Add** → close.
3. ⋮ → **Check for updates** → find **Jerusalem Parking Tickets** → **Install**
   (first build takes ~5–10 min).

Note: this is an app, not a HACS/Marketplace integration — add it in the App store, not in HACS.

## 3. Configure
In the app's **Configuration** tab fill in:

| option | example | meaning |
|---|---|---|
| `id_number` | `123456789` | ID to search tickets for |
| `first_name`, `last_name` | | as registered with the municipality |
| `phone_prefix` | `052` | mobile prefix (dropdown value on the site) |
| `phone_number` | `1234567` | 7 digits after the prefix |
| `email` | `me@gmail.com` | where the municipality sends the code |
| `date_of_birth` | `31/12/1990` | `DD/MM/YYYY` |
| `street` | `... - רחוב` | exact street name as shown in the site's Street list |
| `house_number` | `2` | |
| `gmail_address` | `me@gmail.com` | Gmail account that receives the code |
| `gmail_app_password` | | from step 1 |
| `check_interval_hours` | `24` | `0` = check once and stop |
| `notify_service` | `notify.mobile_app_my_phone` | optional phone alert for new tickets / errors |
| `headless` | `false` | `false` runs a real browser on a virtual screen (less likely to be blocked by reCAPTCHA) |

Then **Start** and watch the **Log** tab.

## How it runs
- Checks on start, then every `check_interval_hours`.
- Check now: restart the app (or use the script below).
- Screenshots of the last run: `/share/jerusalem_parking/` (`last_result.png`, `last_error.png`).

## Sensor
`sensor.jerusalem_parking_tickets`
- state: number of active tickets (or `error`)
- attributes: `tickets` (date, ticket_number, offense, address, vehicle, status, amount,
  interest, balance_due), `total_balance_due`, `last_check`, `error`

## "Check now" script (scripts.yaml)
Use the app's slug as shown in its page URL (`/config/app/<slug>/info`):
```yaml
check_parking_tickets:
  alias: Check parking tickets now
  sequence:
    - action: hassio.addon_restart
      data:
        addon: <slug>
```
