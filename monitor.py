import vk_api
import time
import requests
import os
import logging
import json
from supabase import create_client, Client
from flask import Flask
import threading

# ===================== НАСТРОЙКИ =====================
VK_TOKEN = "vk1.a._7jyp-62jkBPJK5uS0TEZYgoEDKOVwd9ggjIw914efvyOCrExoOmpn6bLLWGcyQtvfCB14a4A-eQ5MPerELhBMGnwBTGml1DznhG5DPVZ1N0Hv_7r12oysJRu7c3mD5RzX6kRjN_G7jP9vFVXthaQfX0prB6GqSjsEqktXZFAWWjtxRr9N05AVpRHnqiyQtck55zPKrrIQihoHw0DyIIvQ"           # замените
USER_ID = "185796802"                        # ID страницы ВК
CHECK_INTERVAL = 60
BOT_TOKEN = "8888651340:AAGBkRtGJAjALGERpkB8aX2aM8pYbcScZRE"         # замените
OWNER_ID = 1104584938                         # ваш Telegram ID

SUPABASE_URL = "https://dsbdjnxmhpeforcvqqep.supabase.co"   # замените
SUPABASE_KEY = "sb_publishable_91prjgAzTv4doAATEm2ehg_8b2fW_lx"          # замените
# ====================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------- Flask для пингов ----------------
app = Flask(__name__)

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/')
def home():
    return "Bot is running", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# ---------- Работа с Supabase ----------
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
    existing = supabase.table('chats').select('*') \
        .eq('chat_id', chat_id).eq('thread_id', thread_id).execute()
    if existing.data:
        return False
    data = {'chat_id': chat_id, 'thread_id': thread_id}
    supabase.table('chats').insert(data).execute()
    logging.info(f"➕ Чат добавлен: {chat_id} (тема: {thread_id if thread_id != 0 else 'общий'})")
    return True

def remove_chat(chat_id, thread_id=None):
    if thread_id is None:
        thread_id = 0
    supabase.table('chats').delete() \
        .eq('chat_id', chat_id).eq('thread_id', thread_id).execute()
    logging.info(f"➖ Чат удалён: {chat_id} (тема: {thread_id if thread_id != 0 else 'общий'})")

def get_last_post_id():
    try:
        response = supabase.table('state').select('value').eq('key', 'last_post_id').execute()
        if response.data:
            return int(response.data[0]['value'])
        else:
            supabase.table('state').insert({'key': 'last_post_id', 'value': '0'}).execute()
            return 0
    except Exception as e:
        logging.error(f"Ошибка загрузки last_post_id: {e}")
        return 0

def save_last_post_id(post_id):
    try:
        supabase.table('state').update({'value': str(post_id)}).eq('key', 'last_post_id').execute()
        logging.info(f"💾 Сохранён last_post_id: {post_id}")
    except Exception as e:
        logging.error(f"Ошибка сохранения last_post_id: {e}")

# ---------- Функции для режимов (меню) ----------
def get_mode(user_id):
    try:
        response = supabase.table('settings').select('mode').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]['mode']
        else:
            supabase.table('settings').insert({'user_id': user_id, 'mode': 'reply'}).execute()
            return 'reply'
    except Exception as e:
        logging.error(f"Ошибка получения режима: {e}")
        return 'reply'

def set_mode(user_id, mode):
    try:
        supabase.table('settings').update({'mode': mode}).eq('user_id', user_id).execute()
        logging.info(f"🔄 Режим для {user_id} изменён на {mode}")
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
            logging.error(f"❌ Ошибка в {chat_id} (тема {thread_id}): {response.text}")
            if response.status_code in [403, 404] or (response.status_code == 400 and "TOPIC_CLOSED" in response.text):
                remove_chat(chat_id, thread_id)
            return None
    except Exception as e:
        logging.error(f"❌ Ошибка отправки в {chat_id} (тема {thread_id}): {e}")
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
        logging.error(f"Ошибка ответа на callback: {e}")

