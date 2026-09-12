from app.db import init_db, db

PRODUCTS = [
    ("Saumon", "Poisson", "kg", 6.0, 12.0, 18.0),
    ("Poulet", "Viande", "kg", 9.0, 10.0, 7.0),
    ("Courgette", "Légumes", "kg", 14.0, 8.0, 2.3),
    ("Champignon", "Légumes", "kg", 8.0, 5.0, 4.0),
    ("Riz", "Épicerie", "kg", 20.0, 12.0, 2.0),
    ("Crème entière", "Crèmerie", "L", 3.0, 8.0, 3.5),
    ("Citron", "Fruits", "kg", 2.0, 3.0, 3.0),
]

def main():
    init_db()
    with db() as conn:
        for product in PRODUCTS:
            conn.execute(
                "INSERT OR IGNORE INTO products(name,category,unit,current_qty,par_level,unit_cost) VALUES(?,?,?,?,?,?)",
                product,
            )
    print("Données de démonstration ajoutées.")

if __name__ == "__main__":
    main()
