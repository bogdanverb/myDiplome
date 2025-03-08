# app.py
from flask import Flask, render_template, request, jsonify, url_for
import mysql.connector
import openai
import json
from config import MYSQL_CONFIG, OPENAI_API_KEY

app = Flask(__name__, static_folder='static', template_folder='templates')

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
    # Добавить логику для других типов компонентов
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
            response.append(f"\n## {cat_name}\n")
            for comp in components:
                response.append(format_component_details(comp))
                response.append("\n---\n")
    
    # Добавление итогов
    response.append("\n### 📊 Общая статистика:\n")
    for cat, count in components_data["inventory"]["stats"]["by_type"].items():
        response.append(f"• {categories.get(cat, (cat,))[0]}: {count}\n")
    
    return "\n".join(response)

def format_component_details(component):
    """Форматирует детали отдельного компонента"""
    return f"""### {component['name']}
💰 **Цена:** ${component['price']}

⚡ **Характеристики:**
{format_specifications(component['specs'])}

📝 **Описание:**
> {component['description']}"""

def format_specifications(specs):
    return "\n".join([f"• {key.title()}: **{value}**" for key, value in specs.items()])

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

def format_db_to_text():
    """Форматирует все данные из БД в текстовый формат для ИИ"""
    data = prepare_data_for_ai()
    text = "Доступные компьютерные комплектующие:\n\n"
    
    # Группируем по категориям
    categories = {}
    for comp in data["inventory"]["components"]:
        cat = comp["type"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(comp)
    
    # Форматируем каждую категорию
    for cat, components in categories.items():
        text += f"\n{cat}:\n"
        for comp in components:
            text += f"""- {comp['name']}
  Цена: ${comp['price']}
  Характеристики: {', '.join([f'{k}: {v}' for k, v in comp['specs'].items()])}
  Описание: {comp['description']}\n"""
    
    return text

# Головна сторінка із чат-інтерфейсом
@app.route('/')
def index():
    return render_template('index.html')

SYSTEM_PROMPT = """Вы - консультант по компьютерным комплектующим. Используйте только информацию о товарах, которая предоставлена ниже.

{db_content}

Ваши задачи:
1. Отвечать на вопросы о наличии и характеристиках товаров из списка выше
2. Если пользователь спрашивает о конкретной категории товаров - показывать все товары этой категории
3. Если запрос неясен - уточнять детали
4. Если товара нет в списке - сообщать об этом
5. Всегда форматировать ответы с использованием HTML

Используйте эмодзи:
💻 - для общей информации
💰 - для цен
⚡ - для характеристик
📝 - для описаний"""

@app.route('/ask', methods=['POST'])
def ask():
    user_message = request.form.get('message').strip()
    
    # Форматируем данные из БД для ИИ
    db_content = format_db_to_text()
    
    # Формируем промпт с актуальными данными
    current_prompt = SYSTEM_PROMPT.format(db_content=db_content)
    
    messages = [
        {"role": "system", "content": current_prompt},
        {"role": "user", "content": f"Найди и покажи товары по запросу: {user_message}"}
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        bot_response = response.choices[0].message['content'].strip()
        
        # Если ответ пустой или содержит "не найдено"
        if not bot_response or "не найдено" in bot_response.lower():
            bot_response = "К сожалению, по вашему запросу ничего не найдено в базе данных"
            
    except Exception as e:
        bot_response = f"Произошла ошибка: {e}"

    return jsonify({
        "response": bot_response
    })

if __name__ == '__main__':
    app.run(debug=True)