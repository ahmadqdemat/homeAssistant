# Home Assistant apps

A collection of Home Assistant apps (formerly add-ons).

## Install
Settings → **Apps** → **Install app** → ⋮ → **Repositories** → add
`https://github.com/ahmadqdemat/homeAssistant` → **Add** → close → ⋮ → **Check for updates**.

Note: these are apps, not HACS/Marketplace integrations — add the repository in the App store, not in HACS.

## Apps
| app | what it does | sensor | docs |
|---|---|---|---|
| **Jerusalem Parking Tickets** | active Jerusalem municipality parking tickets (email code read from Gmail) | `sensor.jerusalem_parking_tickets` | [jerusalem_parking/DOCS.md](jerusalem_parking/DOCS.md) |
| **Kvish 6 Invoices** | open Highway 6 toll invoices (ID + password login) | `sensor.kvish6_open_invoices` | [kvish6_invoices/DOCS.md](kvish6_invoices/DOCS.md) |
| **JDECo Electricity Bills** | unpaid electricity bills and last meter reading (login token, renewed automatically) | `sensor.jdeco_amount_due`, `sensor.jdeco_last_meter_reading`, `sensor.jdeco_prepaid_balance` | [jdeco_bills/DOCS.md](jdeco_bills/DOCS.md) |

All apps are read-only: they never pay, appeal or submit anything.
Each app's setup is also shown in its **Documentation** tab in Home Assistant.

Sensors are created through the Home Assistant API, so they don't appear under
Settings → Entities; find them in Developer tools → **States**.

## Adding a new app
Each app is a folder with `config.yaml`, `Dockerfile`, `run.py`, `DOCS.md` and `CHANGELOG.md`.
Every change bumps `version` in `config.yaml` and adds an entry to the app's `CHANGELOG.md`
(Home Assistant shows it in the update dialog).
