import os

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HH_USER_AGENT = "Job Search Automation App"  # Required by HH.ru API
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Google Sheets Configuration
SHEET_ID = os.getenv("SHEET_ID")
JOBS_WORKSHEET = "Jobs"
LOGS_WORKSHEET = "Logs"

# Job Search Configuration
EXPERIENCE_LEVELS = {
    "junior": ["junior", "младший", "beginning", "начинающий", "0-1", "1-3"],
    "middle": ["middle", "миддл", "средний", "2-4", "3-5"]
}

# HH.ru API Configuration
HH_API_BASE_URL = "https://api.hh.ru/vacancies"
HH_AREAS = {
    "Москва": "1",
    "Санкт-Петербург": "2"
}

# Поиск удаленных вакансий через ключевые слова
REMOTE_KEYWORDS = ["удаленная работа", "удаленно", "remote", "удаленка"]

# Logging Configuration
LOG_LEVEL = "INFO"