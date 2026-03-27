import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", "8080"))

processed_updates = set()

CACHE_SECONDS = 10
USER_COOLDOWN_SECONDS = 10

price_cache = {
    "ounce_usd": None,
    "usd_try": None,
    "gram_tl": None,
    "last_update": 0
}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"WEB SERVER BASLADI: {PORT}")
    server.serve_forever()


def get_ounce_gold_usd():
    url = "https://api.gold-api.com/price/XAU"
    with urlopen(url, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    price = data.get("price")
    if price is None:
        raise ValueError("Ons altın verisi alınamadı.")

    return float(price)


def get_usd_try():
    url = "https://open.er-api.com/v6/latest/USD"
    with urlopen(url, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    if data.get("result") != "success":
        raise ValueError("Kur verisi alınamadı.")

    usd_try = data["rates"].get("TRY")
    if usd_try is None:
        raise ValueError("TRY kuru bulunamadı.")

    return float(usd_try)


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
        "Bot hazır.\n\n"
        "Komutlar:\n"
        "/altin -> gram altın TL hesaplar"
    )


async def altin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.update_id in processed_updates:
        return
    processed_updates.add(update.update_id)

    now = time.time()
    last_request_time = context.user_data.get("last_request_time", 0)

    if now - last_request_time < USER_COOLDOWN_SECONDS:
        remaining = int(USER_COOLDOWN_SECONDS - (now - last_request_time)) + 1
        await update.message.reply_text(
            f"Çok hızlı istek gönderiyorsun. Lütfen {remaining} saniye bekle."
        )
        return

    context.user_data["last_request_time"] = now

    try:
        ounce_usd, usd_try, gram_tl = get_cached_prices()

        message = (
            "💰 Dolar Bazında Altın Hesaplama\n\n"
            f"🟡 Ons: {ounce_usd:,.2f} USD\n"
            f"💵 Kur: {usd_try:,.4f}\n"
            f"📊 Gram: {gram_tl:,.2f} TL"
        )

        await update.message.reply_text(message)

    except (HTTPError, URLError):
        await update.message.reply_text(
            "Şu anda veri alınamadı. Biraz sonra tekrar dene."
        )
    except Exception:
        await update.message.reply_text(
            "Bir hata oluştu. Biraz sonra tekrar dene."
        )


async def post_init(app):
    await app.bot.delete_webhook(drop_pending_updates=True)


app = (
    ApplicationBuilder()
    .token(TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("altin", altin))

if __name__ == "__main__":
    print("BOT BASLADI")

    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    app.run_polling(drop_pending_updates=True)
