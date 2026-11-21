# Changelog

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
