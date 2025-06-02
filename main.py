import logging
import aiohttp
import asyncio
from aiohttp import web
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
import xml.etree.ElementTree as ET

TOKEN = "7346488642:AAG3yOPQXT2Qo0Elxudrjq2cvVfC_BGxP0g"
OPDS_BASE_URL = "http://flibusta.is/opds"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpdsBot:
    def __init__(self):
        self.search_results = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📚 Шалом православный! Если ви хочете какую книжку то напишите мене шо ви хочете, и я таки попробую её найти.")

    async def fetch_entries(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Ошибка HTTP {response.status} при запросе {url}")
                    return None
                xml_data = await response.text()

        with open("last_response.xml", "w", encoding="utf-8") as f:
            f.write(xml_data)

        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        return root.findall('atom:entry', ns)

    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.message.text.strip()
        if not query:
            await update.message.reply_text("Введите название книги или автора.")
            return

        url = f"{OPDS_BASE_URL}/search?query={quote(query)}"
        entries = await self.fetch_entries(url)
        if entries is None:
            await update.message.reply_text("Ошибка при получении данных.")
            return

        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        def has_acquisition(entry):
            for l in entry.findall('atom:link', ns):
                if "acquisition" in l.attrib.get('rel', ''):
                    return True
            return False

        real_books = [e for e in entries if has_acquisition(e)]

        if not real_books:
            sub_links = []
            for e in entries:
                for l in e.findall('atom:link', ns):
                    rel = l.attrib.get('rel', '')
                    type_ = l.attrib.get('type', '')
                    href = l.attrib.get('href', '')
                    if rel == 'subsection' or type_ == 'application/atom+xml':
                        sub_links.append(href)

            for sub_url in sub_links:
                sub_entries = await self.fetch_entries(sub_url)
                if sub_entries is None:
                    continue
                for e in sub_entries:
                    if has_acquisition(e):
                        real_books.append(e)

        if not real_books:
            await update.message.reply_text("Книги не найдены.")
            return

        self.search_results[update.effective_chat.id] = []
        buttons = []
        reply_text = "🔍 Найдено:\n\n"

        for entry in real_books[:10]:
            title = entry.find('atom:title', ns).text
            author_el = entry.find('atom:author/atom:name', ns)
            author = author_el.text if author_el is not None else "Неизвестен"

            link = None
            for l in entry.findall('atom:link', ns):
                if "acquisition" in l.attrib.get('rel', ''):
                    link = l.attrib.get('href')
                    break

            if not link:
                continue

            index = len(self.search_results[update.effective_chat.id])
            self.search_results[update.effective_chat.id].append({
                'title': title,
                'author': author,
                'link': link
            })

            reply_text += f"{index + 1}. {title} — {author}\n"
            buttons.append([InlineKeyboardButton(f"📥 Скачать {index + 1}", callback_data=str(index))])

        if not self.search_results[update.effective_chat.id]:
            await update.message.reply_text("Книги не найдены.")
            return

        await update.message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(buttons))

    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        index = int(query.data)
        chat_id = query.message.chat.id

        if chat_id not in self.search_results or index >= len(self.search_results[chat_id]):
            await query.edit_message_text("❌ Книга не найдена.")
            return

        book = self.search_results[chat_id][index]
        text = (
            f"📖 <b>{book['title']}</b>\n"
            f"👤 Автор: {book['author']}\n\n"
            f"🔗 <a href=\"{book['link']}\">Скачать книгу</a>"
        )

        await query.edit_message_text(text=text, parse_mode="HTML")

async def start_bot():
    bot = OpdsBot()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.search))
    app.add_handler(CallbackQueryHandler(bot.button))

    print("✅ Бот запущен.")
    await app.initialize()
    await app.start()
    return app

# Веб-сервер для Render
async def web_server():
    async def handle(request):
        return web.Response(text="✅ Бот работает!", content_type="text/plain")
    
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    print("🌐 Веб-сервер запущен на порту 10000.")

async def main():
    tg_app = await start_bot()
    await web_server()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
