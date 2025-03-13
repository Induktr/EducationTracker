from typing import Dict, List, Any
from datetime import datetime, timedelta
import re
from config import EXPERIENCE_LEVELS
from logger import logger  # Add logger import

def clean_job_description(description: str) -> str:
    """Clean and normalize job description text"""
    # Remove HTML tags
    description = re.sub(r'<[^>]+>', '', description)
    # Remove extra whitespace
    description = ' '.join(description.split())
    # Remove special characters
    description = re.sub(r'[^\w\s\-.,]', '', description)
    return description

def determine_experience_level(description: str) -> str:
    """
    Determine job experience level based on keywords
    Returns: "junior", "middle", or "senior"
    """
    desc_lower = description.lower()

    # Count occurrences of level-specific keywords
    junior_score = sum(1 for keyword in EXPERIENCE_LEVELS["junior"] 
                      if keyword in desc_lower)
    middle_score = sum(1 for keyword in EXPERIENCE_LEVELS["middle"] 
                      if keyword in desc_lower)
    senior_score = sum(1 for keyword in EXPERIENCE_LEVELS.get("senior", [])
                      if keyword in desc_lower)

    # Parse years of experience if mentioned
    years = parse_experience_years(description)
    if years > 0:
        if years <= 2:
            junior_score += 2
        elif years <= 5:
            middle_score += 2
        else:
            senior_score += 2

    # Determine level based on highest score
    if senior_score > middle_score and senior_score > junior_score:
        return "senior"
    elif middle_score > junior_score:
        return "middle"
    else:
        return "junior"

def filter_recent_jobs(jobs: List[Dict[str, Any]], days: int = 30) -> List[Dict[str, Any]]:
    """Filter jobs posted within the last X days"""
    # Use UTC timezone for consistency
    from datetime import timezone
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    filtered_jobs = []
    for job in jobs:
        # Convert posted_at to UTC for comparison
        posted_at_str = job.get('posted_at', '')
        if not posted_at_str:
            continue

        try:
            # Parse ISO format with timezone
            posted_at = datetime.fromisoformat(posted_at_str.replace('Z', '+00:00'))
            if posted_at >= cutoff_date:
                filtered_jobs.append(job)
        except ValueError:
            # Skip jobs with invalid date format
            continue

    return filtered_jobs

def validate_job_data(job: Dict[str, Any]) -> bool:
    """Validate required job data fields"""
    required_fields = ['job_id', 'title', 'company', 'description']
    return all(job.get(field) for field in required_fields)

def normalize_currency(currency):
    """
    Normalize currency code, converting RUR to RUB
    """
    if currency == "RUR":
        return "RUB"
    return currency

def deduplicate_jobs(jobs, existing_ids):
    """
    Remove duplicate jobs based on job_id and content similarity
    """
    if not jobs:
        return []

    # Log before deduplication
    logger.log_job_processing(
        "deduplication_start",
        "processing",
        {
            "new_jobs_count": len(jobs),
            "existing_ids_count": len(existing_ids),
            "example_new_job_id": jobs[0].get('job_id') if jobs else None
        }
    )

    # Первый проход - удаление дубликатов по ID из существующих записей
    unique_jobs = []
    duplicates = []
    seen_ids = set(existing_ids)  # Используем set для быстрого поиска

    for job in jobs:
        job_id = job.get('job_id')
        if job_id not in seen_ids:
            unique_jobs.append(job)
            seen_ids.add(job_id)  # Добавляем ID в просмотренные для избежания внутренних дубликатов
        else:
            duplicates.append(job_id)

    # Второй проход - улучшенная дедупликация по нескольким критериям
    # Добавляем временные метки для учета самых свежих вакансий
    internal_duplicates = []
    final_unique_jobs = []
    seen_job_signatures = set()
    seen_job_content = {}
    
    # Сортируем вакансии по дате публикации (сначала самые новые)
    sorted_jobs = sorted(
        unique_jobs, 
        key=lambda j: j.get('posted_at', ''), 
        reverse=True
    )  # Словарь для отслеживания схожих вакансий

    for job in sorted_jobs:
        # Базовая подпись вакансии (компания + название)
        company = job.get('company', '').lower().strip()
        title = job.get('title', '').lower().strip()
        base_signature = f"{company}-{title}"

        # Полная подпись вакансии (включая локацию)
        location = job.get('location', '').lower().strip()
        full_signature = f"{base_signature}-{location}"

        # Если точная вакансия с такой же локацией уже есть
        if full_signature in seen_job_signatures:
            internal_duplicates.append(job.get('job_id'))
            continue

        # Проверка на схожие вакансии той же компании и должности, но с разной локацией
        is_duplicate = False
        if base_signature in seen_job_content:
            # Дополнительная проверка схожести вакансии (сравнение по описанию и зарплате)
            existing_job = seen_job_content[base_signature]

            # Проверка похожести по описанию (если описание есть)
            desc_similarity = False
            job_desc = job.get('description', '').lower()
            existing_desc = existing_job.get('description', '').lower()

            # Если описания достаточно похожи или одинаковые зарплаты
            if (job_desc and existing_desc and 
                (job_desc[:100] == existing_desc[:100] or  # Сравниваем первые 100 символов
                 job_desc[-100:] == existing_desc[-100:])):  # и последние 100 символов
                desc_similarity = True

            # Проверка совпадения зарплаты
            salary_similarity = (
                job.get('salary_from') == existing_job.get('salary_from') and
                job.get('salary_to') == existing_job.get('salary_to') and
                job.get('salary_currency') == existing_job.get('salary_currency')
            )

            # Если и описание похоже, и зарплата совпадает - считаем дубликатом
            if (desc_similarity and salary_similarity) or (desc_similarity and "skypro" in company):
                internal_duplicates.append(job.get('job_id'))
                is_duplicate = True

        if not is_duplicate:
            final_unique_jobs.append(job)
            seen_job_signatures.add(full_signature)
            seen_job_content[base_signature] = job

    # Log after deduplication with more details
    logger.log_job_processing(
        "deduplication_complete",
        "processed",
        {
            "original_count": len(jobs),
            "unique_count": len(final_unique_jobs),
            "duplicates_by_id": len(duplicates),
            "duplicates_by_content": len(internal_duplicates),
            "total_duplicates_removed": len(duplicates) + len(internal_duplicates),
            "duplicate_ids": duplicates[:5],  # Log first 5 duplicate IDs for debugging
            "internal_duplicate_ids": internal_duplicates[:5],
            "improved_deduplication": True
        }
    )

    return final_unique_jobs

def extract_key_requirements(description: str) -> List[str]:
    """Extract key requirements from job description"""
    # Common requirement patterns
    requirement_patterns = [
        r'требования:.*?(?=\n|$)',
        r'требуется:.*?(?=\n|$)',
        r'обязательно:.*?(?=\n|$)',
        r'необходимо:.*?(?=\n|$)'
    ]

    requirements = []
    for pattern in requirement_patterns:
        matches = re.findall(pattern, description, re.IGNORECASE)
        requirements.extend(matches)

    return [req.strip() for req in requirements if req.strip()]

def format_date_for_api(date: datetime) -> str:
    """Format date for API requests"""
    return date.strftime('%Y-%m-%d')

def parse_experience_years(text: str) -> int:
    """Parse years of experience from text"""
    patterns = [
        r'(\d+)[\+]?\s*(?:год|лет|года)(?:\s+опыта)?',
        r'опыт\s+(?:работы\s+)?(\d+)[\+]?\s*(?:год|лет|года)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 0