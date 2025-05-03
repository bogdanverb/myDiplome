import os
from dotenv import load_dotenv
from datetime import timedelta

# Загружаем переменные окружения из .env файла
load_dotenv()

# Конфигурация MySQL
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', ''),
    'raise_on_warnings': True
}

# API ключ для OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Конфигурация безопасности
SECURITY_CONFIG = {
    'rate_limit': {
        'requests': 30,
        'window': 60  # seconds
    },
    'allowed_origins': [
        'http://localhost:3000',
        'https://example.com'
    ],
    'ssl': {
        'cert_path': 'certificate.pem',
        'key_path': 'private_key.pem'
    }
}

# Налаштування для CORS
CORS_ORIGINS = [
    'http://localhost:5000',
    'http://127.0.0.1:5000'
]

SESSION_SECRET = os.environ.get('SESSION_SECRET', 'default-secret-key')
RATE_LIMIT = os.environ.get('RATE_LIMIT', '100/day')
