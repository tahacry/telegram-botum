import os
import json
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")

processed_updates = set()


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.update_id in processed_updates:
        return
    processed_updates.add(update.update_id)

    await update.message.reply_text("Bot hazır. /altin yaz.")


async def altin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.update_id in processed_updates:
        return
    processed_updates.add(update.update_id)

    try:
        ounce_usd = get_ounce_gold_usd()
        usd_try = get_usd_try()
        gram_tl = calculate_gram_gold_tl(ounce_usd, usd_try)

        message = (
            "💰 Dolar Bazında Altın Hesaplama\n\n"
            f"🟡 Ons: {ounce_usd:,.2f} USD\n"
            f"💵 Kur: {usd_try:,.4f}\n"
            f"📊 Gram: {gram_tl:,.2f} TL"
        )

        await update.message.reply_text(message)

    except (HTTPError, URLError):
        await update.message.reply_text("Veri kaynaklarına bağlanamadım.")
    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")


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
