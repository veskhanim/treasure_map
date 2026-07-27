import os
import re
import requests
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
    
    if method == 'GET':
        response = requests.get(url)
    else:
        headers = {'Content-Type': 'text/plain;charset=utf-8'}
        payload = {**(body or {}), '_method': method}
        response = requests.post(url, headers=headers, json=payload)
    
    return response.json()

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
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            'Использование: /addchannel <название> <url> [original|translation]\n\n'
            'Пример: /addchannel KQ ENTERTAINMENT UCaO6TYtlC8U5ttzA2hTrZ4Q original'
        )
        return
    
    name = context.args[0]
    url = context.args[1]
    channel_type = context.args[2] if len(context.args) > 2 else 'original'
    
    if channel_type not in ('original', 'translation'):
        await update.message.reply_text('Тип должен быть: original или translation')
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
                    'id': video['id'],
                    'title': video['title'],
                    'channel_id': channel['id'],
                    'channel_name': channel['name'],
                    'published_at': video['published_at'],
                    'video_url': f"https://youtube.com/watch?v={video['id']}"
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

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылок на YouTube"""
    text = update.message.text
    
    # Извлекаем video ID
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'^([0-9A-Za-z_-]{11})$'
    ]
    
    video_id = None
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            video_id = match.group(1)
            break
    
    if not video_id:
        return
    
    # Проверяем существование
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    
    existing_ids = set([v['id'] for v in videos] + [p['id'] for p in pending])
    
    if video_id in existing_ids:
        await update.message.reply_text('️ Это видео уже есть в таблице')
        return
    
    # Получаем информацию о видео
    try:
        url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
        response = requests.get(url)
        data = response.json()
        
        apps_script_request('pending-videos', 'POST', {
            'id': video_id,
            'title': data['title'],
            'channel_id': 'manual',
            'channel_name': 'Добавлено вручную',
            'video_url': f'https://youtube.com/watch?v={video_id}'
        })
        
        await update.message.reply_text(
            f"✅ Видео добавлено в pending!\n\n{data['title']}"
        )
    except Exception as e:
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')

# ===== ПРОВЕРКА ДОСТУПА =====
def check_access(telegram_id: int) -> bool:
    """Проверяет, есть ли у пользователя доступ"""
    try:
        url = f"{APPS_SCRIPT_URL}?path=users"
        response = requests.get(url)
        users = response.json()
        
        if isinstance(users, list):
            for user in users:
                # Сравниваем как строки, чтобы избежать проблем с типами
                if str(user.get('telegram_id')) == str(telegram_id):
                    access_val = str(user.get('access')).lower()
                    return access_val in ['true', '1', 'yes']
        return False
    except Exception as e:
        print(f"Ошибка проверки доступа: {e}")
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
