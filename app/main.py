import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps

from .db import init_db, db
from .services import restock_suggestions, rank_recipes, best_product_match
from .ai import analyze_order_document, analyze_cold_room

BASE = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE.parent / "data" / "uploads")))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "12"))
APP_SECRET = os.getenv("APP_SECRET", "dev-change-me")
ADMIN_PIN = os.getenv("ADMIN_PIN", "2468")
APP_NAME = os.getenv("APP_NAME", "KitchenOps")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_APPLY_THRESHOLD", "0.60"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
PHOTO_RETENTION_DAYS = int(os.getenv("PHOTO_RETENTION_DAYS", "30"))

app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

@app.on_event("startup")
def startup():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    cleanup_old_uploads()

def cleanup_old_uploads():
    if PHOTO_RETENTION_DAYS <= 0:
        return
    cutoff = time.time() - PHOTO_RETENTION_DAYS * 86400
    for item in UPLOAD_DIR.glob("*.jpg"):
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
        except OSError:
            pass

def _sign(payload):
    return hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

def make_session():
    expires = int(time.time()) + 60 * 60 * 12
    payload = str(expires) + "." + secrets.token_hex(8)
    return payload + "." + _sign(payload)

def valid_session(token):
    try:
        if not token:
            return False
        expires, nonce, signature = token.split(".", 2)
        payload = expires + "." + nonce
        return hmac.compare_digest(signature, _sign(payload)) and int(expires) > time.time()
    except Exception:
        return False

def require_login(request):
    if not valid_session(request.cookies.get("kops_session")):
        raise HTTPException(status_code=401)

def page(request, template, **context):
    values = {"request": request, "app_name": APP_NAME}
    values.update(context)
    return templates.TemplateResponse(template, values)

def rows(sql, args=()):
    with db() as conn:
        return [dict(item) for item in conn.execute(sql, args).fetchall()]

def row(sql, args=()):
    with db() as conn:
        item = conn.execute(sql, args).fetchone()
        return dict(item) if item else None

def inventory_snapshot():
    return rows("SELECT * FROM products WHERE active=1 ORDER BY category, name")

def ingredient_map():
    items = rows("SELECT * FROM recipe_ingredients")
    grouped = {}
    for item in items:
        grouped.setdefault(item["recipe_id"], []).append(item)
    return grouped

def all_recipes():
    return rows("SELECT * FROM recipes WHERE active=1 AND approved=1 ORDER BY kind, name")

def save_upload(upload):
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(400, "Le fichier doit être une image.")

    raw = upload.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "Image trop volumineuse.")

    temp = UPLOAD_DIR / ("tmp-" + secrets.token_hex(8))
    final = UPLOAD_DIR / (str(int(time.time())) + "-" + secrets.token_hex(6) + ".jpg")
    temp.write_bytes(raw)

    try:
        with Image.open(temp) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1800, 1800))
            image.save(final, "JPEG", quality=82, optimize=True)
    except Exception as exc:
        raise HTTPException(400, "Image illisible.") from exc
    finally:
        temp.unlink(missing_ok=True)

    return final

