
import json
import logging
import os
import boto3
from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.request import HTTPXRequest
import asyncio
from telegram_bot import JobSearchTelegramBot
from logger import logger

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение токена из переменных окружения или AWS Parameter Store
def get_telegram_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        # Если токен не найден в переменных окружения, пытаемся получить из AWS Parameter Store
        ssm = boto3.client('ssm')
        parameter = ssm.get_parameter(Name='/telegram/bot/token', WithDecryption=True)
        token = parameter['Parameter']['Value']
    return token

# AWS Lambda обработчик
def lambda_handler(event, context):
    """Функция обработчик для AWS Lambda"""
    try:
        # Получаем данные из события
        if 'body' in event:
            body = json.loads(event['body'])
            logger.log_job_processing(
                "lambda_webhook_received",
                "starting",
                {"update_type": body.get('message', {}).get('text', 'unknown')}
            )
            
            # Асинхронно обрабатываем webhook от Telegram
            asyncio.run(process_telegram_update(body))
            
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'success'})
            }
        elif event.get('source') == 'aws.events':
            # Обработка события по расписанию (CloudWatch Events)
            logger.log_job_processing(
                "lambda_scheduled_event",
                "starting",
                {"event_source": "CloudWatch"}
            )
            
            # Запускаем поиск вакансий по расписанию
            asyncio.run(scheduled_job_search())
            
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'scheduled_search_completed'})
            }
        
        return {
            'statusCode': 400,
            'body': json.dumps({'status': 'invalid_request'})
        }
    except Exception as e:
        logger.log_error(
            "lambda_handler_error",
            str(e),
            {"event_type": event.get('source', 'unknown')}
        )
        return {
            'statusCode': 500,
            'body': json.dumps({'status': 'error', 'message': str(e)})
        }

# Асинхронная обработка обновлений Telegram
async def process_telegram_update(update_data):
    """Обрабатывает webhook обновления от Telegram"""
    token = get_telegram_token()
    
    # Создаем экземпляр бота с webhook-режимом
    application = Application.builder().token(token).build()
    
    # Создаем экземпляр нашего бота
    bot = JobSearchTelegramBot(application=application)
    
    # Преобразуем словарь в объект Update
    update = Update.de_json(update_data, application.bot)
    
    # Обрабатываем update
    await application.process_update(update)

# Функция для запуска поиска вакансий по расписанию
async def scheduled_job_search():
    """Запускает поиск вакансий по расписанию через CloudWatch Events"""
    token = get_telegram_token()
    
    # Создаем экземпляр приложения
    application = Application.builder().token(token).build()
    
    # Создаем экземпляр нашего бота
    bot = JobSearchTelegramBot(application=application)
    
    # Запускаем поиск вакансий
    search_results = await bot.perform_job_search()
    
    logger.log_job_processing(
        "scheduled_job_search",
        "completed",
        {
            "new_jobs_found": search_results.get("new_jobs_found", 0),
            "total_processed": search_results.get("total_processed", 0)
        }
    )
    
    return search_results

# Для локального тестирования
if __name__ == "__main__":
    # Имитируем событие из CloudWatch для тестирования
    test_event = {
        'source': 'aws.events',
        'time': '2023-01-01T00:00:00Z',
    }
    result = lambda_handler(test_event, None)
    print(result)
