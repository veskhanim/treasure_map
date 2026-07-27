import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')
APPS_SCRIPT_URL = os.getenv('APPS_SCRIPT_URL')

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

# ===== КОМАНДЫ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
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
    await update.message.reply_text(
        ' Справка:\n\n'
        ' Отправьте ссылку на YouTube — видео добавится в pending\n'
        '/app — открыть мини-приложение\n'
        '/channels — список каналов\n'
        '/pending — ожидающие видео\n'
        '/categories — список категорий\n'
        '/stats — статистика\n'
        '/help — эта справка'
    )

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /app"""
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
        msg += ' ПЕРЕВОДЫ:\n'
        for c in translations:
            track = '✅' if c.get('tracked') else '⏸️'
            msg += f"  {track} {c['name']} ({c['id']})\n"
    
    await update.message.reply_text(msg)

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pending"""
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
    categories = apps_script_request('categories', 'GET')
    
    if not categories:
        await update.message.reply_text(' Категории не найдены')
        return
    
    msg = '📂 Категории:\n\n' + '\n'.join(
        [f"• {c['name']} ({c['short_name']})" for c in categories]
    )
    
    await update.message.reply_text(msg)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
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
        f"   Переводческих: {translations}\n"
        f"  👁️ Отслеживаемых: {tracked}"
    )
    
    await update.message.reply_text(msg)

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылок на YouTube"""
    text = update.message.text
    
    # Извлекаем video ID
    import re
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
    existing_ids = [v['id'] for v in videos]
    
    if video_id in existing_ids:
        await update.message.reply_text('⚠️ Это видео уже есть в таблице')
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

# ===== ЗАПУСК =====
def main():
    """Запуск бота"""
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("app", app_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Обработка ссылок YouTube
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    
    print(" Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
