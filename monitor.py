import vk_api
import time
import requests
import os
import logging
import json
from supabase import create_client, Client

# ===== НАСТРОЙКИ =====
VK_TOKEN = "vk1.a.SSAhcoSsS1CwjV5UcyjFIsyiwYMuQMtihAuAkpkxeg_CAnzXur0bDeArjJHMD9RSsMZqkENVrRdyf-2mvfuUFLYG5BoIGTGlKORCCMRk8mluRHiUJuraYkEDhhmZ7-6uVv5ZsdvUfZSuT2fyOssFyHfHBT7-N_NxH5r_vWFwx3fk-3JDV6XlpmqCRCQpwfTxoHNyX-xrRmhF_btGcutcgA"
USER_ID = "1128567349"
CHECK_INTERVAL = 30
BOT_TOKEN = "8888651340:AAGBkRtGJAjALGERpkB8aX2aM8pYbcScZRE"

# ==== Настройки Supabase (замените на свои) ====
SUPABASE_URL = "https://dsbdjnxmhpeforcvqqep.supabase.co"   # ваш Project URL
SUPABASE_KEY = "sb_publishable_RJoQY-6Nbiuq5H4NtwGAbg_YqjxAMYT"                             # ваш anon public ключ
# ===============================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Функции работы с БД ---
def get_chats():
    try:
        response = supabase.table('chats').select('*').execute()
        return response.data
    except Exception as e:
        logging.error(f"Ошибка загрузки чатов: {e}")
        return []

def add_chat(chat_id, thread_id=None):
    # Если thread_id не передан, используем 0 для общего чата
    if thread_id is None:
        thread_id = 0
    # Проверяем, существует ли уже такая пара
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
    query = supabase.table('chats').delete() \
        .eq('chat_id', chat_id).eq('thread_id', thread_id)
    result = query.execute()
    if result.data:
        logging.info(f"➖ Чат удалён: {chat_id} (тема: {thread_id if thread_id != 0 else 'общий'})")

# --- Отправка сообщений ---
def send_message_to_chat(chat_id, method, data=None, files=None, thread_id=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    # Если thread_id = 0 или None, не передаём параметр
    if thread_id and thread_id != 0:
        if data is None:
            data = {}
        data['message_thread_id'] = thread_id
    try:
        if files:
            response = requests.post(url, files=files, data=data, timeout=30)
        else:
            response = requests.post(url, data=data, timeout=30)
        if response.status_code == 200:
            return True
        else:
            logging.error(f"❌ Ошибка в {chat_id} (тема {thread_id}): {response.text}")
            if response.status_code in [403, 404] or (response.status_code == 400 and "TOPIC_CLOSED" in response.text):
                remove_chat(chat_id, thread_id)
            return False
    except Exception as e:
        logging.error(f"❌ Ошибка отправки в {chat_id} (тема {thread_id}): {e}")
        return False

def send_document(chat_id, file_path, caption=None, thread_id=None):
    with open(file_path, 'rb') as f:
        files = {'document': f}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption
        return send_message_to_chat(chat_id, 'sendDocument', data=data, files=files, thread_id=thread_id)

def send_text(chat_id, text, thread_id=None):
    data = {'chat_id': chat_id, 'text': text}
    return send_message_to_chat(chat_id, 'sendMessage', data=data, thread_id=thread_id)

def send_to_all_chats(file_path, chats, caption=None, sent_files=None):
    if sent_files is None:
        sent_files = set()
    if file_path in sent_files:
        return
    sent_files.add(file_path)
    for chat in chats:
        chat_id = chat['chat_id']
        thread_id = chat.get('thread_id', 0)
        send_document(chat_id, file_path, caption=caption, thread_id=thread_id)

def send_text_to_all_chats(text, chats):
    for chat in chats:
        chat_id = chat['chat_id']
        thread_id = chat.get('thread_id', 0)
        send_text(chat_id, text, thread_id)

# --- Обработка обновлений Telegram ---
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
        for upd in updates:
            if 'message' in upd:
                msg = upd['message']
                chat_id = msg['chat']['id']
                text = msg.get('text', '')
                thread_id = msg.get('message_thread_id')
                if text == '/start':
                    if add_chat(chat_id, thread_id):
                        send_text(chat_id, '✅ Бот активирован! Теперь сюда будут приходить посты.', thread_id)
                    else:
                        logging.info(f"ℹ️ Чат {chat_id} уже активирован, повторный /start игнорируется")
            elif 'channel_post' in upd:
                post = upd['channel_post']
                chat_id = post['chat']['id']
                text = post.get('text', '')
                if text == '/start':
                    if add_chat(chat_id, None):
                        send_text(chat_id, '✅ Бот активирован! Теперь сюда будут приходить посты.')
                    else:
                        logging.info(f"ℹ️ Канал {chat_id} уже активирован, повторный /start игнорируется")
        with open('offset.txt', 'w') as f:
            f.write(str(new_offset))
        return new_offset
    except Exception as e:
        logging.error(f"Ошибка получения обновлений: {e}")
        return offset

# --- VK и обработка постов ---
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
last_post_id = 0

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
            send_to_all_chats(file_path, chats, caption=caption, sent_files=sent_files)
        except Exception as e:
            logging.error(f"Ошибка фото: {e}")
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
                    send_to_all_chats(file_path, chats, caption=caption, sent_files=sent_files)
                    break
                except Exception as e:
                    logging.error(f"Попытка {attempt+1} не удалась: {e}")
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        logging.error(f"Не удалось скачать документ")
    elif att_type == 'video':
        video = att['video']
        link = f"https://vk.com/video{video['owner_id']}_{video['id']}"
        text = f"🎬 Видео в посте #{post_id}:\n{link}"
        full_text = f"{caption}\n\n{text}" if caption else text
        send_text_to_all_chats(full_text, chats)

def main():
    global last_post_id
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
            logging.error(f"Ошибка VK: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
