# Price Notifier with WhatsApp Alerts

Lightweight FastAPI service that scrapes Amazon product pages, compares current price against a target, and sends WhatsApp alerts via Twilio. Supports immediate checks, optional send delays, recurring 6-hour rechecks, a CSV-backed watchlist, and a simple browser UI.

## Tech Stack
- FastAPI, uvicorn, asyncio
- BeautifulSoup for HTML parsing
- Twilio WhatsApp API
- React static UI served by the backend
- Docker (deployed to Heroku in this project)

## Features
- Amazon-focused price extraction with resilient fallbacks for common price blocks.
- Immediate or delayed WhatsApp alerts; per-request recipient override.
- Recurring background re-check every 6 hours for all saved URLs.
- CSV-backed storage for lightweight multi-URL tracking.
- Health check endpoint and static UI for quick testing.

## API Endpoints
- `GET /` – serves the UI.
- `GET /api/health` – simple liveness check.
- `POST /api/notify` – body: `{ url, target_price, delay_minutes (0–1440), send_to? }`; returns status, parsed price, and Twilio SID when sent.

## Configuration
Set environment variables for Twilio credentials and WhatsApp numbers (e.g., `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `TWILIO_WHATSAPP_TO`). Provide any required Amazon-friendly headers/user-agent if the scraper expects them.

## Run Locally
- Install dependencies and start uvicorn (e.g., `uvicorn app:app --reload` or the provided entrypoint).
- Visit the root URL to submit URLs/targets via the UI or call `/api/notify` directly with JSON.
- Optional: run via Docker; configure env vars and expose the service port.

## Notes & Hardening
- Background loop runs in-process; for production, move recurring jobs and state to a durable scheduler/store.
- Add stricter validation/rate limiting if exposing publicly.
- Scraping is Amazon-specific; adjust selectors if layouts change.