def edit_message_text(chat_id, message_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    data = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        logging.error(f"Ошибка редактирования сообщения: {e}")

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

# ---------- Скачивание файлов из Telegram ----------
def download_telegram_file(file_id):
    get_file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    resp = requests.get(get_file_url).json()
    if not resp.get('ok'):
        return None
    file_path = resp['result']['file_path']
    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    local_filename = os.path.basename(file_path)
    r = requests.get(download_url, stream=True)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return local_filename

# ---------- Пересылка сообщений от владельца ----------
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

# ---------- Обработка обновлений Telegram ----------
forwarded_map = {}

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
        logging.info(f"📩 Получено обновлений: {len(updates)}")
        for upd in updates:
            logging.info(f"Обновление: {upd}")
        if not updates:
            return offset
        new_offset = updates[-1]['update_id'] + 1

        for upd in updates:
            # Обработка нажатий на кнопки
            if 'callback_query' in upd:
                query = upd['callback_query']
                user_id = query['from']['id']
                callback_id = query['id']
                data_cb = query.get('data')
                msg_chat_id = query['message']['chat']['id']
                msg_message_id = query['message']['message_id']

                if user_id != OWNER_ID:
                    answer_callback(callback_id, "❌ Только владелец может менять режим", show_alert=True)
                    continue

                if data_cb == 'mode_reply':
                    set_mode(user_id, 'reply')
                    answer_callback(callback_id, "✅ Режим изменён на 'Ответ'")
                    edit_message_text(msg_chat_id, msg_message_id,
                                     "✅ Режим: **Ответ** (основной).\nТеперь вы отвечаете пользователям через reply на пересланные сообщения. Новые сообщения без reply игнорируются.")
                elif data_cb == 'mode_broadcast':
                    set_mode(user_id, 'broadcast')
                    answer_callback(callback_id, "✅ Режим изменён на 'Рассылка'")
                    edit_message_text(msg_chat_id, msg_message_id,
                                     "✅ Режим: **Рассылка** (дополнительный).\nЛюбое ваше сообщение (не в ответ на пересланное) будет отправлено во все чаты.")
                elif data_cb == 'show_mode':
                    current_mode = get_mode(user_id)
                    answer_callback(callback_id, f"Текущий режим: {current_mode}", show_alert=True)
                continue

            # Обработка сообщений
            if 'message' in upd:
                msg = upd['message']
                chat_id = msg['chat']['id']
                text = msg.get('text', '')
                thread_id = msg.get('message_thread_id')
                from_user_id = msg.get('from', {}).get('id')
                reply_to = msg.get('reply_to_message')

                # Команда /start
                if text == '/start':
    if add_chat(chat_id, thread_id):
        send_text(chat_id, '✅ Бот активирован! Теперь сюда будут приходить посты.', thread_id)
    else:
        send_text(chat_id, 'ℹ️ Бот уже активирован в этом чате.', thread_id)
        logging.info(f"ℹ️ Чат {chat_id} уже активирован")
    continue

                # Команда /menu (только для владельца)
                if from_user_id == OWNER_ID and text == '/menu':
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "📝 Режим: Ответ", "callback_data": "mode_reply"},
                                {"text": "📢 Режим: Рассылка", "callback_data": "mode_broadcast"}
                            ],
                            [
                                {"text": "ℹ️ Текущий режим", "callback_data": "show_mode"}
                            ]
                        ]
                    }
                    send_text(chat_id, "Выберите режим работы бота:", thread_id, reply_markup=keyboard)
                    continue

                # --- Сообщения от владельца ---
                if from_user_id == OWNER_ID:
                    current_mode = get_mode(OWNER_ID)

                    # Если владелец отвечает на пересланное сообщение
                    if reply_to:
                        original_msg_id = reply_to.get('message_id')
                        if original_msg_id in forwarded_map:
                            original_user = forwarded_map[original_msg_id]
                            if text:
                                send_text(original_user, f"Ответ от владельца:\n{text}")
                                send_text(chat_id, f"✅ Ответ отправлен пользователю {original_user}")
                                del forwarded_map[original_msg_id]
                            else:
                                send_text(chat_id, "❌ Пустое сообщение не отправлено")
                        else:
                            send_text(chat_id, "❌ Не могу найти, кому ответить (возможно, сообщение не было переслано мной)")
                    else:
                        # Не reply — либо рассылка, либо игнор
                        if current_mode == 'broadcast':
                            chats = get_chats()
                            if chats:
                                forward_owner_message(msg, chats)
                                send_text(chat_id, f"✅ Сообщение отправлено в {len(chats)} чатов")
                            else:
                                send_text(chat_id, "❌ Нет активных чатов для рассылки")
                        else:
                            # Режим ответа, но без reply — напоминаем
                            send_text(chat_id, "ℹ️ Вы в режиме ответа. Чтобы ответить пользователю, используйте reply на пересланное сообщение. Для рассылки переключитесь в режим рассылки через /menu.")
                    continue

                # --- Сообщение от другого пользователя (не владельца) в личку бота ---
                if chat_id == from_user_id:
                    try:
                        forward_url = f"https://api.telegram.org/bot{BOT_TOKEN}/forwardMessage"
                        data = {
                            'chat_id': OWNER_ID,
                            'from_chat_id': chat_id,
                            'message_id': msg['message_id']
                        }
                        resp = requests.post(forward_url, data=data, timeout=10)
                        if resp.status_code == 200:
                            forwarded_data = resp.json()
                            forwarded_msg_id = forwarded_data['result']['message_id']
                            forwarded_map[forwarded_msg_id] = chat_id
                            logging.info(f"📩 Переслано сообщение от {from_user_id} владельцу (forward_id={forwarded_msg_id})")
                        else:
                            logging.error(f"Ошибка пересылки: {resp.text}")
                    except Exception as e:
                        logging.error(f"Ошибка пересылки: {e}")

                # Сообщения из групп/каналов от других пользователей — игнорируем
                else:
                    logging.info(f"Сообщение из чата {chat_id} от {from_user_id} игнорировано (не личка)")

            elif 'channel_post' in upd:
                post = upd['channel_post']
                chat_id = post['chat']['id']
                text = post.get('text', '')
                if text == '/start':
                    if add_chat(chat_id, None):
                        send_text(chat_id, '✅ Бот активирован! Теперь сюда будут приходить посты.')
                    else:
                        logging.info(f"ℹ️ Канал {chat_id} уже активирован")

        with open('offset.txt', 'w') as f:
            f.write(str(new_offset))
        return new_offset
    except Exception as e:
        logging.error(f"Ошибка получения обновлений: {e}")
        return offset