def apply_delta(product_id, delta, event_type, source, note=""):
    with db() as conn:
        product = conn.execute(
            "SELECT current_qty FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
        if not product:
            return

        after = max(0.0, float(product["current_qty"]) + float(delta))
        conn.execute(
            "UPDATE products SET current_qty=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (after, product_id),
        )
        conn.execute(
            "INSERT INTO inventory_events(product_id,event_type,qty_delta,absolute_after,source,note) VALUES(?,?,?,?,?,?)",
            (product_id, event_type, delta, after, source, note),
        )

def set_absolute(product_id, absolute, source, note=""):
    with db() as conn:
        product = conn.execute(
            "SELECT current_qty FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
        if not product:
            return

        before = float(product["current_qty"])
        after = max(0.0, float(absolute))
        delta = after - before

        conn.execute(
            "UPDATE products SET current_qty=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (after, product_id),
        )
        conn.execute(
            "INSERT INTO inventory_events(product_id,event_type,qty_delta,absolute_after,source,note) VALUES(?,?,?,?,?,?)",
            (product_id, "PHOTO_RECONCILIATION", delta, after, source, note),
        )

def projected_products_from_scan(result):
    products = inventory_snapshot()
    projected = [dict(product) for product in products]
    by_id = {product["id"]: product for product in projected}

    for observation in result.get("observed", []):
        product_id = observation.get("catalog_product_id")
        quantity = observation.get("estimated_qty")
        confidence = float(observation.get("confidence") or 0)
        if (
            product_id in by_id
            and quantity is not None
            and confidence >= CONFIDENCE_THRESHOLD
        ):
            by_id[product_id]["current_qty"] = max(0.0, float(quantity))

    return projected

@app.exception_handler(401)
async def unauthorized_handler(request, exc):
    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return page(request, "login.html", error=None)

@app.post("/login")
def login_post(request: Request, pin: str = Form(...)):
    if not hmac.compare_digest(pin, ADMIN_PIN):
        return page(request, "login.html", error="PIN incorrect.")

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "kops_session",
        make_session(),
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        max_age=60 * 60 * 12,
    )
    return response

@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("kops_session")
    return response

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    require_login(request)
    products = inventory_snapshot()
    ranked = rank_recipes(all_recipes(), ingredient_map(), products)
    grouped = {
        kind: [recipe for recipe in ranked if recipe["kind"] == kind][:3]
        for kind in ("PLAT_DU_JOUR", "PERSONNEL", "CARTE")
    }
    return page(
        request,
        "dashboard.html",
        restock=restock_suggestions(products)[:12],
        grouped=grouped,
        recent_scans=rows("SELECT * FROM scans ORDER BY id DESC LIMIT 6"),
    )

@app.get("/inventory", response_class=HTMLResponse)
def inventory(request: Request):
    require_login(request)
    return page(
        request,
        "inventory.html",
        products=inventory_snapshot(),
        events=rows(
            """
            SELECT e.*, p.name AS product_name, p.unit AS unit
            FROM inventory_events e
            JOIN products p ON p.id=e.product_id
            ORDER BY e.id DESC
            LIMIT 40
            """
        ),
    )

@app.post("/inventory/product")
def add_product(
    request: Request,
    name: str = Form(...),
    category: str = Form("Autre"),
    unit: str = Form("u"),
    current_qty: float = Form(0),
    par_level: float = Form(0),
    unit_cost: float = Form(0),
):
    require_login(request)
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO products(name,category,unit,current_qty,par_level,unit_cost) VALUES(?,?,?,?,?,?)",
                (
                    name.strip(),
                    category.strip() or "Autre",
                    unit.strip() or "u",
                    max(0, current_qty),
                    max(0, par_level),
                    max(0, unit_cost),
                ),
            )
    except Exception as exc:
        raise HTTPException(400, "Produit déjà existant ou données invalides.") from exc
    return RedirectResponse("/inventory", status_code=303)

@app.post("/inventory/{product_id}/adjust")
def adjust_inventory(
    request: Request,
    product_id: int,
    absolute_qty: float = Form(...),
    note: str = Form(""),
):
    require_login(request)
    set_absolute(product_id, absolute_qty, "manual", note or "Ajustement manuel")
    return RedirectResponse("/inventory", status_code=303)

@app.get("/recipes", response_class=HTMLResponse)
def recipes_get(request: Request):
    require_login(request)
    recipes = rows("SELECT * FROM recipes WHERE active=1 ORDER BY kind, name")
    ingredients = rows(
        """
        SELECT ri.*, p.name AS product_name, p.unit AS unit
        FROM recipe_ingredients ri
        JOIN products p ON p.id=ri.product_id
        ORDER BY ri.recipe_id, p.name
        """
    )
    grouped = {}
    for ingredient in ingredients:
        grouped.setdefault(ingredient["recipe_id"], []).append(ingredient)

    return page(
        request,
        "recipes.html",
        recipes=recipes,
        ingredients=grouped,
        products=inventory_snapshot(),
    )

