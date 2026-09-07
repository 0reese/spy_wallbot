import vk_api
import time
import requests
import os
import logging
import json

# ===== НАСТРОЙКИ =====
VK_TOKEN = "vk1.a.SSAhcoSsS1CwjV5UcyjFIsyiwYMuQMtihAuAkpkxeg_CAnzXur0bDeArjJHMD9RSsMZqkENVrRdyf-2mvfuUFLYG5BoIGTGlKORCCMRk8mluRHiUJuraYkEDhhmZ7-6uVv5ZsdvUfZSuT2fyOssFyHfHBT7-N_NxH5r_vWFwx3fk-3JDV6XlpmqCRCQpwfTxoHNyX-xrRmhF_btGcutcgA"                # Замените на ваш токен
USER_ID = "1128567349"                   # ID страницы, которую мониторим
CHECK_INTERVAL = 60                      # Интервал между проверками (сек)

BOT_TOKEN = "8888651340:AAGBkRtGJAjALGERpkB8aX2aM8pYbcScZRE"    # Замените на токен бота
# ======================

# --- Файл для хранения списка чатов ---
CHATS_FILE = "chats.txt"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_chats():
    """Загружает список chat_id из файла"""
    try:
        with open(CHATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_chats(chats):
    """Сохраняет список chat_id в файл"""
    with open(CHATS_FILE, 'w') as f:
        json.dump(chats, f)

def add_chat_if_new(chat_id, chats):
    """Добавляет новый chat_id в список, если его там нет"""
    if chat_id not in chats:
        chats.append(chat_id)
        save_chats(chats)
        logging.info(f"➕ Добавлен новый чат: {chat_id}")

def remove_chat(chat_id, chats):
    """Удаляет chat_id из списка (если бот исключён)"""
    if chat_id in chats:
        chats.remove(chat_id)
        save_chats(chats)
        logging.info(f"➖ Удалён чат: {chat_id}")

# --- Подключение к VK ---
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
last_post_id = 0

# --- Функции для отправки в Telegram ---
def send_to_telegram(file_path, chat_id):
    """Отправляет файл в конкретный чат"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': chat_id}
            response = requests.post(url, files=files, data=data, timeout=30)
            if response.status_code == 200:
                logging.info(f"✅ Отправлено в {chat_id}: {os.path.basename(file_path)}")
                return True
            else:
                logging.error(f"❌ Ошибка в {chat_id}: {response.text}")
                # Если ошибка 403 (бот заблокирован) или 404 (чат не найден) — удаляем чат
                if response.status_code in [403, 404]:
                    return False
                return True
    except Exception as e:
        logging.error(f"❌ Ошибка отправки в {chat_id}: {e}")
        return False

def send_to_all_chats(file_path, chats):
    """Отправляет файл во все сохранённые чаты"""
    for chat_id in chats.copy():  # копируем, чтобы можно было удалять во время итерации
        success = send_to_telegram(file_path, chat_id)
        if not success:
            remove_chat(chat_id, chats)

# --- Обработка новых чатов ---
def fetch_new_chats(offset):
    """Получает новые обновления из Telegram и добавляет новые чаты"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url, params={'offset': offset, 'timeout': 10}, timeout=15)
        if response.status_code != 200:
            return offset

        updates = response.json().get('result', [])
        if not updates:
            return offset

        chats = load_chats()
        new_offset = updates[-1]['update_id'] + 1

        for update in updates:
            # Сообщение о добавлении бота в группу/канал
            if 'message' in update:
                msg = update['message']
                # Если бота добавили в группу
                if 'new_chat_members' in msg:
                    for member in msg['new_chat_members']:
                        if member.get('username') == 'spy_wallbot':  # замените на имя вашего бота
                            chat_id = msg['chat']['id']
                            add_chat_if_new(chat_id, chats)
                # Если бота добавили в канал (обычно через администратора, тогда приходит сообщение типа channel_post)
            elif 'channel_post' in update:
                # Для каналов: бот получает сообщения, когда его добавляют админом.
                # В этом случае можно считать любой канал, откуда пришло сообщение, как доверенный.
                chat_id = update['channel_post']['chat']['id']
                add_chat_if_new(chat_id, chats)

        return new_offset
    except Exception as e:
        logging.error(f"Ошибка получения обновлений: {e}")
        return offset

# --- Обработка вложений VK ---
def process_attachment(att, post_id, chats):
    att_type = att['type']
    file_path = None

    if att_type == 'photo':
        photo_url = att['photo']['sizes'][-1]['url']
        file_path = f"photo_{post_id}.jpg"
        try:
            img_data = requests.get(photo_url, timeout=30).content
            with open(file_path, 'wb') as f:
                f.write(img_data)
            send_to_all_chats(file_path, chats)
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
                    send_to_all_chats(file_path, chats)
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
        # Отправляем текстовое сообщение во все чаты
        for chat_id in chats:
            try:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                              data={'chat_id': chat_id, 'text': text}, timeout=30)
                logging.info(f"📹 Ссылка отправлена в {chat_id}")
            except Exception as e:
                logging.error(f"Ошибка отправки ссылки в {chat_id}: {e}")

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    global last_post_id
    offset = 0  # для getUpdates
    chats = load_chats()
    logging.info(f"🚀 Бот запущен. Чатов в списке: {len(chats)}")

    while True:
        # 1. Проверяем новые чаты
        offset = fetch_new_chats(offset)
        # обновляем список чатов (на случай, если добавились новые)
        chats = load_chats()

        # 2. Проверяем новые посты ВК
        try:
            response = vk.wall.get(owner_id=USER_ID, count=5, filter='owner')
            for post in response['items']:
                post_id = post['id']
                if post_id <= last_post_id:
                    continue

                last_post_id = post_id
                logging.info(f"📝 Новый пост #{post_id}")

                if 'attachments' in post:
                    for att in post['attachments']:
                        process_attachment(att, post_id, chats)
                else:
                    # Если нет вложений, можно отправить текст поста во все чаты
                    if post.get('text'):
                        text = f"📄 Новый пост #{post_id}:\n{post['text'][:200]}"
                        for chat_id in chats:
                            try:
                                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                              data={'chat_id': chat_id, 'text': text}, timeout=30)
                            except Exception as e:
                                logging.error(f"Ошибка отправки текста в {chat_id}: {e}")

        except Exception as e:
            logging.error(f"Ошибка VK: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