# ---------- VK и обработка постов ----------
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

def process_attachment(att, post_id, chats, caption, sent_files):
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
                    logging.error(f"Попытка {attempt+1} не удалась: {e}")
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        logging.error(f"Не удалось скачать документ")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    elif att_type == 'video':
        video = att['video']
        link = f"https://vk.com/video{video['owner_id']}_{video['id']}"
        text = f"🎬 Видео в посте #{post_id}:\n{link}"
        full_text = f"{caption}\n\n{text}" if caption else text
        send_text_to_all_chats(full_text, chats)

# ---------- Основной цикл ----------
def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logging.info("🌐 Flask-сервер запущен на порту 10000")

    last_post_id = get_last_post_id()
    logging.info(f"📌 Загружен last_post_id: {last_post_id}")

    try:
        with open('offset.txt', 'r') as f:
            offset = int(f.read().strip())
    except:
        offset = 0

    chats = get_chats()
    logging.info(f"🚀 Бот запущен. Чатов в списке: {len(chats)}")
    logging.info(f"📌 Текущий offset: {offset}")

    while True:
        offset = handle_updates(offset)
        chats = get_chats()
        sent_files = set()

        try:
            response = vk.wall.get(owner_id=USER_ID, count=5, filter='owner')
            for post in response['items']:
                post_id = post['id']
                if post_id <= last_post_id:
                    continue
                last_post_id = post_id
                save_last_post_id(last_post_id)
                logging.info(f"📝 Новый пост #{post_id}")

                post_text = post.get('text', '')
                caption = post_text[:1024] if post_text else None
                full_text = post_text if post_text else None

                if 'attachments' in post:
                    for att in post['attachments']:
                        process_attachment(att, post_id, chats, caption, sent_files)
                    if full_text and len(full_text) > 1024:
                        send_text_to_all_chats(f"📄 Полный текст поста:\n{full_text}", chats)
                else:
                    if full_text:
                        send_text_to_all_chats(f"📄 Новый пост #{post_id}:\n{full_text}", chats)

        except Exception as e:
            if "Flood control" in str(e):
                logging.warning("⚠️ VK ограничил частоту запросов. Пауза 5 минут.")
                time.sleep(300)
            else:
                logging.error(f"Ошибка VK: {e}")
                time.sleep(5)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()