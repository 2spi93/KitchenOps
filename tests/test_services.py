from app.services import best_product_match, restock_suggestions, recipe_score

def test_restock_suggestions():
    products = [
        {"id": 1, "name": "Saumon", "unit": "kg", "current_qty": 2, "par_level": 10},
        {"id": 2, "name": "Riz", "unit": "kg", "current_qty": 20, "par_level": 10},
    ]
    result = restock_suggestions(products)
    assert len(result) == 1
    assert result[0]["name"] == "Saumon"
    assert result[0]["need"] == 8

def test_product_match():
    products = [{"id": 1, "name": "Crème entière", "unit": "L"}]
    product, score = best_product_match("creme entiere", products, min_score=0.4)
    assert product["id"] == 1
    assert score >= 0.4

def test_recipe_score():
    recipe = {"id": 1, "portions_default": 10}
    ingredients = [{"product_id": 1, "qty_per_portion": 0.2}]
    products = {
        1: {"id": 1, "name": "Poulet", "current_qty": 3, "par_level": 2}
    }
    score, reason = recipe_score(recipe, ingredients, products)
    assert score > 80
    assert reason == "Disponible"
