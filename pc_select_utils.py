def select_components_for_budget(db_content, budget, currency):
    """
    Підбирає найдорожчі компоненти по категоріях, щоб сума була максимально близька до бюджету, але не перевищувала його.
    """
    if not budget:
        return None, 0
    # Перетворити бюджет у USD
    # ... тут має бути логіка конвертації ...
    budget_usd = budget if not currency or currency == 'USD' else budget  # спрощено
    categories = ["cpu", "gpu", "ram", "storage", "motherboard", "cooler"]
    selected = []
    total = 0
    for cat in categories:
        comps = db_content["components_catalog"].get(cat, [])
        if comps:
            # Вибрати найдорожчий, який не перевищує залишок бюджету
            comps_sorted = sorted(comps, key=lambda x: -x["price"])
            for comp in comps_sorted:
                if total + comp["price"] <= budget_usd:
                    selected.append(comp)
                    total += comp["price"]
                    break
    return selected, total

def format_selected_pc_response(components, total_price, budget):
    """
    Форматує відповідь для підібраної збірки ПК (HTML-список, абзаци, emoji)
    """
    lines = [
        "<h2>🔧 Ваша збірка ПК</h2>",
        "<ul>"
    ]
    for comp in components:
        lines.append(f"<li><strong>{comp['type']}:</strong> {comp['name']} 💰 ${comp['price']}<br>📝 {comp['description']}</li>")
    lines.append("</ul>")
    lines.append(f"<p><strong>Загальна вартість:</strong> 💰 ${total_price} (бюджет: ${budget})</p>")
    if total_price < budget * 0.9:
        lines.append("<p>⚠️ Залишок бюджету: ${:.2f}. Можна додати додаткові компоненти або аксесуари.</p>".format(budget-total_price))
    return "\n".join(lines)