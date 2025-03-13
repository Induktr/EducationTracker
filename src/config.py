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
    "junior": [
        "junior", "младший", "начинающий", "стажер", "без опыта", "intern",
        "entry level", "entry-level", "0-1 year", "0-1 года", "student", "студент"
    ],
    "middle": [
        "middle", "миддл", "опыт от 2", "опыт от 3", "2+ years", "3+ years", 
        "2-3 года", "3-5 лет", "опытный", "experienced"
    ],
    "senior": [
        "senior", "старший", "ведущий", "lead", "опыт от 5", "опыт от 6",
        "5+ years", "6+ years", "5-7 лет", "архитектор", "team lead",
        "тимлид", "tech lead", "principal", "эксперт"
    ]
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