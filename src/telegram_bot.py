
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError
from logger import logger
from hh_jobs import HeadHunterAPI
from sheets_handler import GoogleSheetsHandler
from utils import clean_job_description, filter_recent_jobs, deduplicate_jobs, determine_experience_level, normalize_currency
from datetime import datetime
import random

# Получаем токен бота из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

class JobSearchTelegramBot:
    def __init__(self, application=None):
        """
        Инициализация бота с поддержкой как стандартного режима, так и AWS Lambda
        
        :param application: Существующий экземпляр Application для режима AWS Lambda
        """
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("Telegram bot token not found in environment variables")
        
        self.hh_api = HeadHunterAPI()
        self.sheets = GoogleSheetsHandler()
        
        # Используем переданный экземпляр Application или создаем новый
        self.application = application or Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Регистрация обработчиков команд
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("search", self.search_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Определяем режим работы (Lambda или стандартный)
        self.is_lambda_mode = application is not None
        
        logger.log_job_processing(
            "telegram_bot_init",
            "success",
            {"bot_initialized": True, "lambda_mode": self.is_lambda_mode}
        )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start - приветствие пользователя."""
        user_name = update.effective_user.first_name
        welcome_message = (
            f"👋 Привет, {user_name}!\n\n"
            "Я бот для поиска вакансий Python разработчиков. "
            "Я помогу вам найти актуальные вакансии на сайте HeadHunter.\n\n"
            "Доступные команды:\n"
            "/search - Запустить поиск последних вакансий\n"
            "/help - Показать справку по командам"
        )
        
        await update.message.reply_text(welcome_message)
        
        logger.log_job_processing(
            "telegram_start_command",
            "success",
            {"user_id": update.effective_user.id, "user_name": user_name}
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help - показывает справку."""
        help_message = (
            "📚 *Справка по командам:*\n\n"
            "/start - Начать взаимодействие с ботом\n"
            "/search - Запустить поиск последних вакансий на HeadHunter\n"
            "/help - Показать эту справку"
        )
        
        await update.message.reply_text(help_message, parse_mode="Markdown")
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /search - поиск вакансий."""
        await update.message.reply_text("🔍 Начинаю поиск вакансий. Это может занять некоторое время...")
        
        try:
            # Запускаем поиск
            search_results = await self.perform_job_search()
            
            if search_results["new_jobs_found"] > 0:
                await update.message.reply_text(
                    f"✅ Поиск завершен!\n\n"
                    f"📊 Найдено новых вакансий: {search_results['new_jobs_found']}\n"
                    f"🔄 Всего обработано вакансий: {search_results['total_processed']}\n\n"
                    "Вакансии добавлены в Google Таблицу."
                )
                
                # Отправляем пример последних 3-х найденных вакансий
                if search_results.get("example_jobs"):
                    await update.message.reply_text("📝 Примеры найденных вакансий:")
                    
                    for job in search_results["example_jobs"][:3]:
                        job_message = (
                            f"*{job['title']}*\n"
                            f"🏢 Компания: {job['company']}\n"
                            f"📍 Локация: {job['location']}\n"
                            f"💰 Зарплата: {self._format_salary(job)}\n"
                            f"🔗 [Ссылка на вакансию]({job['apply_url']})"
                        )
                        await update.message.reply_text(job_message, parse_mode="Markdown", disable_web_page_preview=True)
            else:
                await update.message.reply_text(
                    "🔍 Поиск завершен, но новых вакансий не найдено.\n"
                    "Попробуйте позже или проверьте текущие вакансии в таблице."
                )
                
            logger.log_job_processing(
                "telegram_search_command",
                "success",
                {"user_id": update.effective_user.id, "results": search_results}
            )
            
        except Exception as e:
            error_message = f"❌ Произошла ошибка при поиске вакансий: {str(e)}"
            await update.message.reply_text(error_message)
            
            logger.log_error(
                "telegram_search_error",
                str(e),
                {"user_id": update.effective_user.id}
            )
    
    async def perform_job_search(self):
        """Выполняет поиск вакансий и возвращает результаты."""
        # Расширенный список ключевых слов для поиска
        search_keywords_pool = [
            "Python разработчик", 
            "Python developer", 
            "Python программист",
            "Backend Python",
            "Python backend",
            "Django developer",
            "Flask developer",
            "Python инженер",
            "ML engineer Python",
            "Data engineer Python"
        ]
        
        # Выбираем только 1-2 ключевых слова для каждого поиска 
        search_keywords = random.sample(search_keywords_pool, min(2, len(search_keywords_pool)))
        
        # Места для поиска
        locations = ["Москва", "Санкт-Петербург", "Удаленная работа"]

        all_jobs = []

        # Search jobs for each location
        for location in locations:
            try:
                logger.log_job_processing(
                    "location_search",
                    "starting",
                    {"location": location, "keywords": search_keywords}
                )
                jobs = self.hh_api.search_jobs(
                    keywords=search_keywords,
                    area=location,
                    limit=25
                )
                
                # Если API вернул пустой список, пробуем уменьшить количество ключевых слов
                if not jobs and len(search_keywords) > 1:
                    logger.log_job_processing(
                        "retry_with_less_keywords",
                        "starting",
                        {"location": location}
                    )
                    # Пробуем только с первым ключевым словом
                    jobs = self.hh_api.search_jobs(
                        keywords=[search_keywords[0]],
                        area=location,
                        limit=25
                    )
            except Exception as e:
                logger.log_error(
                    "location_search_error",
                    str(e),
                    {"location": location}
                )
                # Продолжаем со следующей локацией
                jobs = []

            # Get full job details and format
            for job in jobs:
                try:
                    details = self.hh_api.get_job_details(job["id"])
                    formatted_job = self.hh_api.format_job_data(details)

                    # Clean description
                    formatted_job["description"] = clean_job_description(
                        formatted_job["description"]
                    )

                    # Determine experience level based on keywords
                    formatted_job["experience_level"] = determine_experience_level(
                        formatted_job["description"]
                    )
                    
                    # Normalize currency (RUR -> RUB)
                    if "salary_currency" in formatted_job:
                        formatted_job["salary_currency"] = normalize_currency(formatted_job["salary_currency"])

                    all_jobs.append(formatted_job)

                except Exception as e:
                    logger.log_error(
                        "job_processing_error",
                        str(e),
                        {"job_id": job["id"]}
                    )
                    continue

        # Фильтрация только самых свежих вакансий (последние 3 дня)
        recent_jobs = filter_recent_jobs(all_jobs, days=3)
        
        # Получаем полную информацию о существующих вакансиях
        existing_ids = self.sheets.get_existing_job_ids()
        existing_job_data = self.sheets.get_existing_job_data()
        
        # Дополнительная проверка на дубликаты с использованием расширенной информации
        logger.log_job_processing(
            "enhanced_deduplication",
            "starting",
            {"jobs_before_deduplication": len(recent_jobs)}
        )
        
        new_jobs = deduplicate_jobs(recent_jobs, existing_ids)

        # Save to Google Sheets
        if new_jobs:
            self.sheets.append_jobs(new_jobs)
            
            return {
                "new_jobs_found": len(new_jobs),
                "total_processed": len(all_jobs),
                "example_jobs": new_jobs[:5]  # Возвращаем примеры вакансий
            }
        else:
            logger.log_job_processing(
                "job_search_complete",
                "no_new_jobs",
                {"total_jobs_processed": len(all_jobs)}
            )
            
            return {
                "new_jobs_found": 0,
                "total_processed": len(all_jobs)
            }
    
    def _format_salary(self, job):
        """Форматирует информацию о зарплате для вывода."""
        salary_from = job.get("salary_from")
        salary_to = job.get("salary_to")
        currency = job.get("salary_currency", "")
        
        if not salary_from and not salary_to:
            return "Не указана"
            
        salary_text = ""
        
        if salary_from:
            salary_text += f"от {salary_from}"
            
        if salary_to:
            if salary_text:
                salary_text += f" до {salary_to}"
            else:
                salary_text += f"до {salary_to}"
                
        return f"{salary_text} {currency}"
    
    def run(self, webhook_mode=False, webhook_url=None):
        """
        Запускает Telegram бота.
        
        :param webhook_mode: Если True, запускает в режиме webhook для Lambda
        :param webhook_url: URL для webhook (требуется для режима webhook)
        """
        logger.log_job_processing(
            "telegram_bot_start",
            "starting",
            {
                "timestamp": datetime.now().isoformat(),
                "webhook_mode": webhook_mode
            }
        )
        
        if webhook_mode and webhook_url:
            # Настройка webhook для AWS Lambda
            self.application.run_webhook(
                listen="0.0.0.0",
                port=8443,
                url_path=TELEGRAM_BOT_TOKEN,
                webhook_url=webhook_url
            )
        else:
            # Стандартный режим polling
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)


# Функция для запуска бота
def run_telegram_bot(webhook_mode=False, webhook_url=None):
    try:
        bot = JobSearchTelegramBot()
        bot.run(webhook_mode=webhook_mode, webhook_url=webhook_url)
    except Exception as e:
        logger.log_error(
            "telegram_bot_error", 
            str(e),
            {}
        )
        raise


# Функция для настройки webhook
def setup_webhook(webhook_url):
    """
    Настраивает webhook для Telegram бота
    
    :param webhook_url: URL для webhook включая токен
    """
    try:
        import requests
        
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("Telegram bot token not found in environment variables")
            
        # URL для настройки webhook
        set_webhook_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
        response = requests.post(
            set_webhook_url, 
            json={'url': webhook_url}
        )
        
        if response.status_code == 200 and response.json().get('ok'):
            logger.log_job_processing(
                "webhook_setup",
                "success",
                {"webhook_url": webhook_url}
            )
            return True
        else:
            logger.log_error(
                "webhook_setup_error",
                response.text,
                {"webhook_url": webhook_url}
            )
            return False
    except Exception as e:
        logger.log_error(
            "webhook_setup_exception",
            str(e),
            {"webhook_url": webhook_url}
        )
        return False

if __name__ == "__main__":
    run_telegram_bot()
