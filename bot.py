import os
import json
import time
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")

processed_updates = set()

CACHE_SECONDS = 15
USER_COOLDOWN_SECONDS = 6

price_cache = {
    "ounce_usd": None,
    "usd_try": None,
    "gram_tl": None,
    "last_update": 0
}

user_last_request = {}


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


def is_user_on_cooldown(user_id):
    now = time.time()
    last_time = user_last_request.get(user_id)

    if last_time is None:
        return False, 0

    passed = now - last_time
    if passed < USER_COOLDOWN_SECONDS:
        remaining = USER_COOLDOWN_SECONDS - passed
        return True, int(remaining) + 1

    return False, 0


def update_user_request_time(user_id):
    user_last_request[user_id] = time.time()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.update_id in processed_updates:
        return
    processed_updates.add(update.update_id)

    await update.message.reply_text(
        "Bot hazır.\n\n"
        "Komutlar:\n"
        "/altin -> gram altın TL hesaplar"
    )


async def altin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.update_id in processed_updates:
        return
    processed_updates.add(update.update_id)

    user = update.effective_user
    if user is None:
        return

    user_id = user.id
    on_cooldown, remaining = is_user_on_cooldown(user_id)

    if on_cooldown:
        await update.message.reply_text(
            f"Çok hızlı istek gönderiyorsun. Lütfen {remaining} saniye bekle."
        )
        return

    update_user_request_time(user_id)

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
    app.run_polling(drop_pending_updates=True)
