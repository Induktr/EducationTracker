
#!/usr/bin/env python3
import os
import argparse
import requests
from logger import logger
from config import TELEGRAM_BOT_TOKEN

def setup_webhook(webhook_url):
    """
    Настраивает webhook для Telegram бота
    
    :param webhook_url: URL для webhook (API Gateway URL)
    """
    if not TELEGRAM_BOT_TOKEN:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return False
    
    # Полный URL для webhook должен включать токен бота
    full_webhook_url = f"{webhook_url.rstrip('/')}/lambda_function.py"
    
    # URL для настройки webhook
    set_webhook_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    print(f"Настраиваем webhook: {full_webhook_url}")
    
    response = requests.post(
        set_webhook_url, 
        json={'url': full_webhook_url}
    )
    
    if response.status_code == 200 and response.json().get('ok'):
        print("✅ Webhook успешно настроен!")
        logger.log_job_processing(
            "webhook_setup",
            "success",
            {"webhook_url": full_webhook_url}
        )
        return True
    else:
        print(f"❌ Ошибка настройки webhook: {response.text}")
        logger.log_error(
            "webhook_setup_error",
            response.text,
            {"webhook_url": full_webhook_url}
        )
        return False

def get_webhook_info():
    """Получает информацию о текущем webhook"""
    if not TELEGRAM_BOT_TOKEN:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return None
    
    webhook_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    response = requests.get(webhook_info_url)
    
    if response.status_code == 200 and response.json().get('ok'):
        return response.json().get('result')
    else:
        print(f"❌ Ошибка получения информации о webhook: {response.text}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Настройка webhook для Telegram бота')
    parser.add_argument('--url', help='URL для webhook (API Gateway URL)')
    parser.add_argument('--info', action='store_true', help='Получить информацию о текущем webhook')
    
    args = parser.parse_args()
    
    if args.info:
        info = get_webhook_info()
        if info:
            print("Информация о текущем webhook:")
            print(f"URL: {info.get('url')}")
            print(f"Последняя ошибка: {info.get('last_error_message', 'Нет')}")
            print(f"Максимальные соединения: {info.get('max_connections')}")
            print(f"Ожидающие обновления: {info.get('pending_update_count')}")
    elif args.url:
        setup_webhook(args.url)
    else:
        parser.print_help()
