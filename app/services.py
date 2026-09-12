from difflib import SequenceMatcher

def normalize_name(value):
    return " ".join((value or "").lower().replace("-", " ").replace("_", " ").split())

def best_product_match(raw_name, products, min_score=0.55):
    raw = normalize_name(raw_name)
    best = None
    score = 0.0
    for product in products:
        candidate = normalize_name(product["name"])
        if raw == candidate:
            return product, 1.0
        current = SequenceMatcher(None, raw, candidate).ratio()
        if raw and (raw in candidate or candidate in raw):
            current = max(current, 0.86)
        if current > score:
            best = product
            score = current
    if best is not None and score >= min_score:
        return best, score
    return None, score

def restock_suggestions(products):
    suggestions = []
    for product in products:
        current = float(product["current_qty"] or 0)
        target = float(product["par_level"] or 0)
        missing = max(0.0, target - current)
        if missing <= 0:
            continue
        ratio = current / target if target > 0 else 1
        if ratio <= 0.25:
            priority = "URGENT"
        elif ratio <= 0.5:
            priority = "HAUTE"
        else:
            priority = "NORMALE"
        suggestions.append({
            "product_id": product["id"],
            "name": product["name"],
            "unit": product["unit"],
            "current": round(current, 2),
            "target": round(target, 2),
            "need": round(missing, 2),
            "priority": priority,
        })
    order = {"URGENT": 0, "HAUTE": 1, "NORMALE": 2}
    suggestions.sort(key=lambda item: (order[item["priority"]], -item["need"]))
    return suggestions

def recipe_score(recipe, ingredients, product_by_id):
    portions = max(1, int(recipe["portions_default"] or 10))
    if not ingredients:
        return 0.0, "Aucun ingrédient configuré"

    coverages = []
    surplus_bonus = 0.0
    limiting = []

    for ingredient in ingredients:
        product = product_by_id.get(ingredient["product_id"])
        if not product:
            continue
        required = float(ingredient["qty_per_portion"]) * portions
        current = float(product["current_qty"] or 0)
        coverage = 1.0 if required <= 0 else min(1.0, current / required)
        coverages.append(coverage)

        if coverage < 1.0:
            limiting.append(product["name"])

        target = float(product["par_level"] or 0)
        if target > 0 and current > target:
            surplus_bonus += min(0.15, ((current - target) / target) * 0.08)

    if not coverages:
        return 0.0, "Ingrédients non reliés"

    feasibility = min(coverages)
    average = sum(coverages) / len(coverages)
    score = min(100.0, (0.7 * feasibility + 0.3 * average + surplus_bonus) * 100)
    reason = "Disponible" if not limiting else "Limité par : " + ", ".join(limiting[:3])
    return round(score, 1), reason

def rank_recipes(recipes, ingredients_by_recipe, products):
    product_by_id = {product["id"]: product for product in products}
    ranked = []
    for recipe in recipes:
        score, reason = recipe_score(
            recipe,
            ingredients_by_recipe.get(recipe["id"], []),
            product_by_id,
        )
        item = dict(recipe)
        item["score"] = score
        item["reason"] = reason
        ranked.append(item)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked
