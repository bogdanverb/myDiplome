# app.py
from flask import Flask, render_template, request, jsonify, url_for, session, make_response
import uuid
import mysql.connector
import openai
import json
from config import MYSQL_CONFIG, OPENAI_API_KEY
import requests
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'your-secret-key-here'  # Замените на случайный секретный ключ

# Словарь для хранения историй диалогов по сессиям
conversation_histories = {}

# Время жизни сессии (24 часа)
SESSION_LIFETIME = timedelta(hours=24)

def cleanup_old_sessions():
    """Очистка старых сессий"""
    current_time = datetime.now()
    for session_id in list(conversation_histories.keys()):
        last_activity = conversation_histories[session_id].get('last_activity')
        if last_activity and (current_time - last_activity) > SESSION_LIFETIME:
            del conversation_histories[session_id]

# Встановлюємо ключ OpenAI API
openai.api_key = OPENAI_API_KEY

# Функція для отримання з'єднання з MySQL
def get_db_connection():
    conn = mysql.connector.connect(
        host=MYSQL_CONFIG['host'],
        user=MYSQL_CONFIG['user'],
        password=MYSQL_CONFIG['password'],
        database=MYSQL_CONFIG['database']
    )
    return conn

# Функція для уточнення запиту користувача за допомогою OpenAI API
def refine_search_query(query):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Виконай наступне завдання: перетвори запит користувача, "
                        "який стосується комп'ютерних комплектуючих, до набору ключових слів, "
                        "які можуть міститися у полях name, type або description бази даних. "
                        "Виведи лише ключові слова через пробіл, без додаткового тексту."
                    )
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            temperature=0
        )
        refined = response.choices[0].message['content'].strip()
        return refined
    except Exception as e:
        print(f"Error in refine_search_query: {e}")
        return query

# Універсальна функція пошуку по всіх таблицях бази даних із розбиттям запиту на ключові слова
def universal_search_db(query):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Отримуємо список таблиць
    cursor.execute("SHOW TABLES")
    tables = [list(row.values())[0] for row in cursor.fetchall()]
    
    search_results = []
    # Розбиваємо уточнений запит на ключові слова
    tokens = query.split()
    
    for table in tables:
        # Отримуємо опис таблиці для визначення текстових колонок
        cursor.execute(f"DESCRIBE {table}")
        columns = cursor.fetchall()
        text_columns = []
        for col in columns:
            # Вважаємо текстовими поля, якщо тип містить "char", "text" або "enum"
            if "char" in col['Type'] or "text" in col['Type'] or "enum":
                text_columns.append(col['Field'])
        if not text_columns:
            continue  # Таблиця не містить текстових полів
        
        # Формуємо умови пошуку для кожного ключового слова
        conditions = []
        params = []
        for token in tokens:
            sub_conditions = []
            for col in text_columns:
                sub_conditions.append(f"{col} LIKE %s")
                params.append("%" + token + "%")
            # Кожне слово має бути знайдене хоча б в одному з полів
            conditions.append("(" + " OR ".join(sub_conditions) + ")")
        
        if conditions:
            where_clause = " AND ".join(conditions)
            sql = f"SELECT * FROM {table} WHERE {where_clause}"
            try:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
                if rows:
                    search_results.extend(rows)
            except Exception as e:
                print(f"Error querying table {table}: {e}")
                continue
    
    cursor.close()
    conn.close()
    return search_results

def get_performance_category(component):
    """Определяет категорию производительности компонента"""
    price = float(component['price'])
    if component['type'] == 'CPU':
        if price > 300: return "high-end"
        if price > 200: return "mid-range"
        return "budget"
    elif component['type'] == 'GPU':
        if price > 500: return "high-end"
        if price > 300: return "mid-range"
        return "budget"
    elif component['type'] == 'RAM':
        if price > 150: return "high-end"
        if price > 100: return "mid-range"
        return "budget"
    elif component['type'] == 'SSD':
        if price > 200: return "high-end"
        if price > 100: return "mid-range"
        return "budget"
    elif component['type'] == 'HDD':
        if price > 100: return "high-end"
        if price > 50: return "mid-range"
        return "budget"
    return "standard"

def format_db_data_for_ai():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    structured_data = {
        "components_catalog": {
            "cpu": [],
            "gpu": [],
            "ram": [],
            "storage": [],
            "other": []
        },
        "metadata": {
            "categories": [],
            "price_ranges": {},
            "specifications_schema": {}
        }
    }

    try:
        # Получаем все компоненты
        cursor.execute("SELECT * FROM components")
        components = cursor.fetchall()
        
        for component in components:
            # Парсим JSON из specs
            specs = json.loads(component['specs'])
            category = component['type'].lower()
            
            # Форматируем компонент
            formatted_component = {
                "id": component['id'],
                "name": component['name'],
                "type": component['type'],
                "description": component['description'],
                "price": float(component['price']),
                "specifications": specs,
                "performance_category": get_performance_category(component)
            }
            
            # Распределяем по категориям
            if category in structured_data["components_catalog"]:
                structured_data["components_catalog"][category].append(formatted_component)
            else:
                structured_data["components_catalog"]["other"].append(formatted_component)
                
            # Обновляем метаданные
            if category not in structured_data["metadata"]["categories"]:
                structured_data["metadata"]["categories"].append(category)

    except Exception as e:
        print(f"Error formatting data: {e}")
    finally:
        cursor.close()
        conn.close()
        
    return structured_data

def create_ai_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    ai_context = {
        "available_components": [],
        "inventory_summary": {
            "total_items": 0,
            "categories": {},
            "price_ranges": {}
        },
        "search_helpers": {
            "component_types": [],
            "manufacturers": [],
            "common_queries": []
        }
    }

    try:
        cursor.execute("SELECT * FROM components")
        components = cursor.fetchall()
        
        for item in components:
            specs = json.loads(item['specs'])
            
            # Форматируем компонент
            component = {
                "name": item['name'],
                "type": item['type'],
                "price": float(item['price']),
                "specs": specs,
                "in_stock": True,  # Можно добавить реальную логику наличия
                "description": item['description']
            }
            
            ai_context["available_components"].append(component)
            
            # Обновляем статистику
            category = item['type']
            ai_context["inventory_summary"]["categories"][category] = \
                ai_context["inventory_summary"]["categories"].get(category, 0) + 1
            
            # Добавляем производителя
            manufacturer = item['name'].split()[0]
            if manufacturer not in ai_context["search_helpers"]["manufacturers"]:
                ai_context["search_helpers"]["manufacturers"].append(manufacturer)
                
        ai_context["inventory_summary"]["total_items"] = len(components)
        
        return ai_context
        
    finally:
        cursor.close()
        conn.close()

def prepare_data_for_ai():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM components")
        components = cursor.fetchall()
        
        data = {
            "inventory": {
                "components": [],
                "stats": {
                    "total": len(components),
                    "by_type": {}
                }
            }
        }
        
        for item in components:
            component = {
                "name": item['name'],
                "type": item['type'],
                "price": float(item['price']),
                "specs": json.loads(item['specs']),
                "description": item['description']
            }
            
            data["inventory"]["components"].append(component)
            
            # Подсчет статистики
            ctype = item['type']
            if ctype not in data["inventory"]["stats"]["by_type"]:
                data["inventory"]["stats"]["by_type"][ctype] = 0
            data["inventory"]["stats"]["by_type"][ctype] += 1
            
        return data
        
    finally:
        cursor.close()
        conn.close()

def format_component_details(component):
    """Форматирует детали компонента в красивом виде"""
    specs_str = "\n".join([f"  • {key}: {value}" for key, value in component['specs'].items()])
    
    return f"""### {component['name']}
📌 **Тип**: {component['type']}
💰 **Цена**: ${component['price']}
🔧 **Характеристики**:
{specs_str}
📝 **Описание**: {component['description']}
"""

def format_category_header(category):
    icons = {
        "CPU": "🔲",
        "GPU": "🎮",
        "RAM": "🧮",
        "SSD": "💾",
        "HDD": "💿",
        "OTHER": "🔧"
    }
    return f"\n## {icons.get(category, '📦')} {category}\n"

def format_component(component):
    specs_list = "".join([
        f"<li><strong>{key.title()}:</strong> {value}</li>" 
        for key, value in component['specs'].items()
    ])
    
    return f"""
    <div class='component'>
        <h3>{component['name']}</h3>
        <p class='price'>💰 <strong>Цена:</strong> ${component['price']}</p>
        <div class='specs'>
            <h4>📋 Характеристики:</h4>
            <ul>{specs_list}</ul>
        </div>
        <blockquote class='description'>
            <p>📝 {component['description']}</p>
        </blockquote>
    </div>
    """

def format_category(category, components):
    icons = {
        "CPU": "🔲", "GPU": "🎮", "RAM": "🧮",
        "SSD": "💾", "HDD": "💿", "OTHER": "🔧"
    }
    
    formatted = f"<div class='category'><h2>{icons.get(category, '📦')} {category}</h2>"
    for comp in components:
        formatted += format_component(comp)
    formatted += "</div>"
    return formatted

def format_response(components_data):
    """Форматирует ответ с правильной структурой і відступами"""
    response = []
    
    # Заголовок
    response.append("# 🏪 Доступные комплектующие\n")
    
    # Группировка по категориям
    categories = {
        "CPU": ("💻 Процессоры", []),
        "GPU": ("🎮 Видеокарты", []),
        "RAM": ("🧮 Оперативная память", []),
        "SSD": ("💾 Накопители", []),
        "OTHER": ("🔧 Прочее", [])
    }
    
    # Распределение компонентов
    for component in components_data["inventory"]["components"]:
        category = component["type"]
        if category in categories:
            categories[category][1].append(component)
    
    # Форматирование каждой категории
    for cat_key, (cat_name, components) in categories.items():
        if components:
            response.append(f"\n## {cat_name}\н")
            for comp in components:
                response.append(format_component_details(comp))
                response.append("\н---\н")
    
    # Добавление итогов
    response.append("\н### 📊 Общая статистика:\н")
    for cat, count in components_data["inventory"]["stats"]["by_type"].items():
        response.append(f"• {categories.get(cat, (cat,))[0]}: {count}\н")
    
    return "\н".join(response)

def format_component_details(component):
    """Форматирует детали отдельного компонента"""
    return f"""### {component['name']}
💰 **Цена:** ${component['price']}

⚡ **Характеристики:**
{format_specifications(component['specs'])}

📝 **Описание:**
> {component['description']}"""

def format_specifications(specs):
    return "\н".join([f"• {key.title()}: **{value}**" for key, value in specs.items()])

def format_bot_response(components_data):
    response = """
    <div class="bot-response">
        <div class="category-header">
            <h2>🏪 Доступные комплектующие:</h2>
        </div>
    """
    
    categories = {
        "CPU": "💻 Процессоры",
        "GPU": "🎮 Видеокарты",
        "RAM": "🧮 Оперативная память",
        "SSD": "💾 Накопители"
    }
    
    for category, title in categories.items():
        components = [c for c in components_data if c["type"] == category]
        if components:
            response += f"""
                <div class="category-section">
                    <h3>{title}</h3>
                    <div class="components-list">
            """
            
            for comp in components:
                specs = "".join([
                    f'<li><span class="spec-key">{key}:</span> {value}</li>'
                    for key, value in comp["specs"].items()
                ])
                
                response += f"""
                    <div class="component-card">
                        <h4>{comp["name"]}</h4>
                        <p class="price">💰 Цена: ${comp["price"]}</p>
                        <div class="specs">
                            <p>⚡ Характеристики:</p>
                            <ul>{specs}</ul>
                        </div>
                        <p class="description">📝 {comp["description"]}</p>
                    </div>
                """
            
            response += "</div></div>"
    
    response += "</div>"
    return response

# Глобальные переменные для кеширования курсов валют
exchange_rates = {}
last_rates_update = None
UPDATE_INTERVAL = timedelta(hours=1)  # Обновлять курсы каждый час

def update_exchange_rates():
    """Получает актуальные курсы валют через API MonoBank"""
    global exchange_rates, last_rates_update
    
    try:
        # Используем API MonoBank для получения актуальных курсов
        response = requests.get('https://api.monobank.ua/bank/currency')
        if response.status_code == 200:
            rates = response.json()
            exchange_rates = {}
            
            # USD/UAH (840/980)
            usd_rate = next((rate for rate in rates if rate['currencyCodeA'] == 840 and rate['currencyCodeB'] == 980), None)
            # EUR/UAH (978/980)
            eur_rate = next((rate for rate in rates if rate['currencyCodeA'] == 978 and rate['currencyCodeB'] == 980), None)
            
            if usd_rate and eur_rate:
                # Сохраняем курсы
                exchange_rates['USD_UAH'] = usd_rate['rateCross'] if 'rateCross' in usd_rate else usd_rate['rateSell']
                exchange_rates['EUR_UAH'] = eur_rate['rateCross'] if 'rateCross' in eur_rate else eur_rate['rateSell']
                
                # Обратные курсы
                exchange_rates['UAH_USD'] = 1 / exchange_rates['USD_UAH']
                exchange_rates['UAH_EUR'] = 1 / exchange_rates['EUR_UAH']
                
                # Кросс-курс EUR/USD
                exchange_rates['EUR_USD'] = exchange_rates['EUR_UAH'] / exchange_rates['USD_UAH']
                exchange_rates['USD_EUR'] = 1 / exchange_rates['EUR_USD']
                
                last_rates_update = datetime.now()
                print(f"Successfully updated exchange rates at {last_rates_update}: {exchange_rates}")
                return True
            
    except Exception as e:
        print(f"Error updating exchange rates: {e}")
    
    # Если не удалось получить курсы, используем резервные значения
    exchange_rates = {
        'USD_UAH': 41.24,
        'EUR_UAH': 44.72,
        'EUR_USD': 1.08,
        'USD_EUR': 0.92,
        'UAH_USD': 0.024,
        'UAH_EUR': 0.022
    }
    print(f"Using fallback exchange rates: {exchange_rates}")
    return False

def get_current_rates_info():
    """Возвращает строку с информацией о текущих курсах валют"""
    update_exchange_rates()  # Обновляем курсы
    
    if not exchange_rates:
        return "На жаль, не вдалося отримати актуальні курси валют"
    
    return f"""💰 Поточні курси валют:

USD/UAH: {exchange_rates['USD_UAH']:.2f} грн
EUR/UAH: {exchange_rates['EUR_UAH']:.2f} грн
EUR/USD: {exchange_rates['EUR_USD']:.2f}

Останнє оновлення: {last_rates_update.strftime('%Y-%m-%d %H:%М:%S')}"""

def handle_currency_query(message):
    """Обрабатывает запросы о курсах валют"""
    # Более точные ключевые слова для запроса курса
    currency_keywords = [
        'курс валют', 'курс доллара', 'курс євро',
        'вартість доллара', 'вартість євро',
        'поточний курс', 'який курс'
    ]
    return any(keyword in message.lower() for keyword in currency_keywords)

def format_currency_response():
    """Форматирует ответ с курсами валют"""
    if not exchange_rates:
        return "На жаль, не вдалося отримати актуальні курси валют"
    
    try:
        return f"""💰 Поточні курси валют:

1 USD = {exchange_rates['USD_UAH']:.2f} UAH
1 EUR = {exchange_rates['EUR_UAH']:.2f} UAH
1 EUR = {exchange_rates['EUR_USD']:.2f} USD

⏰ Останнє оновлення: {last_rates_update.strftime('%H:%М:%S')}"""
    except Exception as e:
        print(f"Error formatting currency response: {e}")
        return "Помилка форматування курсів валют"

def get_exchange_rate(from_currency, to_currency):
    """Получает актуальный курс валют с автоматическим обновлением"""
    global last_rates_update
    
    # Проверяем, нужно ли обновить курсы
    if not last_rates_update or datetime.now() - last_rates_update > UPDATE_INTERVAL:
        update_exchange_rates()
    
    # Возвращаем курс или значение по умолчанию
    rate_key = f"{from_currency}_{to_currency}"
    return exchange_rates.get(rate_key, 37.5)  # Значение по умолчанию если API недоступен

def format_price(price_usd):
    """Форматирует цену во всех поддерживаемых валютах"""
    usd_price = float(price_usd)
    rates = {
        'UAH': get_exchange_rate('USD', 'UAH'),
        'EUR': get_exchange_rate('USD', 'EUR'),
    }
    
    return f"""💰 ${usd_price:.2f} 
       ≈ {(usd_price * rates['UAH']):.2f} грн
       ≈ {(usd_price * rates['EUR']):.2f} EUR"""

def parse_price_from_text(text):
    """Парсит цену и валюту из текста пользователя"""
    import re
    
    # Паттерны для различных форматов цен (исправлены)
    patterns = {
        'UAH': r'(\д+(?:\с*\д+)*)\с*(?:грн|гривень?|грв|uah|₴)',
        'USD': r'\$?\с*(\д+(?:\с*\д+)*)\с*(?:usd|долларов|доларів|баксов|баксів|\$)',
        'EUR': r'(\д+(?:\с*\д+)*)\с*(?:євро|евро|euro|eur|€)'  # исправлен символ д на d
    }
    
    for currency, pattern in patterns.items():
        if match := re.search(pattern, text, re.IGNORECASE):
            amount = float(match.group(1).replace(' ', ''))
            return amount, currency
    
    return None, None

# Обновляем промпт с информацией о валютах
SYSTEM_PROMPT = """Ви - консультант з комп'ютерних комплектуючих. 
Ви ЗАВЖДИ відповідаєте УКРАЇНСЬКОЮ мовою і підтримуєте контекст розмови.

При запиті на збірку ПК:
1. Враховуйте бюджет користувача
2. Підбирайте сумісні компоненти
3. Вказуйте ціни у всіх валютах (USD, UAH, EUR)
4. Описуйте призначення кожного компонента
5. Додавайте короткі пояснення щодо вибору

{current_rates}

Використовуйте тільки інформацію про товари, яка надана нижче:
{db_content}

Використовуйте емодзі:
💰 - для цін та бюджету
⚡ - для характеристик
💻 - для загальної інформації
🔧 - для сумісності
💡 - для порад та рекомендацій
⚠️ - для важливих зауважень

Якщо перелічуєте комплектуючі, завжди використовуйте HTML-розмітку списку: <ul><li>...</li></ul> для переліків.
"""

# Головна сторінка із чат-інтерфейсом
@app.route('/')
def index():
    """Главная страница с созданием новой сессии"""
    # Генерируем уникальный ID сессии
    session_id = str(uuid.uuid4())
    
    # Создаем новый ответ
    response = make_response(render_template('index.html'))
    
    # Устанавливаем cookie с session_id
    response.set_cookie('session_id', session_id, max_age=86400)  # 24 часа
    
    # Инициализируем историю диалога для новой сессии
    conversation_histories[session_id] = {
        'messages': [],
        'last_activity': datetime.now()
    }
    
    return response

# Добавим словарь приветствий
GREETINGS = {
    "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
    "вітаю", "привіт", "добрий день", "добрий вечір", "добрий ранок", "доброго дня"
}

def extract_budget_from_message(message):
    """Извлекает бюджет и валюту из сообщения пользователя"""
    import re
    
    # Паттерны для разных валют (исправлены)
    patterns = {
        'UAH': r'(\д+(?:\с*\д+)*)\с*(?:грн|гривень?|грв|uah|₴)',
        'USD': r'\$?\с*(\д+(?:\с*\д+)*)\с*(?:usd|долларов|доларів|баксов|баксів|\$)',
        'EUR': r'(\д+(?:\с*\д+)*)\с*(?:євро|евро|euro|eur|€)'  # исправлены символы д на d
    }
    
    for currency, pattern in patterns.items():
        if match := re.search(pattern, message.lower(), re.IGNORECASE):
            amount = float(match.group(1).replace(' ', ''))
            return amount, currency
    
    return None, None

def convert_budget_to_usd(amount, from_currency):
    """Конвертирует бюджет в USD для поиска компонентов"""
    if from_currency == 'USD':
        return amount
    elif from_currency == 'UAH':
        return amount / get_exchange_rate('USD', 'UAH')
    elif from_currency == 'EUR':
        return amount / get_exchange_rate('USD', 'EUR')
    return amount

def format_price_all_currencies(price_usd):
    """Форматирует цену во всех поддерживаемых валютах"""
    rates = {
        'UAH': get_exchange_rate('USD', 'UAH'),
        'EUR': get_exchange_rate('USD', 'EUR')
    }
    
    return f"""💰 ${price_usd:.2f} | {(price_usd * rates['UAH'])::.2f} грн | {(price_usd * rates['EUR'])::.2f} EUR"""

@app.route('/ask', methods=['POST'])
def ask():
    """Обработка запросов с учетом сессий"""
    # Получаем ID сессии из cookie
    session_id = request.cookies.get('session_id')
    user_message = request.form.get('message', '').strip()
    
    # Если сессия не существует или устарела, создаем новую
    if not session_id or session_id not in conversation_histories:
        session_id = str(uuid.uuid4())
        conversation_histories[session_id] = {
            'messages': [],
            'last_activity': datetime.now()
        }
    
    # Обновляем время последней активности
    conversation_histories[session_id]['last_activity'] = datetime.now()
    
    # Очистка старых сессий
    cleanup_old_sessions()
    
    # Получаем историю диалога для текущей сессии
    session_history = conversation_histories[session_id]['messages']
    
    # Проверяем запрос о курсах валют
    if handle_currency_query(user_message):
        update_exchange_rates()
        currency_response = format_currency_response()
        session_history.append({
            "role": "assistant",
            "content": currency_response
        })
        return jsonify({"response": currency_response, "session_id": session_id})
    
    # Обработка приветствий
    if user_message.lower() in GREETINGS:
        greeting_response = "Вітаю! Чим можу допомогти з вибором комп'ютерних комплектуючих?"
        session_history.append({"role": "user", "content": user_message})
        session_history.append({"role": "assistant", "content": greeting_response})
        return jsonify({"response": greeting_response, "session_id": session_id})

    # Извлекаем бюджет из сообщения
    budget, currency = extract_budget_from_message(user_message)
    
    # Добавляем сообщение пользователя в историю
    session_history.append({"role": "user", "content": user_message})
    
    try:
        # Готовим контекст для AI
        db_content = format_db_data_for_ai()
        
        # Если есть бюджет, добавляем информацию о нем
        if budget:
            budget_usd = convert_budget_to_usd(budget, currency)
            user_message += f"\nБюджет: {format_price_all_currencies(budget_usd)}"
        
        # Формируем сообщения для API
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(
                db_content=db_content,
                current_rates=f"Поточні курси валют:\n" +
                            f"USD/UAH: {get_exchange_rate('USD', 'UAH')}\n" +
                            f"USD/EUR: {get_exchange_rate('USD', 'EUR')}"
            )}
        ]
        
        # Добавляем историю диалога
        messages.extend(session_history[-10:])  # Последние 5 пар сообщений
        
        # Получаем ответ от API
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        
        bot_response = response.choices[0].message['content'].strip()
        
        # Сохраняем ответ в историю
        session_history.append({"role": "assistant", "content": bot_response})
        
        # Обрезаем историю если она слишком длинная
        if len(session_history) > 20:  # Храним последние 10 пар сообщений
            conversation_histories[session_id]['messages'] = session_history[-20:]
            
        return jsonify({
            "response": bot_response,
            "session_id": session_id
        })
        
    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({
            "response": "Виникла помилка при обробці запиту. Спробуйте ще раз.",
            "session_id": session_id
        }), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
