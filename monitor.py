import vk_api
import time
import requests
import os
import logging

# ===== НАСТРОЙКИ (УЖЕ ЗАПОЛНЕНЫ) =====
VK_TOKEN = "vk1.a.SSAhcoSsS1CwjV5UcyjFIsyiwYMuQMtihAuAkpkxeg_CAnzXur0bDeArjJHMD9RSsMZqkENVrRdyf-2mvfuUFLYG5BoIGTGlKORCCMRk8mluRHiUJuraYkEDhhmZ7-6uVv5ZsdvUfZSuT2fyOssFyHfHBT7-N_NxH5r_vWFwx3fk-3JDV6XlpmqCRCQpwfTxoHNyX-xrRmhF_btGcutcgA"
USER_ID = "1128567349"
CHECK_INTERVAL = 60

BOT_TOKEN = "8888651340:AAGBkRtGJAjALGERpkB8aX2aM8pYbcScZRE"
CHAT_ID = "-1003968224550"
# =====================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

STATE_FILE = "state.txt"

def load_last_post_id():
    try:
        with open(STATE_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return 0

def save_last_post_id(post_id):
    with open(STATE_FILE, 'w') as f:
        f.write(str(post_id))

last_post_id = load_last_post_id()

def send_to_telegram(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': CHAT_ID}
            response = requests.post(url, files=files, data=data, timeout=60)
            if response.status_code == 200:
                logging.info(f"✅ Отправлено: {os.path.basename(file_path)}")
            else:
                logging.error(f"❌ Ошибка отправки: {response.text}")
        os.remove(file_path)
    except Exception as e:
        logging.error(f"❌ Ошибка отправки: {e}")

def process_attachment(att, post_id):
    att_type = att['type']
    file_path = None

    if att_type == 'photo':
        photo_url = att['photo']['sizes'][-1]['url']
        file_path = f"photo_{post_id}.jpg"
        try:
            img_data = requests.get(photo_url, timeout=30).content
            with open(file_path, 'wb') as f:
                f.write(img_data)
            send_to_telegram(file_path)
        except Exception as e:
            logging.error(f"❌ Ошибка фото: {e}")

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
                    send_to_telegram(file_path)
                    break
                except Exception as e:
                    logging.error(f"❌ Попытка {attempt+1} скачать документ не удалась: {e}")
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        logging.error(f"❌ Не удалось скачать документ после 3 попыток")

    elif att_type == 'video':
        video = att['video']
        link = f"https://vk.com/video{video['owner_id']}_{video['id']}"
        text = f"🎬 Видео в посте #{post_id}:\n{link}"
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          data={'chat_id': CHAT_ID, 'text': text}, timeout=30)
            logging.info(f"📹 Ссылка на видео отправлена")
        except Exception as e:
            logging.error(f"❌ Ошибка отправки ссылки на видео: {e}")

    elif att_type == 'audio':
        audio = att['audio']
        text = f"🎵 Аудио: {audio['artist']} - {audio['title']}"
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          data={'chat_id': CHAT_ID, 'text': text}, timeout=30)
            logging.info(f"🎵 Инфо об аудио отправлена")
        except Exception as e:
            logging.error(f"❌ Ошибка отправки информации об аудио: {e}")

def main():
    global last_post_id
    logging.info("🚀 Мониторинг запущен. Ожидаем новые посты...")
    logging.info(f"📌 Последний обработанный пост: {last_post_id}")

    while True:
        try:
            response = vk.wall.get(owner_id=USER_ID, count=5, filter='owner')

            for post in response['items']:
                post_id = post['id']
                if post_id <= last_post_id:
                    continue

                last_post_id = post_id
                logging.info(f"📝 Новый пост #{post_id}")
                save_last_post_id(post_id)

                if 'attachments' in post:
                    for att in post['attachments']:
                        process_attachment(att, post_id)

        except Exception as e:
            logging.error(f"❌ Ошибка: {e}")
            time.sleep(5)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
