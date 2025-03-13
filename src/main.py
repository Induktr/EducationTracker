from hh_jobs import HeadHunterAPI
from utils import clean_job_description, filter_recent_jobs, deduplicate_jobs, determine_experience_level, normalize_currency
from sheets_handler import GoogleSheetsHandler
from logger import logger
from datetime import datetime

def main():
    try:
        # Initialize components
        logger.log_job_processing(
            "main_start",
            "starting",
            {"timestamp": datetime.now().isoformat()}
        )
        hh_api = HeadHunterAPI()
        sheets = GoogleSheetsHandler()

        # Расширенный список ключевых слов для поиска
        import random
        
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
        # чтобы не превышать длину запроса
        search_keywords = random.sample(search_keywords_pool, min(2, len(search_keywords_pool)))
        
        # Места для поиска
        locations = ["Москва", "Санкт-Петербург", "Удаленная работа"]

        all_jobs = []

        # Search jobs for each location
        for location in locations:
            try:
                # Увеличиваем лимит поиска для каждой локации
                logger.log_job_processing(
                    "location_search",
                    "starting",
                    {"location": location, "keywords": search_keywords}
                )
                jobs = hh_api.search_jobs(
                    keywords=search_keywords,
                    area=location,
                    limit=25  # Увеличенный лимит для получения большего количества вакансий
                )
                
                # Если API вернул пустой список, пробуем уменьшить количество ключевых слов
                if not jobs and len(search_keywords) > 1:
                    logger.log_job_processing(
                        "retry_with_less_keywords",
                        "starting",
                        {"location": location}
                    )
                    # Пробуем только с первым ключевым словом
                    jobs = hh_api.search_jobs(
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
                    details = hh_api.get_job_details(job["id"])
                    formatted_job = hh_api.format_job_data(details)

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
        existing_ids = sheets.get_existing_job_ids()
        existing_job_data = sheets.get_existing_job_data()
        
        # Дополнительная проверка на дубликаты с использованием расширенной информации
        logger.log_job_processing(
            "enhanced_deduplication",
            "starting",
            {"jobs_before_deduplication": len(recent_jobs)}
        )
        
        new_jobs = deduplicate_jobs(recent_jobs, existing_ids)

        # Save to Google Sheets
        if new_jobs:
            sheets.append_jobs(new_jobs)
            logger.log_job_processing(
                "job_search_complete",
                "success",
                {
                    "new_jobs_found": len(new_jobs),
                    "total_jobs_processed": len(all_jobs)
                }
            )
        else:
            logger.log_job_processing(
                "job_search_complete",
                "no_new_jobs",
                {"total_jobs_processed": len(all_jobs)}
            )
    except Exception as e:
        logger.log_error(
            "main_execution_error",
            str(e),
            {}
        )
        raise

if __name__ == "__main__":
    main()