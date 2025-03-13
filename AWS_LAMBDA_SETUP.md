
# Инструкция по настройке Telegram бота на AWS Lambda

Эта инструкция поможет вам настроить бота для поиска вакансий на AWS Lambda, чтобы он работал постоянно.

## Предварительные требования

1. Аккаунт AWS с правами на создание:
   - Lambda функций
   - API Gateway
   - CloudWatch Events
   - IAM ролей
2. Токен Telegram бота
3. Учетные данные Google Sheets API

## Шаг 1: Создание пакета для Lambda

1. В Replit выполните следующую команду для создания пакета:
   ```
   python src/create_lambda_package.py
   ```
2. Скачайте созданный файл `lambda_function.zip`

## Шаг 2: Создание Lambda функции

1. Откройте [консоль AWS Lambda](https://console.aws.amazon.com/lambda)
2. Нажмите "Create function" (Создать функцию)
3. Выберите "Author from scratch" (Создать с нуля)
4. Заполните параметры:
   - Function name: `telegram-job-search-bot`
   - Runtime: Python 3.11
   - Architecture: x86_64
5. Нажмите "Create function"
6. На странице функции загрузите пакет:
   - Выберите вкладку "Code"
   - Нажмите "Upload from" -> ".zip file"
   - Загрузите скачанный файл `lambda_function.zip`
   - Нажмите "Save"
7. Настройте переменные окружения:
   - Выберите вкладку "Configuration" -> "Environment variables"
   - Добавьте следующие переменные:
     - `TELEGRAM_BOT_TOKEN`: ваш токен бота
     - `GOOGLE_SHEETS_CREDENTIALS`: учетные данные Google Sheets API в формате JSON
     - `SHEET_ID`: ID вашей Google таблицы
8. Увеличьте таймаут функции:
   - Выберите вкладку "Configuration" -> "General configuration"
   - Нажмите "Edit"
   - Установите таймаут на 5 минут (300 секунд)
   - Увеличьте объем памяти до 512 MB

## Шаг 3: Настройка API Gateway для webhook

1. Выберите вкладку "Configuration" -> "Triggers"
2. Нажмите "Add trigger"
3. Выберите "API Gateway"
4. Настройте:
   - API type: HTTP API
   - Security: Open
5. Нажмите "Add"
6. Скопируйте URL триггера API Gateway (понадобится для настройки webhook)

## Шаг 4: Настройка webhook в Telegram

Используйте скрипт в Replit для настройки webhook:

```
python src/setup_webhook.py --url https://your-api-gateway-url
```

Или проверьте текущую настройку:

```
python src/setup_webhook.py --info
```

## Шаг 5: Настройка CloudWatch Events для регулярного поиска

1. Откройте [консоль Amazon EventBridge](https://console.aws.amazon.com/events)
2. Нажмите "Create rule" (Создать правило)
3. Заполните параметры:
   - Name: `daily-job-search`
   - Rule type: Schedule
4. В разделе "Schedule pattern" выберите:
   - Fixed rate: 1 Day
5. В разделе "Select targets":
   - Target: Lambda function
   - Function: выберите `telegram-job-search-bot`
   - Payload: Fixed
   - JSON: `{"source": "aws.events", "time": "auto-generated"}`
6. Нажмите "Create"

## Проверка работы

1. Отправьте команду `/start` вашему боту в Telegram
2. Бот должен ответить приветственным сообщением
3. Попробуйте команду `/search` для тестирования поиска вакансий

## Советы по оптимизации

1. Настройте частоту поиска вакансий в CloudWatch Events (например, раз в день)
2. Мониторьте расход ресурсов в CloudWatch Logs
3. Добавьте защиту от спама в бота, ограничив количество запросов от одного пользователя

## Решение проблем

Если бот не отвечает, проверьте:
1. Логи в AWS CloudWatch Logs
2. Настройку webhook через команду `python src/setup_webhook.py --info`
3. Переменные окружения в Lambda функции
