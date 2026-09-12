# Sécurité et vie privée — v1

## Principes
- aucune reconnaissance faciale ;
- aucune biométrie ;
- aucun audio ;
- les photos sont recompressées côté serveur afin de réduire la taille et d'éliminer la majorité des métadonnées EXIF ;
- les images ne sont accessibles qu'à travers une route nécessitant une session ;
- cookie de session HttpOnly et SameSite=Lax ;
- limite de taille des images configurable ;
- durée de conservation configurable.

## Caméra fixe
Avant d'installer une caméra fixe dans une chambre froide :
- cadrer principalement les rayons et marchandises ;
- éviter autant que possible de filmer les salariés ;
- documenter la finalité ;
- informer les personnes concernées ;
- faire vérifier les obligations applicables au restaurant ;
- ne conserver aucune vidéo continue si une capture ponctuelle suffit au besoin métier.

## Production
Le PIN partagé est acceptable uniquement pour un premier pilote contrôlé.
Avant plusieurs établissements ou plusieurs niveaux d'accès, utiliser des comptes individuels, journalisation des actions et rôles.
