
#!/usr/bin/env python3
import os
import shutil
import zipfile
import subprocess

def create_lambda_package():
    """Создает ZIP-архив для загрузки в AWS Lambda"""
    print("Начинаем создание пакета для AWS Lambda...")
    
    # Создаем временную директорию для пакета
    if os.path.exists("lambda_package"):
        shutil.rmtree("lambda_package")
    
    os.makedirs("lambda_package", exist_ok=True)
    
    # Установка зависимостей в пакет
    print("Устанавливаем зависимости...")
    subprocess.run([
        "pip", "install", 
        "-t", "lambda_package", 
        "python-telegram-bot==21.11.1", 
        "google-api-python-client", 
        "google-auth", 
        "boto3",
        "requests"
    ])
    
    # Копируем файлы исходного кода
    print("Копируем исходный код...")
    for file_name in os.listdir("src"):
        if file_name.endswith(".py"):
            shutil.copy(os.path.join("src", file_name), os.path.join("lambda_package", file_name))
    
    # Создаем ZIP-архив
    print("Создаем ZIP-архив...")
    with zipfile.ZipFile("lambda_function.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
        # Добавляем все файлы из временной директории
        for root, _, files in os.walk("lambda_package"):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, "lambda_package")
                zipf.write(file_path, arcname)
    
    # Удаляем временную директорию
    shutil.rmtree("lambda_package")
    
    print(f"Пакет создан успешно: {os.path.abspath('lambda_function.zip')}")
    print("Размер пакета:", os.path.getsize("lambda_function.zip") / (1024 * 1024), "МБ")
    
    print("\nДля загрузки в AWS Lambda:")
    print("1. Зайдите в консоль AWS Lambda")
    print("2. Создайте новую функцию с именем 'telegram-job-search-bot'")
    print("3. Выберите среду выполнения 'Python 3.11'")
    print("4. Загрузите созданный ZIP-архив")
    print("5. Настройте переменные окружения (TELEGRAM_BOT_TOKEN, GOOGLE_SHEETS_CREDENTIALS, SHEET_ID)")
    print("6. Установите таймаут функции на 5 минут (300 секунд)")
    print("7. Настройте API Gateway для получения вебхуков от Telegram")
    print("8. Настройте CloudWatch Events для запуска поиска вакансий по расписанию")

if __name__ == "__main__":
    create_lambda_package()
