import requests
from typing import Dict, List, Optional
from datetime import datetime
import json
from time import sleep
from config import HH_API_BASE_URL, HH_USER_AGENT, HH_AREAS
from logger import logger

class HeadHunterAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": HH_USER_AGENT,
            "Content-Type": "application/json"
        }
        self.request_delay = 2  # Increased base delay
        self.max_retries = 3

    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict:
        """Make API request with exponential backoff"""
        retries = 0
        while retries < self.max_retries:
            try:
                sleep(self.request_delay * (2 ** retries))  # Exponential backoff

                # Логируем параметры запроса для отладки
                logger.log_api_call(
                    "hh.ru",
                    "api_request",
                    f"attempt {retries + 1}/{self.max_retries}"
                )

                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params or {}
                )

                if response.status_code == 403:
                    logger.log_error(
                        "hh_rate_limit",
                        f"Rate limit exceeded, retry {retries + 1}/{self.max_retries}",
                        {"url": url}
                    )
                    retries += 1
                    continue

                # Проверяем другие коды ошибок и пытаемся продолжить
                if response.status_code == 400:
                    # Логируем подробности ошибки и пытаемся исправить параметры
                    logger.log_error(
                        "hh_bad_request",
                        f"Bad request, trying to fix parameters, retry {retries + 1}/{self.max_retries}",
                        {"params": params}
                    )
                    # Упрощаем запрос при ошибке
                    if params and "text" in params and len(params["text"]) > 50:
                        # Сокращаем поисковый запрос для следующей попытки
                        params["text"] = params["text"].split()[0]
                    if params and "date_from" in params:
                        del params["date_from"]
                    if params and "period" in params:
                        del params["period"]
                    retries += 1
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                if retries == self.max_retries - 1:
                    logger.log_error(
                        "hh_api_error",
                        str(e),
                        {"url": url, "params": params, "retries": retries}
                    )
                    # Если это последняя попытка, возвращаем пустые результаты вместо ошибки
                    return {"items": []}
                retries += 1

        # Вместо исключения возвращаем пустой результат
        logger.log_error(
            "hh_max_retries",
            "Max retries exceeded, returning empty results",
            {"url": url, "params": params}
        )
        return {"items": []}

    def search_jobs(self, 
                   keywords: List[str],
                   area: Optional[str] = None,
                   experience_level: Optional[str] = None,
                   limit: int = 25) -> List[Dict]:
        """
        Search for jobs on hh.ru
        Returns list of job postings
        """
        # Initialize params outside the try block to avoid "possibly unbound" error
        params = {}

        try:
            # Если ищем удаленную работу, добавляем соответствующие ключевые слова
            if area == "Удаленная работа":
                from config import REMOTE_KEYWORDS
                search_text = " ".join(keywords + REMOTE_KEYWORDS[:2])  # Берем первые два ключевых слова
                area_param = None
            else:
                search_text = " ".join(keywords)
                area_param = HH_AREAS.get(area) if area else None

            # Используем только параметр period для поиска по последним дням
            # Не используем date_from, чтобы избежать ошибок с датами
            import random

            # Рандомизируем порядок сортировки для разнообразия результатов
            sort_options = ["publication_time", "salary_desc", "relevance"]

            # Ограничиваем длину поискового запроса
            max_text_length = 100
            if len(search_text) > max_text_length:
                search_text = search_text[:max_text_length]

            params = {
                "text": search_text,
                "per_page": limit,
                "only_with_salary": True,
                "order_by": random.choice(sort_options),
                "period": 7  # Ищем вакансии за последнюю неделю
            }

            if area_param:
                params["area"] = area_param

            if experience_level:
                # HH.ru experience levels: noExperience, between1And3, between3And6
                params["experience"] = (
                    "noExperience" if experience_level == "junior" 
                    else "between1And3"
                )

            jobs = self._make_request(HH_API_BASE_URL, params)
            jobs = jobs.get("items", [])

            logger.log_api_call(
                "hh.ru",
                "search_jobs",
                f"success - found {len(jobs)} jobs"
            )

            return jobs

        except Exception as e:
            logger.log_error(
                "hh_api_error",
                str(e),
                {"params": params}  # Now params is guaranteed to be defined
            )
            raise

    def get_job_details(self, job_id: str) -> Dict:
        """
        Get detailed information about a specific job
        """
        try:
            job_details = self._make_request(f"{HH_API_BASE_URL}/{job_id}")

            logger.log_api_call(
                "hh.ru",
                f"get_job_details/{job_id}",
                "success"
            )

            return job_details

        except Exception as e:
            logger.log_error(
                "hh_job_details_error",
                str(e),
                {"job_id": job_id}
            )
            raise

    def format_job_data(self, job: Dict) -> Dict:
        """Format job data for storage"""
        from datetime import datetime, timezone

        # Convert timestamp to UTC ISO format
        posted_at = job.get("published_at")
        if posted_at:
            try:
                dt = datetime.fromisoformat(posted_at.replace('Z', '+00:00'))
                posted_at = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                posted_at = datetime.now(timezone.utc).isoformat()

        salary = job.get("salary", {})
        return {
            "job_id": job.get("id"),
            "title": job.get("name"),
            "company": job.get("employer", {}).get("name"),
            "location": job.get("area", {}).get("name"),
            "description": job.get("description"),
            "salary_from": salary.get("from"),
            "salary_to": salary.get("to"),
            "salary_currency": salary.get("currency"),
            "apply_url": job.get("alternate_url"),
            "posted_at": posted_at,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }