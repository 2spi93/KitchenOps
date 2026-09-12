import base64
import json
import os
from pathlib import Path

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

def _client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key)

def _data_url(path):
    path = Path(path)
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:" + mime + ";base64," + encoded

def _parse_json(text):
    text = (text or "").strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = text.replace(fence + "json", "", 1).replace(fence, "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)

def _error_result(kind, message):
    if kind == "order":
        return {
            "configured": True,
            "error": True,
            "message": message,
            "document_type": "AUTRE",
            "supplier": "",
            "reference": "",
            "date": "",
            "total": None,
            "lines": [],
        }
    return {
        "configured": True,
        "error": True,
        "message": message,
        "observed": [],
        "unknown": [],
        "warnings": ["Analyse non appliquée : vérification manuelle nécessaire."],
    }

def analyze_order_document(image_path, catalog):
    client = _client()
    if client is None:
        return {
            "configured": False,
            "message": "OPENAI_API_KEY absente : analyse IA désactivée.",
            "document_type": "BON_COMMANDE",
            "supplier": "",
            "reference": "",
            "date": "",
            "total": None,
            "lines": [],
        }

    catalog_text = "\n".join(
        '- id={}; nom="{}"; unite="{}"'.format(p["id"], p["name"], p["unit"])
        for p in catalog[:500]
    )

    prompt = """
Tu extrais un document d'approvisionnement de restaurant photographié avec une tablette.
Réponds UNIQUEMENT en JSON valide, sans markdown.

Catalogue interne:
{}

Schéma JSON attendu:
{{
  "configured": true,
  "document_type": "BON_COMMANDE|BON_LIVRAISON|FACTURE|AUTRE",
  "supplier": "string",
  "reference": "string",
  "date": "YYYY-MM-DD ou chaine vide",
  "total": null,
  "lines": [
    {{
      "raw_name": "nom lu sur le document",
      "catalog_product_id": null,
      "qty": 1.0,
      "unit": "kg|L|u|carton|...",
      "unit_price": null,
      "confidence": 0.0
    }}
  ]
}}

Règles:
- Ne devine pas une ligne illisible.
- catalog_product_id doit rester null si la correspondance n'est pas raisonnablement certaine.
- unit_price et total peuvent être null.
- Ne transforme jamais un bon de commande en réception de stock.
- Garde les unités réellement visibles.
""".format(catalog_text)

    try:
        response = client.responses.create(
            model=MODEL,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": _data_url(image_path)},
                ],
            }],
        )
        return _parse_json(response.output_text)
    except Exception:
        return _error_result(
            "order",
            "L'analyse IA du document a échoué. Le document reste archivé et doit être saisi ou rescanné.",
        )

def analyze_cold_room(image_path, catalog):
    client = _client()
    if client is None:
        return {
            "configured": False,
            "message": "OPENAI_API_KEY absente : analyse IA désactivée.",
            "observed": [],
            "unknown": [],
            "warnings": [],
        }

    catalog_text = "\n".join(
        '- id={}; nom="{}"; unite="{}"; stock_enregistre={}; cible={}'.format(
            p["id"], p["name"], p["unit"], p["current_qty"], p["par_level"]
        )
        for p in catalog[:500]
    )

    prompt = """
Tu analyses UNE photo ponctuelle d'une chambre froide de restaurant.
Tu estimes uniquement ce qui est réellement visible.
Réponds UNIQUEMENT en JSON valide, sans markdown.

Catalogue:
{}

Schéma:
{{
  "configured": true,
  "observed": [
    {{
      "catalog_product_id": null,
      "name": "string",
      "estimated_qty": 1.0,
      "unit": "string",
      "confidence": 0.0,
      "basis": "3 bacs visibles, 2 cartons, niveau approximatif"
    }}
  ],
  "unknown": ["produits visibles non rapprochés"],
  "warnings": ["zones cachées ou quantité non mesurable"]
}}

Règles:
- Si le poids ou le volume n'est pas réellement inférable, baisse fortement confidence.
- Ne prétends jamais voir derrière un carton ou dans un bac opaque.
- Ignore entièrement les personnes.
- N'identifie ni visage ni caractéristique personnelle.
- Utilise catalog_product_id=null quand le rapprochement n'est pas fiable.
""".format(catalog_text)

    try:
        response = client.responses.create(
            model=MODEL,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": _data_url(image_path)},
                ],
            }],
        )
        return _parse_json(response.output_text)
    except Exception:
        return _error_result(
            "cold",
            "L'analyse IA de la chambre froide a échoué. Le stock n'a pas été modifié.",
        )
