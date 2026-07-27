import os
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')
SHEET_ID = os.getenv('SHEET_ID')
SERVICE_ACCOUNT_FILE = 'credentials.json'
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

def get_sheets_service():
    """Получение сервиса Google Sheets"""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=creds)

def get_user(telegram_id):
    """Проверка доступа пользователя"""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Users!A:D'
    ).execute()
    
    rows = result.get('values', [])
    for row in rows[1:]:  # Пропускаем заголовок
        if str(row[0]) == str(telegram_id):
            return {
                'telegram_id': row[0],
                'username': row[1],
                'name': row[2],
                'access': row[3] == 'true'
            }
    return None

def check_access(telegram_id):
    """Проверка доступа"""
    user = get_user(telegram_id)
    return user and user['access']

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    telegram_id = update.effective_user.id
    
    if not check_access(telegram_id):
        await update.message.reply_text(
            '❌ У вас нет доступа к боту.\n\n'
            'Обратитесь к администратору для получения доступа.'
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("🗺️ Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    
    await update.message.reply_text(
        f'Привет, {update.effective_user.first_name}! 👋\n\n'
        'Я бот для управления видео ATEEZ.\n\n'
        '📱 Откройте мини-приложение для просмотра видео\n'
        ' Отправьте ссылку на YouTube для добавления\n'
        '/help - справка',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    if not check_access(update.effective_user.id):
        return
    
    await update.message.reply_text(
        '📖 Справка:\n\n'
        '📹 Отправьте ссылку на YouTube - видео добавится в pending\n'
        '/app - открыть мини-приложение\n'
        '/channels - список каналов\n'
        '/addchannel <name> <url> [original|translation] - добавить канал\n'
        '/track <channel_id> - включить отслеживание\n'
        '/untrack <channel_id> - выключить отслеживание\n'
        '/settype <channel_id> <original|translation> - тип канала\n'
        '/refresh - обновить отслеживаемые каналы\n'
        '/pending - ожидающие видео\n'
        '/categories - список категорий\n'
        '/addcat <name> <short> - добавить категорию\n'
        '/stats - статистика\n'
        '/help - эта справка'
    )

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /app"""
    if not check_access(update.effective_user.id):
        return
    
    keyboard = [
        [InlineKeyboardButton("🗺️ Открыть", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    
    await update.message.reply_text(
        'Откройте мини-приложение:',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /channels"""
    if not check_access(update.effective_user.id):
        return
    
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E'
    ).execute()
    
    rows = result.get('values', [])
    channels = []
    
    for row in rows[1:]:
        if len(row) >= 5:
            channels.append({
                'id': row[0],
                'name': row[1],
                'url': row[2],
                'type': row[3],
                'tracked': row[4] == 'true'
            })
    
    if not channels:
        await update.message.reply_text(' Каналы не найдены')
        return
    
    msg = ' Каналы:\n\n'
    
    originals = [c for c in channels if c['type'] == 'original']
    translations = [c for c in channels if c['type'] == 'translation']
    
    if originals:
        msg += '🎬 ОРИГИНАЛЬНЫЕ:\n'
        for c in originals:
            track = '✅' if c['tracked'] else '⏸️'
            msg += f'  {track} {c["name"]} ({c["id"]})\n'
        msg += '\n'
    
    if translations:
        msg += '🌐 ПЕРЕВОДЫ:\n'
        for c in translations:
            track = '✅' if c['tracked'] else '⏸️'
            msg += f'  {track} {c["name"]} ({c["id"]})\n'
    
    await update.message.reply_text(msg)

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addchannel"""
    if not check_access(update.effective_user.id):
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
    
    service = get_sheets_service()
    
    # Получаем текущее количество каналов для генерации ID
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:A'
    ).execute()
    
    new_id = f'ch{len(result.get("values", []))}'
    
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E',
        valueInputOption='RAW',
        body={'values': [[new_id, name, url, channel_type, 'false']]}
    ).execute()
    
    await update.message.reply_text(
        f'✅ Канал добавлен!\n\n'
        f'ID: {new_id}\n'
        f'Название: {name}\n'
        f'Тип: {channel_type}\n\n'
        f'Используйте /track {new_id} для включения отслеживания.'
    )

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /track"""
    if not check_access(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text('Использование: /track <channel_id>')
        return
    
    channel_id = context.args[0]
    
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E'
    ).execute()
    
    rows = result.get('values', [])
    
    for i, row in enumerate(rows[1:], 2):
        if row[0] == channel_id:
            range_str = f'Channels!E{i}:E{i}'
            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=range_str,
                valueInputOption='RAW',
                body={'values': [['true']]}
            ).execute()
            
            await update.message.reply_text(f'✅ Отслеживание канала {channel_id} включено')
            return
    
    await update.message.reply_text('❌ Канал не найден')

async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /untrack"""
    if not check_access(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text('Использование: /untrack <channel_id>')
        return
    
    channel_id = context.args[0]
    
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E'
    ).execute()
    
    rows = result.get('values', [])
    
    for i, row in enumerate(rows[1:], 2):
        if row[0] == channel_id:
            range_str = f'Channels!E{i}:E{i}'
            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=range_str,
                valueInputOption='RAW',
                body={'values': [['false']]}
            ).execute()
            
            await update.message.reply_text(f'️ Отслеживание канала {channel_id} выключено')
            return
    
    await update.message.reply_text('❌ Канал не найден')

async def set_type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settype"""
    if not check_access(update.effective_user.id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text('Использование: /settype <channel_id> <original|translation>')
        return
    
    channel_id = context.args[0]
    channel_type = context.args[1]
    
    if channel_type not in ('original', 'translation'):
        await update.message.reply_text('Тип должен быть: original или translation')
        return
    
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E'
    ).execute()
    
    rows = result.get('values', [])
    
    for i, row in enumerate(rows[1:], 2):
        if row[0] == channel_id:
            range_str = f'Channels!D{i}:D{i}'
            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=range_str,
                valueInputOption='RAW',
                body={'values': [[channel_type]]}
            ).execute()
            
            type_name = 'оригинальный' if channel_type == 'original' else 'переводческий'
            await update.message.reply_text(f'✅ Тип канала {channel_id} изменен на: {type_name}')
            return
    
    await update.message.reply_text('❌ Канал не найден')

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /refresh - обновление отслеживаемых каналов"""
    if not check_access(update.effective_user.id):
        return
    
    await update.message.reply_text('🔄 Обновляю каналы...')
    
    service = get_sheets_service()
    
    # Получаем отслеживаемые каналы
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E'
    ).execute()
    
    rows = result.get('values', [])
    channels = []
    
    for row in rows[1:]:
        if len(row) >= 5 and row[4] == 'true':
            channels.append({
                'id': row[0],
                'name': row[1],
                'url': row[2]
            })
    
    if not channels:
        await update.message.reply_text('📺 Нет отслеживаемых каналов')
        return
    
    # Получаем существующие видео
    videos_result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Videos!A:A'
    ).execute()
    
    existing_ids = set()
    for row in videos_result.get('values', [])[1:]:
        if row:
            existing_ids.add(row[0])
    
    # Получаем pending видео
    pending_result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='PendingVideos!A:A'
    ).execute()
    
    for row in pending_result.get('values', [])[1:]:
        if row:
            existing_ids.add(row[0])
    
    total_new = 0
    
    for channel in channels:
        try:
            # Получаем видео с канала через YouTube API
            youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
            
            channel_response = youtube.channels().list(
                id=channel['url'],
                part='contentDetails'
            ).execute()
            
            if not channel_response.get('items'):
                continue
            
            upload_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            playlist_items = youtube.playlistItems().list(
                playlistId=upload_id,
                part='snippet',
                maxResults=10
            ).execute()
            
            for item in playlist_items['items']:
                video_id = item['snippet']['resourceId']['videoId']
                
                if video_id not in existing_ids:
                    # Добавляем в pending
                    service.spreadsheets().values().append(
                        spreadsheetId=SHEET_ID,
                        range='PendingVideos!A:I',
                        valueInputOption='RAW',
                        body={'values': [[
                            video_id,
                            item['snippet']['title'],
                            channel['id'],
                            channel['name'],
                            item['snippet']['publishedAt'],
                            '',
                            '',
                            f'https://youtube.com/watch?v={video_id}',
                            ''
                        ]]}
                    ).execute()
                    
                    existing_ids.add(video_id)
                    total_new += 1
            
        except Exception as e:
            print(f'Error fetching {channel["name"]}: {e}')
    
    if total_new > 0:
        await update.message.reply_text(f'✅ Найдено {total_new} новых видео!')
    else:
        await update.message.reply_text('✨ Новых видео не найдено')

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pending"""
    if not check_access(update.effective_user.id):
        return
    
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='PendingVideos!A:I'
    ).execute()
    
    rows = result.get('values', [])
    pending = []
    
    for row in rows[1:]:
        if len(row) >= 9:
            pending.append({
                'id': row[0],
                'title': row[1],
                'channel_name': row[3]
            })
    
    if not pending:
        await update.message.reply_text('✨ Нет ожидающих видео')
        return
    
    msg = f' Ожидающие видео ({len(pending)}):\n\n'
    
    for i, v in enumerate(pending[:5], 1):
        msg += f'{i}. {v["title"]}\n'
        msg += f'   📺 {v["channel_name"]}\n\n'
    
    if len(pending) > 5:
        msg += f'... и еще {len(pending) - 5}\n'
    
    await update.message.reply_text(msg)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /categories"""
    if not check_access(update.effective_user.id):
        return
    
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Categories!A:C'
    ).execute()
    
    rows = result.get('values', [])
    categories = []
    
    for row in rows[1:]:
        if len(row) >= 3:
            categories.append(f'{row[1]} ({row[2]})')
    
    if not categories:
        await update.message.reply_text('📂 Категории не найдены')
        return
    
    msg = ' Категории:\n\n' + '\n'.join(categories)
    await update.message.reply_text(msg)

async def add_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addcat"""
    if not check_access(update.effective_user.id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            'Использование: /addcat <название> <краткое>\n\n'
            'Пример: /addcat Music Video MV'
        )
        return
    
    name = context.args[0]
    short = context.args[1]
    
    service = get_sheets_service()
    
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Categories!A:A'
    ).execute()
    
    new_id = str(len(result.get('values', [])))
    
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range='Categories!A:C',
        valueInputOption='RAW',
        body={'values': [[new_id, name, short]]}
    ).execute()
    
    await update.message.reply_text(f'✅ Категория добавлена: {name} ({short})')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    if not check_access(update.effective_user.id):
        return
    
    service = get_sheets_service()
    
    # Видео
    videos_result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Videos!A:A'
    ).execute()
    videos_count = len(videos_result.get('values', [])) - 1
    
    # Pending
    pending_result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='PendingVideos!A:A'
    ).execute()
    pending_count = len(pending_result.get('values', [])) - 1
    
    # Каналы
    channels_result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Channels!A:E'
    ).execute()
    
    channels = channels_result.get('values', [])[1:]
    originals = len([c for c in channels if len(c) >= 4 and c[3] == 'original'])
    translations = len([c for c in channels if len(c) >= 4 and c[3] == 'translation'])
    tracked = len([c for c in channels if len(c) >= 5 and c[4] == 'true'])
    
    msg = (
        f'📊 Статистика:\n\n'
        f'🎬 Видео: {videos_count}\n'
        f'⏳ Pending: {pending_count}\n'
        f'📺 Каналы: {len(channels)}\n'
        f'  🎬 Оригинальных: {originals}\n'
        f'   Переводческих: {translations}\n'
        f'  👁️ Отслеживаемых: {tracked}'
    )
    
    await update.message.reply_text(msg)

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылок на YouTube"""
    if not check_access(update.effective_user.id):
        return
    
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
    service = get_sheets_service()
    
    videos_result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Videos!A:A'
    ).execute()
    
    existing_ids = set()
    for row in videos_result.get('values', [])[1:]:
        if row:
            existing_ids.add(row[0])
    
    if video_id in existing_ids:
        await update.message.reply_text('⚠️ Это видео уже есть в таблице')
        return
    
    # Получаем информацию о видео
    try:
        url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
        response = requests.get(url)
        data = response.json()
        
        service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range='PendingVideos!A:I',
            valueInputOption='RAW',
            body={'values': [[
                video_id,
                data['title'],
                'manual',
                'Добавлено вручную',
                '',
                '',
                '',
                f'https://youtube.com/watch?v={video_id}',
                ''
            ]]}
        ).execute()
        
        await update.message.reply_text(
            f'✅ Видео добавлено в pending!\n\n'
            f'{data["title"]}'
        )
    except Exception as e:
        await update.message.reply_text(f'❌ Ошибка получения информации о видео: {str(e)}')

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