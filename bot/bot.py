import os
import re
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')
APPS_SCRIPT_URL = os.getenv('APPS_SCRIPT_URL')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# ===== API HELPER =====
def apps_script_request(path, method='GET', body=None, params=None):
    """Запрос к Apps Script"""
    if params is None:
        params = {}
    
    url = f"{APPS_SCRIPT_URL}?path={path}"
    if 'id' in params:
        url += f"&id={params['id']}"
    
    try:
        if method == 'GET':
            response = requests.get(url, timeout=10)
        else:
            headers = {'Content-Type': 'text/plain;charset=utf-8'}
            payload = {**(body or {}), '_method': method}
            response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        print(f"📡 Apps Script Response [{method} {path}]: Status={response.status_code}")
        print(f"📄 Response text (first 500 chars): {response.text[:500]}")
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            print(f"❌ Пустой ответ от Apps Script для {path}")
            return {'error': 'Пустой ответ от сервера'}
        
        # Проверяем, что ответ начинается с { или [ (JSON)
        if not response.text.strip().startswith(('{', '[')):
            print(f"❌ Apps Script вернул не JSON для {path}: {response.text[:100]}")
            return {'error': 'Сервер вернул не JSON (возможно HTML ошибка)'}
        
        return response.json()
        
    except requests.exceptions.Timeout:
        print(f" Таймаут при запросе к Apps Script: {path}")
        return {'error': 'Таймаут запроса'}
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при запросе к Apps Script: {e}")
        return {'error': f'Ошибка сети: {str(e)}'}
    except Exception as e:
        print(f"❌ Неизвестная ошибка при запросе к Apps Script: {e}")
        return {'error': f'Неизвестная ошибка: {str(e)}'}

# ===== YOUTUBE API =====
def get_channel_videos(channel_url):
    """Получить видео с канала YouTube"""
    if not YOUTUBE_API_KEY:
        return []
    
    try:
        # Получаем upload playlist ID канала
        channel_response = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={
                'part': 'contentDetails',
                'id': channel_url,
                'key': YOUTUBE_API_KEY
            }
        ).json()
        
        if not channel_response.get('items'):
            return []
        
        upload_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Получаем последние видео
        playlist_response = requests.get(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            params={
                'part': 'snippet',
                'playlistId': upload_playlist_id,
                'maxResults': 10,
                'key': YOUTUBE_API_KEY
            }
        ).json()
        
        videos = []
        for item in playlist_response.get('items', []):
            videos.append({
                'id': item['snippet']['resourceId']['videoId'],
                'title': item['snippet']['title'],
                'published_at': item['snippet']['publishedAt']
            })
        
        return videos
    except Exception as e:
        print(f"Error fetching channel videos: {e}")
        return []

