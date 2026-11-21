# Jerusalem Parking Tickets – Home Assistant add-on

Checks **active** parking tickets for an ID on the Jerusalem municipality site
(https://jeronlineforms.jerusalem.muni.il/Parking), reads the email verification
code from Gmail, and publishes the result as `sensor.jerusalem_parking_tickets`.
It only reads tickets: it never pays, appeals or submits anything.

## Install
1. Settings → Add-ons → Add-on Store → ⋮ → **Repositories** → add
   `https://github.com/ahmadqdemat/ha-jerusalem-parking`
2. Install **Jerusalem Parking Tickets** (first build ~5–10 min).
3. **Configuration** tab – fill in:
   - `id_number`, `first_name`, `last_name`
   - `phone_prefix` (e.g. `052`), `phone_number` (7 digits)
   - `email` (where the municipality sends the code), `date_of_birth` (`DD/MM/YYYY`)
   - `street` – the exact option text as shown in the site's Street list (e.g. `... - רחוב`)
   - `street_search` – a word typed into the street filter to find it
   - `house_number`
   - `gmail_address` + `gmail_app_password` (see below)
   - optional `notify_service`, e.g. `notify.mobile_app_my_phone`
4. **Start**, then check the **Log** tab.

### Gmail app password
Google Account → Security → turn on 2-Step Verification →
https://myaccount.google.com/apppasswords → create one → paste the 16 characters.

## How it runs
- Checks on start, then every `check_interval_hours` (default 24; 0 = once).
- Check now: restart the add-on, or use the script below.
- Screenshots of the last run: `/share/jerusalem_parking/` (`last_result.png`, `last_error.png`).

## Sensor
`sensor.jerusalem_parking_tickets` – state: number of active tickets (or `error`);
attributes: `tickets` (date, ticket_number, offense, address, vehicle, status, amount,
interest, balance_due), `total_balance_due`, `last_check`, `error`.

### "Check now" script
```yaml
check_parking_tickets:
  alias: Check parking tickets now
  sequence:
    - action: hassio.addon_restart
      data:
        addon: <slug shown in the add-on's URL>_jerusalem_parking
```
