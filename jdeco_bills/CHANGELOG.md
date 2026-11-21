# Changelog

## 1.1.0 – 2026-11-21
- New option `service_numbers`: list the service numbers (رقم الخدمة) to check – several services supported.
- New per-service sensors: `sensor.jdeco_<service>_amount_due`, `_last_meter_reading`, `_prepaid_balance`.
- `sensor.jdeco_amount_due` is now the total of all configured services; the other two combined sensors show the first service.
- `account_id` is now optional and used only when `service_numbers` is empty.

## 1.0.6 – 2026-11-21
- Check interval is now set in minutes: `check_interval_minutes` (default 720, min 5, max 43200).
  Replaces `check_interval_hours`.

## 1.0.5 – 2026-11-21
- New sensor `sensor.jdeco_prepaid_balance` (kWh) from the `prepaidBalanceKwh` field.

## 1.0.4 – 2026-11-21
- The log now shows all data read from JDECo (accounts, details, bills, payments) and a result summary.

## 1.0.3 – 2026-11-21
- Meter reading taken only from the configured `account_id` (accounts with several services showed another service's reading).

## 1.0.2 – 2026-11-21
- Also reads the accounts list, where the latest meter reading ("آخر قراءة للعداد") is.

## 1.0.1 – 2026-11-21
- Unpaid bills use the real fields: invoice number, date, due date, full amount (`netAmount`) and remaining amount.
- Meter reading: the newest reading found is used.

## 1.0.0 – 2026-11-21
- First version: unpaid bills (`sensor.jdeco_amount_due`) and last meter reading (`sensor.jdeco_last_meter_reading`)
  using a refresh token that is renewed on every check.
