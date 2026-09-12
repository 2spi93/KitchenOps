# KitchenOps v1

KitchenOps est un MVP tablette pour restaurant : inventaire, analyse IA de bons de commande / bons de livraison, analyse ponctuelle de la chambre froide par photo, propositions de réassort et classement de plats pré-approuvés par le chef.

## Décisions produit

- Pas de caméra fixe obligatoire au lancement.
- La tablette peut prendre directement une photo avec la caméra arrière.
- Un bon fournisseur photographié est enregistré automatiquement comme brouillon.
- Le stock n'augmente qu'après confirmation de réception réelle.
- Une photo de chambre froide donne une estimation du visible et une simulation avant validation.
- L'IA ne crée jamais librement la carte : elle classe uniquement des recettes configurées par le chef.
- La vision est un outil de réconciliation, pas une mesure garantie du poids caché dans des cartons ou bacs opaques.

## Démarrage

1. Copier .env.example vers .env.
2. Modifier APP_SECRET et ADMIN_PIN.
3. Ajouter OPENAI_API_KEY pour activer la vision.
4. Lancer docker compose up --build -d.
5. Ouvrir http://localhost:8080.
6. Ajouter les produits, les niveaux cibles et les recettes du chef.

Pour charger des exemples :
docker compose exec kitchenops python seed_demo.py

## Workflow quotidien

Réception fournisseur :
- prendre une photo du bon de commande, BL ou facture ;
- KitchenOps extrait les lignes et archive le document ;
- vérifier les correspondances ;
- confirmer Réceptionner uniquement si les marchandises sont physiquement arrivées.

Chambre froide :
- prendre une ou plusieurs photos couvrant les rayons ;
- KitchenOps estime uniquement ce qui est visible ;
- avant toute modification du stock, l'écran simule :
  - ce qu'il resterait à commander ;
  - le meilleur repas du personnel parmi les recettes autorisées ;
  - le meilleur plat du jour parmi les recettes autorisées ;
  - les plats de carte les plus faisables ;
- le chef valide ou ignore la photo.

## Mise en production

Le conteneur est prévu pour être placé derrière un reverse proxy HTTPS tel que Caddy, Nginx ou Traefik.
En production :
- APP_SECRET doit être long et aléatoire ;
- COOKIE_SECURE=true doit être ajouté à l'environnement ;
- le dossier data doit être sauvegardé quotidiennement ;
- la politique de conservation des photos doit être configurée ;
- un compte individuel par utilisateur devra remplacer le PIN partagé avant un déploiement multi-restaurant.

## Évolution prévue après le pilote

La caméra IP PoE fixe est un module phase 2. Elle ne doit être ajoutée que si les photos tablette prouvent que la vision apporte une valeur mesurable.