# ===== КОМАНДЫ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    keyboard = [
        [InlineKeyboardButton(
            "🗺️ Открыть приложение", 
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    
    await update.message.reply_text(
        'Привет! 👋\n\n'
        'Я бот для управления видео ATEEZ.\n'
        'Нажми кнопку ниже, чтобы открыть приложение:',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    await update.message.reply_text(
        ' Справка:\n\n'
        ' Отправьте ссылку на YouTube — видео добавится в pending\n'
        '/app — открыть мини-приложение\n'
        '/channels — список каналов\n'
        '/addchannel <name> <url> [original|translation] — добавить канал\n'
        '/track <channel_id> — включить отслеживание\n'
        '/untrack <channel_id> — выключить отслеживание\n'
        '/settype <channel_id> <original|translation> — тип канала\n'
        '/refresh — обновить видео с отслеживаемых каналов\n'
        '/pending — ожидающие видео\n'
        '/categories — список категорий\n'
        '/addcat <name> <short> — добавить категорию\n'
        '/stats — статистика\n'
        '/help — эта справка'
    )

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /app"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    keyboard = [
        [InlineKeyboardButton(
            "🗺️ Открыть", 
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    
    await update.message.reply_text(
        'Откройте мини-приложение:',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /channels"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    channels = apps_script_request('channels', 'GET')
    
    if not channels:
        await update.message.reply_text(' Каналы не найдены')
        return
    
    msg = '📺 Каналы:\n\n'
    
    originals = [c for c in channels if c.get('type') == 'original']
    translations = [c for c in channels if c.get('type') == 'translation']
    
    if originals:
        msg += '🎬 ОРИГИНАЛЬНЫЕ:\n'
        for c in originals:
            track = '✅' if c.get('tracked') else '⏸️'
            msg += f"  {track} {c['name']} ({c['id']})\n"
        msg += '\n'
    
    if translations:
        msg += '🌐 ПЕРЕВОДЫ:\n'
        for c in translations:
            track = '✅' if c.get('tracked') else '⏸️'
            msg += f"  {track} {c['name']} ({c['id']})\n"
    
    await update.message.reply_text(msg)

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addchannel"""
    if len(context.args) < 2:
        await update.message.reply_text(
            'Использование: /addchannel <название> <url> [original|translation]\n\n'
            'Пример: /addchannel KQ ENTERTAINMENT UCaO6TYtlC8U5ttzA2hTrZ4Q original'
        )
        return
    
    # Копируем список аргументов, чтобы не ломать оригинал
    args = context.args.copy()
    
    # 1. Определяем тип канала (последний аргумент, если он original или translation)
    channel_type = 'original'
    if args[-1] in ('original', 'translation'):
        channel_type = args.pop()
    
    # 2. Ссылка на канал (теперь последний аргумент)
    url = args.pop()
    
    # 3. Название канала (всё, что осталось, склеиваем пробелами)
    name = ' '.join(args)
    
    if not name or not url:
        await update.message.reply_text('Неверный формат. Проверьте название и ссылку.')
        return
    
    result = apps_script_request('channels', 'POST', {
        'name': name,
        'url': url,
        'type': channel_type,
        'tracked': False
    })
    
    await update.message.reply_text(
        f"✅ Канал добавлен!\n\n"
        f"ID: {result.get('id')}\n"
        f"Название: {name}\n"
        f"Тип: {channel_type}\n\n"
        f"Используйте /track {result.get('id')} для включения отслеживания."
    )

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /track"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if not context.args:
        await update.message.reply_text('Использование: /track <channel_id>')
        return
    
    channel_id = context.args[0]
    
    channels = apps_script_request('channels', 'GET')
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        await update.message.reply_text('❌ Канал не найден')
        return
    
    channel['tracked'] = True
    apps_script_request('channels', 'PUT', channel, {'id': channel_id})
    
    await update.message.reply_text(f"✅ Отслеживание канала {channel_id} включено")

async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /untrack"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if not context.args:
        await update.message.reply_text('Использование: /untrack <channel_id>')
        return
    
    channel_id = context.args[0]
    
    channels = apps_script_request('channels', 'GET')
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        await update.message.reply_text('❌ Канал не найден')
        return
    
    channel['tracked'] = False
    apps_script_request('channels', 'PUT', channel, {'id': channel_id})
    
    await update.message.reply_text(f"⏸️ Отслеживание канала {channel_id} выключено")

async def set_type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settype"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if len(context.args) < 2:
        await update.message.reply_text('Использование: /settype <channel_id> <original|translation>')
        return
    
    channel_id = context.args[0]
    channel_type = context.args[1]
    
    if channel_type not in ('original', 'translation'):
        await update.message.reply_text('Тип должен быть: original или translation')
        return
    
    channels = apps_script_request('channels', 'GET')
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        await update.message.reply_text('❌ Канал не найден')
        return
    
    channel['type'] = channel_type
    apps_script_request('channels', 'PUT', channel, {'id': channel_id})
    
    type_name = 'оригинальный' if channel_type == 'original' else 'переводческий'
    await update.message.reply_text(f"✅ Тип канала {channel_id} изменен на: {type_name}")

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /refresh - обновление видео с отслеживаемых каналов"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    await update.message.reply_text('🔄 Обновляю каналы...')
    
    # Получаем отслеживаемые каналы
    channels = apps_script_request('channels', 'GET')
    tracked_channels = [c for c in channels if c.get('tracked')]
    
    if not tracked_channels:
        await update.message.reply_text('📺 Нет отслеживаемых каналов')
        return
    
    # Получаем существующие видео
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    
    existing_ids = set([v['id'] for v in videos] + [p['id'] for p in pending])
    
    total_new = 0
    
    for channel in tracked_channels:
        channel_videos = get_channel_videos(channel['url'])
        
        for video in channel_videos:
            if video['id'] not in existing_ids:
                # Добавляем в pending
                apps_script_request('pending-videos', 'POST', {
                    'id': video_id,
                    'title': oembed_data.get('title', 'Без названия'),
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'published_at': published_at,  # dd.mm.yyyy
                    'duration': duration,          # hh.mm
                    'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                    'video_url': f'https://youtube.com/watch?v={video_id}'
                })
                
                existing_ids.add(video['id'])
                total_new += 1
    
    if total_new > 0:
        await update.message.reply_text(f"✅ Найдено {total_new} новых видео!")
    else:
        await update.message.reply_text('✨ Новых видео не найдено')

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pending"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    pending = apps_script_request('pending-videos', 'GET')
    
    if not pending:
        await update.message.reply_text('✨ Нет ожидающих видео')
        return
    
    msg = f"⏳ Ожидающие видео ({len(pending)}):\n\n"
    
    for i, v in enumerate(pending[:5], 1):
        msg += f"{i}. {v['title']}\n"
        msg += f"   📺 {v.get('channel_name', 'Неизвестно')}\n\n"
    
    if len(pending) > 5:
        msg += f"... и ещё {len(pending) - 5}\n"
    
    await update.message.reply_text(msg)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /categories"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    categories = apps_script_request('categories', 'GET')
    
    if not categories:
        await update.message.reply_text(' Категории не найдены')
        return
    
    msg = '📂 Категории:\n\n' + '\n'.join(
        [f"• {c['name']} ({c['short_name']})" for c in categories]
    )
    
    await update.message.reply_text(msg)

async def add_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addcat"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            'Использование: /addcat <название> <краткое>\n\n'
            'Пример: /addcat Music Video MV'
        )
        return
    
    name = context.args[0]
    short = context.args[1]
    
    apps_script_request('categories', 'POST', {
        'name': name,
        'short_name': short
    })
    
    await update.message.reply_text(f"✅ Категория добавлена: {name} ({short})")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    channels = apps_script_request('channels', 'GET')
    
    originals = len([c for c in channels if c.get('type') == 'original'])
    translations = len([c for c in channels if c.get('type') == 'translation'])
    tracked = len([c for c in channels if c.get('tracked')])
    
    msg = (
        f"📊 Статистика:\n\n"
        f" Видео: {len(videos)}\n"
        f"⏳ Pending: {len(pending)}\n"
        f"📺 Каналы: {len(channels)}\n"
        f"  🎬 Оригинальных: {originals}\n"
        f"  🌐 Переводческих: {translations}\n"
        f"  👁️ Отслеживаемых: {tracked}"
    )
    
    await update.message.reply_text(msg)

from datetime import datetime
import re

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылок на YouTube"""
    text = update.message.text
    
    # Извлекаем video ID
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$',
        r'shorts\/([0-9A-Za-z_-]{11})',
    ]
    
    video_id = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            video_id = match.group(1)
            break
    
    if not video_id:
        return
    
    # Проверяем существование
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    
    existing_video_ids = set()
    if isinstance(videos, list):
        existing_video_ids.update([str(v.get('id', '')) for v in videos])
    if isinstance(pending, list):
        existing_video_ids.update([str(p.get('id', '')) for p in pending])
    
    if video_id in existing_video_ids:
        await update.message.reply_text('⚠️ Это видео уже есть в таблице')
        return
    
    try:
        # 1. Получаем базовую информацию через oEmbed
        oembed_url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
        oembed_response = requests.get(oembed_url, timeout=10)
        oembed_data = oembed_response.json() if oembed_response.status_code == 200 else {}
        
        channel_id = 'manual'
        channel_name = oembed_data.get('author_name', 'Неизвестно')
        duration = ''
        published_at = ''
        
        print(f"🔍 Видео ID: {video_id}")
        print(f" Название канала из oEmbed: {channel_name}")
        
        # 2. Получаем список каналов из таблицы
        channels = apps_script_request('channels', 'GET')
        print(f" Получено каналов из таблицы: {len(channels) if isinstance(channels, list) else 0}")
        
        if isinstance(channels, list):
            for ch in channels:
                print(f"  - Канал: id={ch.get('id')}, name={ch.get('name')}, url={ch.get('url')}")
        
        # 3. Если есть YouTube API ключ, получаем точный channel_id
        if YOUTUBE_API_KEY:
            print(f"🔑 YouTube API ключ установлен")
            try:
                api_url = f'https://www.googleapis.com/youtube/v3/videos'
                api_response = requests.get(
                    api_url,
                    params={
                        'part': 'snippet,contentDetails',
                        'id': video_id,
                        'key': YOUTUBE_API_KEY
                    },
                    timeout=10
                )
                api_data = api_response.json()
                
                if api_data.get('items'):
                    video_info = api_data['items'][0]
                    snippet = video_info['snippet']
                    
                    # Получаем точный ID канала с YouTube
                    yt_channel_id = snippet.get('channelId', '')
                    published_at_iso = snippet.get('publishedAt', '')
                    
                    print(f" YouTube channel ID: {yt_channel_id}")
                    
                    # Форматируем дату как dd.mm.yyyy
                    if published_at_iso:
                        pub_date = datetime.fromisoformat(published_at_iso.replace('Z', '+00:00'))
                        published_at = pub_date.strftime('%d.%m.%Y')
                        print(f" Дата публикации: {published_at}")
                    
                    # Длительность - форматируем как hh:mm:ss или mm:ss
                    duration_iso = video_info['contentDetails']['duration']
                    hours = re.search(r'(\d+)H', duration_iso)
                    minutes = re.search(r'(\d+)M', duration_iso)
                    seconds = re.search(r'(\d+)S', duration_iso)
                    
                    h = int(hours.group(1)) if hours else 0
                    m = int(minutes.group(1)) if minutes else 0
                    s = int(seconds.group(1)) if seconds else 0
                    
                    # Формат: hh:mm:ss если есть часы, иначе mm:ss
                    if h > 0:
                        duration = f'{h}:{m:02d}:{s:02d}'
                    else:
                        duration = f'{m}:{s:02d}'
                    
                    print(f"⏱️ Длительность: {duration}")
                    
                    # 4. Ищем совпадение по ID канала
                    if isinstance(channels, list):
                        for ch in channels:
                            ch_url = str(ch.get('url', '')).strip()
                            if ch_url == yt_channel_id:
                                channel_id = ch.get('id', 'manual')
                                channel_name = ch.get('name', channel_name)
                                print(f"✅ Найдено совпадение по ID: {channel_id}")
                                break
                            if 'youtube.com/channel/' in ch_url:
                                extracted_id = ch_url.split('youtube.com/channel/')[-1].split('/')[0]
                                if extracted_id == yt_channel_id:
                                    channel_id = ch.get('id', 'manual')
                                    channel_name = ch.get('name', channel_name)
                                    print(f"✅ Найдено совпадение по ссылке канала: {channel_id}")
                                    break
                else:
                    print(f"⚠️ YouTube API не вернул данные для видео")
                    
            except Exception as e:
                print(f"❌ Ошибка YouTube API: {e}")
        else:
            print(f"⚠️ YouTube API ключ НЕ установлен")
        
        # 5. Fallback: если не нашли по ID, ищем по названию
        if channel_id == 'manual' and isinstance(channels, list):
            print(f"🔍 Пробуем найти по названию канала...")
            for ch in channels:
                db_name = str(ch.get('name', '')).lower().strip()
                oembed_name = channel_name.lower().strip()
                
                if db_name == oembed_name:
                    channel_id = ch.get('id', 'manual')
                    print(f"✅ Найдено совпадение по названию: {channel_id}")
                    break
                
                if db_name in oembed_name or oembed_name in db_name:
                    channel_id = ch.get('id', 'manual')
                    print(f"✅ Найдено частичное совпадение по названию: {channel_id}")
                    break
        
        if channel_id == 'manual':
            print(f"️ Канал не найден, устанавливаем manual")
        
        # 6. Добавляем в pending
        result = apps_script_request('pending-videos', 'POST', {
            'id': video_id,
            'title': oembed_data.get('title', 'Без названия'),
            'channel_id': channel_id,
            'channel_name': channel_name,
            'published_at': published_at,  # dd.mm.yyyy
            'duration': duration,          # hh:mm:ss или mm:ss
            'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
            'video_url': f'https://youtube.com/watch?v={video_id}'
        })
        
        if isinstance(result, dict) and result.get('success'):
            duration_text = f"⏱ {duration}" if duration else ""
            channel_text = f"📺 {channel_name}" if channel_name != 'Неизвестно' else ""
            
            msg = f"✅ Видео добавлено в pending!\n\n"
            msg += f"📹 {oembed_data.get('title', 'Без названия')}\n"
            if channel_text: msg += f"{channel_text}\n"
            if duration_text: msg += f"{duration_text}\n"
            if published_at: msg += f" {published_at}\n"
            msg += f"\n🆔 Channel ID: {channel_id}"
            
            if channel_id == 'manual':
                msg += "\n⚠️ Канал не найден в таблице"
            
            await update.message.reply_text(msg)
        else:
            error_msg = result.get('error', 'Неизвестная ошибка') if isinstance(result, dict) else str(result)
            await update.message.reply_text(f'❌ Ошибка при добавлении: {error_msg}')
            
    except requests.exceptions.Timeout:
        await update.message.reply_text('❌ Таймаут при получении информации о видео')
    except Exception as e:
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')

# ===== ПРОВЕРКА ДОСТУПА =====
def check_access(telegram_id: int) -> bool:
    """Проверяет, есть ли у пользователя доступ"""
    try:
        url = f"{APPS_SCRIPT_URL}?path=users"
        print(f"🔍 Запрос к Apps Script: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"📡 Статус ответа: {response.status_code}")
        print(f"📄 Текст ответа: {response.text[:300]}") # Покажет первые 300 символов ответа
        
        # Пробуем распарсить JSON
        users = response.json()
        
        if isinstance(users, list):
            for user in users:
                if str(user.get('telegram_id')) == str(telegram_id):
                    access_val = str(user.get('access')).lower()
                    return access_val in ['true', '1', 'yes']
        return False
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при проверке доступа: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка парсинга JSON при проверке доступа: {e}")
        return False
        
# ===== ЗАПУСК =====
def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("app", app_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("addchannel", add_channel_command))
    application.add_handler(CommandHandler("track", track_command))
    application.add_handler(CommandHandler("untrack", untrack_command))
    application.add_handler(CommandHandler("settype", set_type_command))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("addcat", add_category_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Обработка ссылок
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