@app.post("/recipes")
def add_recipe(
    request: Request,
    name: str = Form(...),
    kind: str = Form(...),
    portions_default: int = Form(10),
    notes: str = Form(""),
    ingredients_text: str = Form(""),
):
    require_login(request)
    if kind not in {"CARTE", "PLAT_DU_JOUR", "PERSONNEL"}:
        raise HTTPException(400, "Type de recette invalide.")

    products = inventory_snapshot()
    product_by_name = {product["name"].lower(): product for product in products}

    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO recipes(name,kind,portions_default,notes) VALUES(?,?,?,?)",
            (name.strip(), kind, max(1, portions_default), notes.strip()),
        )
        recipe_id = cursor.lastrowid

        for segment in ingredients_text.split(";"):
            segment = segment.strip()
            if not segment or ":" not in segment:
                continue
            product_name, raw_qty = segment.rsplit(":", 1)
            product = product_by_name.get(product_name.strip().lower())
            if not product:
                continue
            try:
                quantity = float(raw_qty.replace(",", ".").strip())
            except ValueError:
                continue
            if quantity <= 0:
                continue
            conn.execute(
                "INSERT INTO recipe_ingredients(recipe_id,product_id,qty_per_portion) VALUES(?,?,?)",
                (recipe_id, product["id"], quantity),
            )

    return RedirectResponse("/recipes", status_code=303)

@app.get("/scan", response_class=HTMLResponse)
def scan_get(request: Request):
    require_login(request)
    return page(
        request,
        "scan.html",
        scans=rows("SELECT * FROM scans ORDER BY id DESC LIMIT 30"),
    )

