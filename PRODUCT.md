# KitchenOps — Spécification v1

## Utilisateur principal
Chef de cuisine, second, responsable approvisionnement.

## Modules
- tableau de bord du jour ;
- inventaire et niveaux cibles ;
- scan photo bon de commande / bon de livraison / facture ;
- archive automatique des documents ;
- réception contrôlée du stock ;
- scan ponctuel chambre froide ;
- simulation de réassort à partir du stock observé ;
- carte, plats du jour et repas du personnel définis par le chef ;
- classement automatique des recettes selon la disponibilité des ingrédients ;
- historique des mouvements ;
- interface responsive installable comme PWA sur tablette.

## Règle de stock

stock_estime = stock_enregistre + receptions - consommations - pertes +/- ajustements

La photo ne remplace pas cette logique. Lorsqu'une observation est validée :

ajustement = quantite_observee - stock_enregistre

## Règle des plats

CARTE, PLAT_DU_JOUR et PERSONNEL sont trois ensembles distincts définis par le chef.
KitchenOps peut classer ces plats, mais ne peut pas en créer un nouveau sans enregistrement préalable du chef.

## Caméra fixe

Une caméra IP PoE pourra produire périodiquement le même type d'observation qu'une photo tablette.
La v1 n'en dépend pas afin de réduire coût, complexité et questions de surveillance des salariés.
