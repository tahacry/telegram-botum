import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen, Request

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", "8080"))

FOOTER_TEXT = os.getenv("FOOTER_TEXT", "")

CACHE_SECONDS = 120
USER_COOLDOWN_SECONDS = 6

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


# 🟡 Ons
def get_ounce_gold_usd():
    data = fetch_json("https://api.gold-api.com/price/XAU")
    return float(data["price"])


# 💵 Kur kaynak 1
def get_usd_try_from_erapi():
    data = fetch_json("https://open.er-api.com/v6/latest/USD")
    return float(data["rates"]["TRY"])


# 💵 Kur kaynak 2
def get_usd_try_from_frankfurter():
    data = fetch_json("https://api.frankfurter.dev/v2/rate/USD/TRY")
    return float(data["rate"])


def is_rate_reasonable(rate: float):
    return 10 < rate < 100


def choose_best_rate(rates):
    global last_good_usd_try

    valid = [r for r in rates if is_rate_reasonable(r)]

    if not valid:
        if last_good_usd_try:
            return last_good_usd_try
        raise ValueError("Kur bulunamadi")

    if len(valid) == 1:
        last_good_usd_try = valid[0]
        return valid[0]

    r1, r2 = valid[0], valid[1]
    diff = abs(r1 - r2) / ((r1 + r2) / 2)

    if diff < 0.01:
        chosen = (r1 + r2) / 2
    elif last_good_usd_try:
        chosen = min(valid, key=lambda r: abs(r - last_good_usd_try))
    else:
        chosen = sorted(valid)[1]

    last_good_usd_try = chosen
    return chosen


def get_usd_try():
    rates = []

    try:
        rates.append(get_usd_try_from_erapi())
    except Exception as e:
        print("ER API hata:", e)

    try:
        rates.append(get_usd_try_from_frankfurter())
    except Exception as e:
        print("Frankfurter hata:", e)

    return choose_best_rate(rates)


def calculate_gram_gold_tl(ounce_usd, usd_try):
    return (ounce_usd * usd_try) / 31.1034768


def calculate_other_gold_prices(gram):
    return {
        "ceyrek": gram * 1.754,
        "yarim": gram * 3.508,
        "tam": gram * 7.016,
        "ayar22": gram * (22 / 24),
    }


def get_cached_prices():
    now = time.time()

    if (
        price_cache["gram_tl"] is not None
        and now - price_cache["last_update"] < CACHE_SECONDS
    ):
        return (
            price_cache["ounce_usd"],
            price_cache["usd_try"],
            price_cache["gram_tl"],
        )

    ounce = get_ounce_gold_usd()
    usd_try = get_usd_try()
    gram = calculate_gram_gold_tl(ounce, usd_try)

    price_cache.update({
        "ounce_usd": ounce,
        "usd_try": usd_try,
        "gram_tl": gram,
        "last_update": now
    })

    return ounce, usd_try, gram


# 🔥 START KOMUTU (senin istediğin gibi)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Aşağıdaki komutlardan birini giriniz ya da tıklayınız:\n\n"
        "/altin"
    )


async def altin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last = context.user_data.get("last", 0)

    if now - last < USER_COOLDOWN_SECONDS:
        await update.message.reply_text("Lütfen biraz bekle.")
        return

    context.user_data["last"] = now

    try:
        ounce, usd, gram = get_cached_prices()
        extra = calculate_other_gold_prices(gram)

        message = (
            "💰 Altin Hesaplama\n\n"
            f"🟡 Ons: {ounce:,.2f} USD\n"
            f"💵 Kur: {usd:,.4f}\n\n"
            f"📊 Gram Altin: {gram:,.2f} TL\n"
            f"🪙 Ceyrek Altin: {extra['ceyrek']:,.2f} TL\n"
            f"🪙 Yarim Altin: {extra['yarim']:,.2f} TL\n"
            f"🪙 Tam Altin: {extra['tam']:,.2f} TL\n"
            f"🟠 22 Ayar Gram: {extra['ayar22']:,.2f} TL\n\n"
            + (FOOTER_TEXT if FOOTER_TEXT else "")
        )

        await update.message.reply_text(message)

    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")


async def post_init(app):
    await app.bot.delete_webhook(drop_pending_updates=True)


def main():
    print("BOT BASLADI - FINAL")

    threading.Thread(target=run_web_server, daemon=True).start()

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
