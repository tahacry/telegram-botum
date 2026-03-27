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
    "last_update": 0,
}

last_good_usd_try = None


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
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_ounce_gold_usd():
    data = fetch_json("https://api.gold-api.com/price/XAU")
    price = data.get("price")

    if price is None:
        raise ValueError(f"Ons verisi alinamadi: {data}")

    return float(price)


def get_usd_try_from_erapi():
    data = fetch_json("https://open.er-api.com/v6/latest/USD")

    if data.get("result") != "success":
        raise ValueError(f"ER API hatasi: {data}")

    rate = data.get("rates", {}).get("TRY")
    if rate is None:
        raise ValueError(f"ER API TRY kuru alinamadi: {data}")

    return float(rate)


def get_usd_try_from_frankfurter():
    data = fetch_json("https://api.frankfurter.dev/v2/rate/USD/TRY")

    rate = data.get("rate")
    if rate is None:
        raise ValueError(f"Frankfurter TRY kuru alinamadi: {data}")

    return float(rate)


def is_rate_reasonable(rate: float) -> bool:
    return 10.0 < rate < 100.0


def choose_best_rate(rates: list[float]) -> float:
    global last_good_usd_try

    valid_rates = [r for r in rates if is_rate_reasonable(r)]
    if not valid_rates:
        if last_good_usd_try is not None:
            return last_good_usd_try
        raise ValueError("Gecerli kur verisi bulunamadi")

    if len(valid_rates) == 1:
        chosen = valid_rates[0]
        last_good_usd_try = chosen
        return chosen

    r1, r2 = valid_rates[0], valid_rates[1]
    diff_ratio = abs(r1 - r2) / ((r1 + r2) / 2)

    # Fark %1'den küçükse ortalama al
    if diff_ratio < 0.01:
        chosen = (r1 + r2) / 2
        last_good_usd_try = chosen
        return chosen

    # Son iyi veriye yakın olanı seç
    if last_good_usd_try is not None:
        chosen = min(valid_rates, key=lambda r: abs(r - last_good_usd_try))
        last_good_usd_try = chosen
        return chosen

    # Son iyi veri yoksa ortanca mantığı
    chosen = sorted(valid_rates)[len(valid_rates) // 2]
    last_good_usd_try = chosen
    return chosen


def get_usd_try():
    rates = []

    try:
        rates.append(get_usd_try_from_erapi())
    except Exception as e:
        print(f"ER API HATASI: {e}")

    try:
        rates.append(get_usd_try_from_frankfurter())
    except Exception as e:
        print(f"FRANKFURTER HATASI: {e}")

    return choose_best_rate(rates)


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
            f"Cok hizli istek gonderiyorsun. Lutfen {remaining} saniye bekle."
        )
        return

    context.user_data["last_request_time"] = now

    try:
        ounce_usd, usd_try, gram_tl = get_cached_prices()

        message = (
            "💰 Dolar Bazinda Altin Hesaplama\n\n"
            f"🟡 Ons: {ounce_usd:,.2f} USD\n"
            f"💵 Kur: {usd_try:,.4f}\n"
            f"📊 Gram: {gram_tl:,.2f} TL"
        )

        await update.message.reply_text(message)

    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")


async def post_init(app):
    await app.bot.delete_webhook(drop_pending_updates=True)


def main():
    print("BOT BASLADI - MIX SURUM")

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
