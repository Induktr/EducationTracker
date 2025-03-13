
#!/usr/bin/env python3
import argparse
import os
import time
import logging
from telegram_bot import run_telegram_bot, setup_webhook
from logger import logger

# Настройка логирования для отслеживания перезапусков
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    """
    Основная функция с циклом перезапуска при ошибках
    для обеспечения постоянной работы бота.
    """
    parser = argparse.ArgumentParser(description='Запуск Telegram бота для поиска вакансий')
    parser.add_argument('--webhook', help='URL для webhook (если запускается в режиме webhook)')
    parser.add_argument('--setup-only', action='store_true', help='Только настроить webhook без запуска бота')
    
    args = parser.parse_args()
    
    # Настраиваем webhook, если нужно
    if args.webhook:
        if args.setup_only:
            # Только настраиваем webhook без запуска бота
            if setup_webhook(args.webhook):
                print("Webhook успешно настроен. Выход.")
                return
            else:
                print("Ошибка настройки webhook. Выход.")
                return
        
        # Запускаем в режиме webhook
        print(f"Запуск бота в режиме webhook с URL: {args.webhook}")
        try:
            run_telegram_bot(webhook_mode=True, webhook_url=args.webhook)
        except Exception as e:
            logger.log_error(
                "telegram_bot_webhook_error",
                str(e),
                {"webhook_url": args.webhook}
            )
    else:
        # Запускаем в стандартном режиме с перезапуском при ошибках
        # Определяем, запущен ли бот в режиме деплоя
        is_deployment = os.getenv("REPLIT_DEPLOYMENT") == "1"
        
        # Логируем информацию о среде
        logger.log_job_processing(
            "telegram_bot_startup",
            "starting",
            {"deployment": is_deployment, "message": "Бот запускается"}
        )
        
        # В режиме деплоя используем цикл перезапуска
        while True:
            try:
                # Запускаем бота
                run_telegram_bot()
            except Exception as e:
                # Логируем ошибку
                logger.log_error(
                    "telegram_bot_crash",
                    str(e),
                    {"restart": "Попытка перезапуска через 60 секунд"}
                )
                # Ждем 60 секунд перед перезапуском
                time.sleep(60)
            
            # Если не в режиме деплоя, не перезапускаем автоматически
            if not is_deployment:
                break

if __name__ == "__main__":
    main()
