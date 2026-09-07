import vk_api
import time
import requests
import os
import logging

# ===== НАСТРОЙКИ =====
VK_TOKEN = "vk1.a.Bz-nwwK34t8ZDzMXyD4ADXvWR9OHrZLXgZvl3OsU2R3mTBCEyQr3zU2TeyIOav65OpXGJoUwvjCpT-WZYgTRYvTeLPDYH5ZOU3TeqTPMWxesL78_ThOVGbpVWccS2mrsWtmY7XY2YXhBWhYgkA7uoG2U0RDcaCRiOuHQu3IyeVOoH06AxSx4aYQkZjtZfNf8rQ7HB9CsriF-TPEdUHnjPQ"
USER_ID = "1128567349"              # Новая страница
CHECK_INTERVAL = 30

BOT_TOKEN = "8888651340:AAGBkRtGJAjALGERpkB8aX2aM8pYbcScZRE"
CHAT_ID = "-1003968224550"
# ====================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

last_post_id = 0

def send_to_telegram(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': CHAT_ID}
            response = requests.post(url, files=files, data=data)
            if response.status_code == 200:
                logging.info(f"✅ Отправлено: {os.path.basename(file_path)}")
            else:
                logging.error(f"❌ Ошибка: {response.text}")
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
            img_data = requests.get(photo_url, timeout=10).content
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
            try:
                doc_data = requests.get(doc_url, timeout=30).content
                with open(file_path, 'wb') as f:
                    f.write(doc_data)
                send_to_telegram(file_path)
            except Exception as e:
                logging.error(f"❌ Ошибка документа: {e}")

    elif att_type == 'video':
        video = att['video']
        link = f"https://vk.com/video{video['owner_id']}_{video['id']}"
        text = f"🎬 Видео в посте #{post_id}:\n{link}"
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={'chat_id': CHAT_ID, 'text': text})
        logging.info(f"📹 Ссылка на видео отправлена")

    elif att_type == 'audio':
        audio = att['audio']
        text = f"🎵 Аудио: {audio['artist']} - {audio['title']}"
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={'chat_id': CHAT_ID, 'text': text})
        logging.info(f"🎵 Инфо об аудио отправлена")

def main():
    global last_post_id
    logging.info("🚀 Мониторинг запущен. Ожидаем новые посты...")

    while True:
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
                        process_attachment(att, post_id)

        except Exception as e:
            logging.error(f"❌ Ошибка: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
