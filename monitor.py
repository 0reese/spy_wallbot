import vk_api
import time
import requests
import os
import sys
import logging
import json
import socket
from supabase import create_client, Client
from flask import Flask
import threading

# Глобальный таймаут для всех сетевых запросов (30 секунд)
socket.setdefaulttimeout(30)

# ===================== НАСТРОЙКИ (ЗАМЕНИТЕ НА СВОИ) =====================
VK_TOKEN = "vk1.a.L-GUuKoDiF686t_K1PeX_i_huL23RLUZiZzh9PN8MXMZ1Ob-DP9AURCh0LwfOE0yTfOA9IIjEfHNkQqf5l2PG-XvWucAKQu7pPVWgsO6BWVXEzm4SwLktJHseUGV7ywIl95nCqiCsGJB3ODUI-4dh4f-VTCG1cWD0iYA_lkDACRMgG7iv1dYVkrktq-2RMDNKh9-C_YFMPV3hxDfXgztzA"
USER_ID = "185796802"
CHECK_INTERVAL = 60
BOT_TOKEN = "8888651340:AAGBkRtGJAjALGERpkB8aX2aM8pYbcScZRE"
OWNER_ID = 1104584938

SUPABASE_URL = "https://dsbdjnxmhpeforcvqqep.supabase.co"
SUPABASE_KEY = "sb_publishable_RJoQY-6Nbiuq5H4NtwGAbg_YqjxAMYT"
# =======================================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

last_activity = time.time()
forwarded_map = {}

# ---------------- Flask ----------------
app = Flask(__name__)

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/')
def home():
    return "Bot is running", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# ---------------- Watchdog ----------------
def watchdog():
    global last_activity
    while True:
        time.sleep(60)
        idle = time.time() - last_activity
        if idle > 600:
            logging.error(f"Watchdog: нет активности {int(idle)} сек. Перезапуск...")
            os._exit(1)

def touch_activity():
    global last_activity
    last_activity = time.time()

# ---------- Supabase ----------
def get_config(key, default=None):
    try:
        response = supabase.table('config').select('value').eq('key', key).execute()
        if response.data:
            return response.data[0]['value']
        return default
    except Exception as e:
        logging.error(f"Ошибка config[{key}]: {e}")
        return default

def set_config(key, value):
    try:
        supabase.table('config').update({'value': str(value)}).eq('key', key).execute()
        logging.info(f"config[{key}] = {value}")
    except Exception as e:
        logging.error(f"Ошибка сохранения config[{key}]: {e}")

def get_user_id():
    return get_config('user_id', USER_ID)

def get_chats():
    try:
        response = supabase.table('chats').select('*').execute()
        data = response.data
        seen = set()
        unique = []
        for row in data:
            key = (row['chat_id'], row.get('thread_id', 0))
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique
    except Exception as e:
        logging.error(f"Ошибка загрузки чатов: {e}")
        return []

def add_chat(chat_id, thread_id=None):
    if thread_id is None:
        thread_id = 0
    if thread_id != 0:
        supabase.table('chats').delete().eq('chat_id', chat_id).eq('thread_id', 0).execute()
    else:
        supabase.table('chats').delete().eq('chat_id', chat_id).neq('thread_id', 0).execute()
    existing = supabase.table('chats').select('*').eq('chat_id', chat_id).eq('thread_id', thread_id).execute()
    if existing.data:
        return False
    data = {'chat_id': chat_id, 'thread_id': thread_id}
    supabase.table('chats').insert(data).execute()
    logging.info(f"Чат добавлен: {chat_id} (тема: {thread_id})")
    return True

def remove_chat(chat_id, thread_id=None):
    if thread_id is None:
        thread_id = 0
    supabase.table('chats').delete().eq('chat_id', chat_id).eq('thread_id', thread_id).execute()
    logging.info(f"Чат удалён: {chat_id} (тема: {thread_id})")

def get_last_post_id():
    try:
        response = supabase.table('state').select('value').eq('key', 'last_post_id').execute()
        if response.data:
            return int(response.data[0]['value'])
        else:
            supabase.table('state').insert({'key': 'last_post_id', 'value': '0'}).execute()
            return 0
    except Exception as e:
        logging.error(f"Ошибка last_post_id: {e}")
        return 0

def save_last_post_id(post_id):
    try:
        supabase.table('state').update({'value': str(post_id)}).eq('key', 'last_post_id').execute()
        logging.info(f"Сохранён last_post_id: {post_id}")
    except Exception as e:
        logging.error(f"Ошибка сохранения last_post_id: {e}")

