# Changelog

## 1.0.6 – 2026-11-22
- If the ticket list doesn't open after entering the code, click Continue again, wait up to 90 s,
  and log what the page shows.
- A failed check is retried once after 60 s before reporting an error.

## 1.0.5 – 2026-11-21
- Don't fail when the page keeps loading in the background (analytics); waits up to 10 s, then reads the tickets.

## 1.0.4 – 2026-11-21
- Removed the `street_search` option; the street filter word is taken from `street`.

## 1.0.3 – 2026-11-21
- `street_search` made optional.

## 1.0.2 – 2026-11-21
- Fixed the build: install `libatomic1` before Playwright.

## 1.0.1 – 2026-11-21
- Docs updated for Home Assistant Apps (App store install).

## 1.0.0 – 2026-11-21
- First version: active Jerusalem parking tickets (`sensor.jerusalem_parking_tickets`),
  email verification code read from Gmail.
