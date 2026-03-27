import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", "8080"))

CACHE_SECONDS = 240
USER_COOLDOWN_SECONDS = 5

price_cache = {
    "ounce_usd": None,
    "usd_try": None,
    "gram_tl": None,
    "last_update": 0
}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print("WEB SERVER BASLADI")
    server.serve_forever()


def fetch_json(url: str):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_ounce_gold_usd():
    url = "https://api.gold-api.com/price/XAU"
    data = fetch_json(url)

    price = data.get("price")
    if price is None:
        raise ValueError(f"Ons verisi alinamadi: {data}")

    return float(price)


def get_usd_try():
    url = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=TRY"

    try:
        data = fetch_json(url)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise ValueError(f"Kur API HTTP {e.code}: {body}")
    except URLError as e:
        raise ValueError(f"Kur API baglanti hatasi: {e}")

    try_price = data.get("rates", {}).get("TRY")
    if try_price is None:
        raise ValueError(f"TRY kuru alinamadi: {data}")

    return float(try_price)


def calculate_gram_gold_tl(ounce_usd, usd_try):
    return (ounce_usd * usd_try) / 31.1034768


def get_cached_prices():
    now = time.time()

    if (
        price_cache["ounce_usd"] is not None
        and price_cache["usd_try"] is not None
        and price_cache["gram_tl"] is not None
        and now - price_cache["last_update"] < CACHE_SECONDS
    ):
        return (
            price_cache["ounce_usd"],
            price_cache["usd_try"],
            price_cache["gram_tl"],
        )

    ounce_usd = get_ounce_gold_usd()
    usd_try = get_usd_try()
    gram_tl = calculate_gram_gold_tl(ounce_usd, usd_try)

    price_cache["ounce_usd"] = ounce_usd
    price_cache["usd_try"] = usd_try
    price_cache["gram_tl"] = gram_tl
    price_cache["last_update"] = now

    return ounce_usd, usd_try, gram_tl


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot hazir.\n\n"
        "Komutlar:\n"
        "/altin -> gram altin TL hesaplar"
    )


async def altin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last_request_time = context.user_data.get("last_request_time", 0)

    if now - last_request_time < USER_COOLDOWN_SECONDS:
        remaining = int(USER_COOLDOWN_SECONDS - (now - last_request_time)) + 1
        await update.message.reply_text(
            f"Yavaş lann gaç tane alıyoon. {remaining} saniye bekle."
        )
        return

    context.user_data["last_request_time"] = now

    try:
        ounce_usd, usd_try, gram_tl = get_cached_prices()

        message = (
            "💰 Dolar Bazinda Altin Hesaplama\n\n"
            f"🟡 Ons: {ounce_usd:,.2f} USD\n"
            f"💵 Kur: {usd_try:,.4f}\n"
            f"📊 Gram: {gram_tl:,.2f} TL\n\n"
            "ℹ️ Veriler en fazla 4 dakika gecikmeli olabilir."
        )

        await update.message.reply_text(message)

    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")


async def post_init(app):
    await app.bot.delete_webhook(drop_pending_updates=True)


def main():
    print("BOT BASLADI - FRANKFURTER DEV SURUMU")

    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("altin", altin))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