@app.post("/scan/order")
def scan_order(request: Request, photo: UploadFile = File(...)):
    require_login(request)
    image_path = save_upload(photo)
    products = inventory_snapshot()
    result = analyze_order_document(image_path, products)

    for line in result.get("lines", []):
        if not line.get("catalog_product_id"):
            match, score = best_product_match(line.get("raw_name", ""), products)
            if match:
                line["catalog_product_id"] = match["id"]
                line["confidence"] = max(float(line.get("confidence") or 0), score)

    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO scans(scan_type,image_name,status,result_json) VALUES('ORDER_DOC',?,'RECORDED',?)",
            (image_path.name, json.dumps(result, ensure_ascii=False)),
        )
        scan_id = cursor.lastrowid

        po_cursor = conn.execute(
            """
            INSERT INTO purchase_orders(
                scan_id,supplier,document_type,reference,document_date,total,received
            ) VALUES(?,?,?,?,?,?,0)
            """,
            (
                scan_id,
                result.get("supplier", ""),
                result.get("document_type", "BON_COMMANDE"),
                result.get("reference", ""),
                result.get("date", ""),
                result.get("total"),
            ),
        )
        purchase_order_id = po_cursor.lastrowid

        for line in result.get("lines", []):
            conn.execute(
                """
                INSERT INTO purchase_order_lines(
                    purchase_order_id,product_id,raw_name,qty,unit,unit_price,confidence
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    purchase_order_id,
                    line.get("catalog_product_id"),
                    line.get("raw_name", ""),
                    float(line.get("qty") or 0),
                    line.get("unit", ""),
                    line.get("unit_price"),
                    float(line.get("confidence") or 0),
                ),
            )

    return RedirectResponse("/scan/" + str(scan_id), status_code=303)

@app.post("/scan/cold-room")
def scan_cold_room(request: Request, photo: UploadFile = File(...)):
    require_login(request)
    image_path = save_upload(photo)
    result = analyze_cold_room(image_path, inventory_snapshot())

    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO scans(scan_type,image_name,result_json) VALUES('COLD_ROOM',?,?)",
            (image_path.name, json.dumps(result, ensure_ascii=False)),
        )
        scan_id = cursor.lastrowid

    return RedirectResponse("/scan/" + str(scan_id), status_code=303)

@app.get("/scan/{scan_id}", response_class=HTMLResponse)
def scan_review(request: Request, scan_id: int):
    require_login(request)
    scan = row("SELECT * FROM scans WHERE id=?", (scan_id,))
    if not scan:
        raise HTTPException(404)

    result = json.loads(scan["result_json"] or "{}")
    products = inventory_snapshot()
    product_map = {product["id"]: product for product in products}
    projected_restock = []
    projected_grouped = {}

    if scan["scan_type"] == "COLD_ROOM":
        projected = projected_products_from_scan(result)
        projected_restock = restock_suggestions(projected)[:12]
        ranked = rank_recipes(all_recipes(), ingredient_map(), projected)
        projected_grouped = {
            kind: [recipe for recipe in ranked if recipe["kind"] == kind][:3]
            for kind in ("PLAT_DU_JOUR", "PERSONNEL", "CARTE")
        }

    purchase_order = None
    if scan["scan_type"] == "ORDER_DOC":
        purchase_order = row(
            "SELECT * FROM purchase_orders WHERE scan_id=? ORDER BY id DESC LIMIT 1",
            (scan_id,),
        )

    return page(
        request,
        "scan_review.html",
        scan=scan,
        result=result,
        pmap=product_map,
        threshold=CONFIDENCE_THRESHOLD,
        restock=projected_restock,
        grouped=projected_grouped,
        purchase_order=purchase_order,
    )

@app.post("/scan/{scan_id}/receive-order")
def receive_order(
    request: Request,
    scan_id: int,
    confirm: Optional[str] = Form(None),
):
    require_login(request)
    if confirm != "yes":
        return RedirectResponse("/scan/" + str(scan_id), status_code=303)

    scan = row("SELECT * FROM scans WHERE id=?", (scan_id,))
    purchase_order = row(
        "SELECT * FROM purchase_orders WHERE scan_id=? ORDER BY id DESC LIMIT 1",
        (scan_id,),
    )
    if not scan or not purchase_order:
        raise HTTPException(404)

    if int(purchase_order["received"] or 0) == 1:
        return RedirectResponse("/scan/" + str(scan_id), status_code=303)

    lines = rows(
        "SELECT * FROM purchase_order_lines WHERE purchase_order_id=?",
        (purchase_order["id"],),
    )

    for line in lines:
        product_id = line.get("product_id")
        quantity = float(line.get("qty") or 0)
        confidence = float(line.get("confidence") or 0)
        if product_id and quantity > 0 and confidence >= CONFIDENCE_THRESHOLD:
            apply_delta(
                product_id,
                quantity,
                "DELIVERY",
                "order-scan:" + str(scan_id),
                "Réception document " + str(purchase_order.get("reference") or ""),
            )

    with db() as conn:
        conn.execute(
            "UPDATE purchase_orders SET received=1 WHERE id=?",
            (purchase_order["id"],),
        )
        conn.execute(
            "UPDATE scans SET status='RECEIVED' WHERE id=?",
            (scan_id,),
        )

    return RedirectResponse("/", status_code=303)

@app.post("/scan/{scan_id}/apply-cold-room")
def apply_cold_room(
    request: Request,
    scan_id: int,
    confirm: Optional[str] = Form(None),
):
    require_login(request)
    if confirm != "yes":
        return RedirectResponse("/scan/" + str(scan_id), status_code=303)

    scan = row("SELECT * FROM scans WHERE id=?", (scan_id,))
    if not scan or scan["scan_type"] != "COLD_ROOM":
        raise HTTPException(404)

    result = json.loads(scan["result_json"] or "{}")
    for observation in result.get("observed", []):
        product_id = observation.get("catalog_product_id")
        quantity = observation.get("estimated_qty")
        confidence = float(observation.get("confidence") or 0)

        if (
            product_id
            and quantity is not None
            and confidence >= CONFIDENCE_THRESHOLD
        ):
            set_absolute(
                product_id,
                float(quantity),
                "cold-room:" + str(scan_id),
                observation.get("basis", "Observation photo"),
            )

    with db() as conn:
        conn.execute(
            "UPDATE scans SET status='APPLIED' WHERE id=?",
            (scan_id,),
        )

    return RedirectResponse("/", status_code=303)

@app.get("/media/{image_name}")
def media(request: Request, image_name: str):
    require_login(request)
    safe_name = Path(image_name).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)

@app.get("/health")
def health():
    return {"status": "ok", "app": APP_NAME}
