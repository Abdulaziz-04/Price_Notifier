import asyncio
import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup
from decouple import config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from twilio.rest import Client
from pathlib import Path


app = FastAPI(title="Price Notifier with WhatsApp Alert", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class NotifyRequest(BaseModel):
    url: HttpUrl
    target_price: float = Field(
        ..., gt=0, description="Price threshold to trigger notification"
    )
    delay_minutes: int = Field(
        0, ge=0, le=1440, description="Minutes to delay WhatsApp delivery"
    )
    send_to: Optional[str] = Field(
        None, description="Override recipient WhatsApp number"
    )


def _twilio_client() -> Client:
    sid = config("SID", default=None)
    auth = config("AUTH", default=None)
    if not sid or not auth:
        raise HTTPException(
            status_code=500, detail="Twilio credentials missing (SID/AUTH)."
        )
    return Client(sid, auth)


def _resolve_recipient(send_to: Optional[str]) -> str:
    to_number = send_to or config("TO_WHATSAPP", default=None)
    if not to_number:
        raise HTTPException(
            status_code=400, detail="Recipient WhatsApp number missing."
        )
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"
    return to_number


def _get_from_number() -> str:
    from_number = config("FROM_WHATSAPP", default=None)
    if not from_number:
        raise HTTPException(
            status_code=500, detail="WhatsApp sender number missing (FROM_WHATSAPP)."
        )
    return from_number


def fetch_price(url: str) -> float:
    headers = {
        "User-Agent": config(
            "USER_AGENT",
            default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    price_text = None
    for pid in ("priceblock_ourprice", "priceblock_dealprice", "priceblock_saleprice"):
        el = soup.find(id=pid)
        if el and el.get_text():
            price_text = el.get_text().strip()
            break
    if not price_text:
        # fallback: first currency-looking pattern
        match = re.search(r"[\d,]+\.?\d*", soup.get_text())
        price_text = match.group(0) if match else None
    if not price_text:
        raise HTTPException(status_code=400, detail="Could not parse price from page.")
    numbers = re.findall(r"[\d,]+\.?\d*", price_text)
    if not numbers:
        raise HTTPException(status_code=400, detail="Price format not recognized.")
    numeric = numbers[0].replace(",", "")
    try:
        return float(numeric)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Price parse failed.") from exc


def send_whatsapp(body: str, to_override: Optional[str] = None) -> str:
    client = _twilio_client()
    to_number = _resolve_recipient(to_override)
    from_number = _get_from_number()
    message = client.messages.create(body=body, from_=from_number, to=to_number)
    return message.sid


async def delayed_whatsapp(
    body: str, delay_minutes: int, to_override: Optional[str]
) -> str:
    if delay_minutes:
        await asyncio.sleep(delay_minutes * 60)
    return send_whatsapp(body, to_override)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(index_path)


@app.post("/api/notify")
async def notify(payload: NotifyRequest):
    price = fetch_price(str(payload.url))
    triggered = price <= payload.target_price

    body = (
        f"Price alert for {payload.url}\n"
        f"Current price: {price}\n"
        f"Target: {payload.target_price}\n"
        f"Triggered: {'yes' if triggered else 'no'}"
    )

    if triggered:
        task = asyncio.create_task(
            delayed_whatsapp(body, payload.delay_minutes, payload.send_to)
        )
        sid = await task
        return {"status": "sent", "sid": sid, "price": price, "triggered": True}
    else:
        return {"status": "not_triggered", "price": price, "triggered": False}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True
    )