# ---------- Режимы ----------
def get_mode(user_id):
    try:
        response = supabase.table('settings').select('mode').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]['mode']
        else:
            supabase.table('settings').insert({'user_id': user_id, 'mode': 'reply'}).execute()
            return 'reply'
    except Exception as e:
        logging.error(f"Ошибка режима: {e}")
        return 'reply'

def set_mode(user_id, mode):
    try:
        supabase.table('settings').update({'mode': mode}).eq('user_id', user_id).execute()
        logging.info(f"Режим {user_id} -> {mode}")
    except Exception as e:
        logging.error(f"Ошибка сохранения режима: {e}")

# ---------- Отправка в Telegram ----------
def send_message_to_chat(chat_id, method, data=None, files=None, thread_id=None, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if thread_id and thread_id != 0:
        if data is None:
            data = {}
        data['message_thread_id'] = thread_id
    if reply_markup:
        if data is None:
            data = {}
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        if files:
            response = requests.post(url, files=files, data=data, timeout=30)
        else:
            response = requests.post(url, data=data, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Ошибка {chat_id} (тема {thread_id}): {response.text}")
            if response.status_code in [403, 404] or (response.status_code == 400 and "TOPIC_CLOSED" in response.text):
                remove_chat(chat_id, thread_id)
            return None
    except Exception as e:
        logging.error(f"Ошибка отправки в {chat_id}: {e}")
        return None

def send_document(chat_id, file_path, caption=None, thread_id=None):
    with open(file_path, 'rb') as f:
        files = {'document': f}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption
        return send_message_to_chat(chat_id, 'sendDocument', data=data, files=files, thread_id=thread_id)

def send_photo(chat_id, file_path, caption=None, thread_id=None):
    with open(file_path, 'rb') as f:
        files = {'photo': f}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption
        return send_message_to_chat(chat_id, 'sendPhoto', data=data, files=files, thread_id=thread_id)

def send_text(chat_id, text, thread_id=None, reply_markup=None):
    data = {'chat_id': chat_id, 'text': text}
    return send_message_to_chat(chat_id, 'sendMessage', data=data, thread_id=thread_id, reply_markup=reply_markup)

def answer_callback(callback_id, text, show_alert=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    data = {'callback_query_id': callback_id, 'text': text, 'show_alert': show_alert}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        logging.error(f"Ошибка callback: {e}")

def edit_message_text(chat_id, message_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    data = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        logging.error(f"Ошибка edit: {e}")

def send_to_all_chats_file(file_path, chats, caption=None, file_type='document'):
    for chat in chats:
        chat_id = chat['chat_id']
        thread_id = chat.get('thread_id', 0)
        if file_type == 'photo':
            send_photo(chat_id, file_path, caption=caption, thread_id=thread_id)
        else:
            send_document(chat_id, file_path, caption=caption, thread_id=thread_id)

def send_text_to_all_chats(text, chats):
    for chat in chats:
        chat_id = chat['chat_id']
        thread_id = chat.get('thread_id', 0)
        send_text(chat_id, text, thread_id)

def download_telegram_file(file_id):
    get_file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    resp = requests.get(get_file_url, timeout=15).json()
    if not resp.get('ok'):
        return None
    file_path = resp['result']['file_path']
    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    local_filename = os.path.basename(file_path)
    r = requests.get(download_url, stream=True, timeout=60)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return local_filename

def forward_owner_message(msg, chats):
    if not chats:
        return
    text = msg.get('text', '')
    if text:
        send_text_to_all_chats(text, chats)
    if 'photo' in msg:
        file_id = msg['photo'][-1]['file_id']
        local_file = download_telegram_file(file_id)
        if local_file:
            send_to_all_chats_file(local_file, chats, caption=text, file_type='photo')
            os.remove(local_file)
    if 'document' in msg:
        file_id = msg['document']['file_id']
        local_file = download_telegram_file(file_id)
        if local_file:
            send_to_all_chats_file(local_file, chats, caption=text, file_type='document')
            os.remove(local_file)
    if 'video' in msg:
        file_id = msg['video']['file_id']
        local_file = download_telegram_file(file_id)
        if local_file:
            send_to_all_chats_file(local_file, chats, caption=text, file_type='document')
            os.remove(local_file)

# ---------- Telegram обновления ----------
def handle_updates(offset):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, params={'offset': offset, 'timeout': 10}, timeout=15)
        if resp.status_code != 200:
            return offset
        data = resp.json()
        if not data.get('ok'):
            return offset
        updates = data.get('result', [])
        if not updates:
            return offset

        new_offset = updates[-1]['update_id'] + 1
        with open('offset.txt', 'w') as f:
            f.write(str(new_offset))

        for upd in updates:
            if 'callback_query' in upd:
                query = upd['callback_query']
                user_id = query['from']['id']
                callback_id = query['id']
                data_cb = query.get('data')
                msg_chat_id = query['message']['chat']['id']
                msg_message_id = query['message']['message_id']

                if user_id != OWNER_ID:
                    answer_callback(callback_id, "Только владелец", show_alert=True)
                    continue

                if data_cb == 'mode_reply':
                    set_mode(user_id, 'reply')
                    answer_callback(callback_id, "Режим: Ответ")
                    edit_message_text(msg_chat_id, msg_message_id, "Режим: Ответ (основной).")
                elif data_cb == 'mode_broadcast':
                    set_mode(user_id, 'broadcast')
                    answer_callback(callback_id, "Режим: Рассылка")
                    edit_message_text(msg_chat_id, msg_message_id, "Режим: Рассылка (дополнительный).")
                elif data_cb == 'show_mode':
                    answer_callback(callback_id, f"Режим: {get_mode(user_id)}", show_alert=True)
                elif data_cb == 'show_page':
                    answer_callback(callback_id, f"Страница: {get_user_id()}", show_alert=True)
                continue

            if 'message' in upd:
                msg = upd['message']
                chat_id = msg['chat']['id']
                text = msg.get('text', '')
                thread_id = msg.get('message_thread_id')
                from_user_id = msg.get('from', {}).get('id')
                reply_to = msg.get('reply_to_message')

                if text == '/start':
                    if add_chat(chat_id, thread_id):
                        send_text(chat_id, 'Бот активирован!', thread_id)
                    else:
                        send_text(chat_id, 'Уже активирован.', thread_id)
                    continue

                if from_user_id == OWNER_ID:
                    if text == '/menu':
                        keyboard = {
                            "inline_keyboard": [
                                [
                                    {"text": "Ответ", "callback_data": "mode_reply"},
                                    {"text": "Рассылка", "callback_data": "mode_broadcast"}
                                ],
                                [
                                    {"text": "Режим", "callback_data": "show_mode"},
                                    {"text": "Страница", "callback_data": "show_page"}
                                ]
                            ]
                        }
                        send_text(chat_id, "Меню:", thread_id, reply_markup=keyboard)
                        continue

                    if text == '/getpage':
                        send_text(chat_id, f"Страница: {get_user_id()}", thread_id)
                        continue

                    if text.startswith('/setpage'):
                        parts = text.split()
                        if len(parts) == 2 and parts[1].lstrip('-').isdigit():
                            new_id = parts[1].strip()
                            set_config('user_id', new_id)
                            save_last_post_id(0)
                            send_text(chat_id, f"Страница {new_id}, last_post_id сброшен.", thread_id)
                        else:
                            send_text(chat_id, "Формат: /setpage <ID>", thread_id)
                        continue

                    current_mode = get_mode(OWNER_ID)

                    if reply_to:
                        original_msg_id = reply_to.get('message_id')
                        if original_msg_id in forwarded_map:
                            original_user = forwarded_map[original_msg_id]
                            if text:
                                send_text(original_user, f"Ответ:\n{text}")
                                send_text(chat_id, f"Отправлено в {original_user}")
                                del forwarded_map[original_msg_id]
                            else:
                                send_text(chat_id, "Пусто")
                        else:
                            send_text(chat_id, "Не могу найти получателя")
                    else:
                        if current_mode == 'broadcast':
                            chats = get_chats()
                            if chats:
                                forward_owner_message(msg, chats)
                                send_text(chat_id, f"Отправлено в {len(chats)} чатов")
                            else:
                                send_text(chat_id, "Нет чатов")
                        else:
                            send_text(chat_id, "Режим Ответ. Используй reply или /menu")
                    continue

                if chat_id == from_user_id:
                    try:
                        forward_url = f"https://api.telegram.org/bot{BOT_TOKEN}/forwardMessage"
                        data = {'chat_id': OWNER_ID, 'from_chat_id': chat_id, 'message_id': msg['message_id']}
                        resp = requests.post(forward_url, data=data, timeout=10)
                        if resp.status_code == 200:
                            fwd = resp.json()['result']
                            forwarded_map[fwd['message_id']] = chat_id
                            logging.info(f"Переслано от {from_user_id}")
                    except Exception as e:
                        logging.error(f"Ошибка пересылки: {e}")

            elif 'channel_post' in upd:
                post = upd['channel_post']
                chat_id = post['chat']['id']
                text = post.get('text', '')
                if text == '/start':
                    if add_chat(chat_id, None):
                        send_text(chat_id, 'Бот активирован!')
                    else:
                        send_text(chat_id, 'Уже активирован.')

        return new_offset
    except Exception as e:
        logging.error(f"Ошибка getUpdates: {e}")
        return offset

def telegram_polling():
    try:
        with open('offset.txt', 'r') as f:
            offset = int(f.read().strip())
    except:
        offset = 0
    logging.info(f"Telegram polling, offset={offset}")
    while True:
        touch_activity()
        try:
            offset = handle_updates(offset)
        except Exception as e:
            logging.error(f"Ошибка в telegram_polling: {e}")
        time.sleep(1)

# ---------- VK ----------
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

def process_attachment(att, post_id, chats, caption):
    att_type = att['type']
    file_path = None
    if att_type == 'photo':
        photo_url = att['photo']['sizes'][-1]['url']
        file_path = f"photo_{post_id}.jpg"
        try:
            img_data = requests.get(photo_url, timeout=30).content
            with open(file_path, 'wb') as f:
                f.write(img_data)
            send_to_all_chats_file(file_path, chats, caption=caption, file_type='photo')
        except Exception as e:
            logging.error(f"Ошибка фото: {e}")
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    elif att_type == 'doc':
        doc = att['doc']
        doc_url = doc.get('url')
        if doc_url:
            file_path = f"doc_{post_id}_{doc['title']}"
            for attempt in range(3):
                try:
                    doc_data = requests.get(doc_url, timeout=60).content
                    with open(file_path, 'wb') as f:
                        f.write(doc_data)
                    send_to_all_chats_file(file_path, chats, caption=caption, file_type='document')
                    break
                except Exception as e:
                    logging.error(f"Попытка {attempt+1}: {e}")
                    if attempt < 2:
                        time.sleep(5)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    elif att_type == 'video':
        video = att['video']
        link = f"https://vk.com/video{video['owner_id']}_{video['id']}"
        text = f"Видео #{post_id}:\n{link}"
        full_text = f"{caption}\n\n{text}" if caption else text
        send_text_to_all_chats(full_text, chats)

# ---------- Main ----------
def main():
    global last_activity

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logging.info("Flask запущен на порту 10000")

    watchdog_thread = threading.Thread(target=watchdog, daemon=True)
    watchdog_thread.start()
    logging.info("Watchdog запущен")

    telegram_thread = threading.Thread(target=telegram_polling, daemon=True)
    telegram_thread.start()
    logging.info("Telegram поток запущен")

    last_post_id = get_last_post_id()
    logging.info(f"Загружен last_post_id: {last_post_id}")

    chats = get_chats()
    logging.info(f"Бот запущен. Чатов: {len(chats)}")

    while True:
        touch_activity()
        logging.info(f"Итерация VK, last_post_id={last_post_id}")
        try:
            current_user_id = get_user_id()
            logging.info(f"Проверяю страницу {current_user_id}")
            response = vk.wall.get(owner_id=current_user_id, count=5, filter='owner')

            if response['items']:
                max_id = max(p['id'] for p in response['items'])
                if last_post_id > max_id:
                    logging.warning(f"last_post_id ({last_post_id}) > макс ({max_id}). Сброс в 0.")
                    last_post_id = 0
                    save_last_post_id(0)

            for post in response['items']:
                post_id = post['id']
                if post_id <= last_post_id:
                    continue
                last_post_id = post_id
                save_last_post_id(last_post_id)
                logging.info(f"Новый пост #{post_id}")

                post_text = post.get('text', '')
                caption = post_text[:1024] if post_text else None
                full_text = post_text if post_text else None

                if 'attachments' in post:
                    for att in post['attachments']:
                        process_attachment(att, post_id, chats, caption)
                    if full_text and len(full_text) > 1024:
                        send_text_to_all_chats(f"Полный текст:\n{full_text}", chats)
                else:
                    if full_text:
                        send_text_to_all_chats(f"Пост #{post_id}:\n{full_text}", chats)

                chats = get_chats()

        except Exception as e:
            if "Flood control" in str(e):
                logging.warning("Flood control. Пауза 5 минут.")
                time.sleep(300)
            else:
                logging.error(f"Ошибка VK: {e}")
                time.sleep(5)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()