# Lot 4.4, expérience F : couverture avant entraînement

**Statut : diagnostic de couverture terminé, aucun modèle F entraîné.** F ajouterait à D une seule variable, le nombre de transactions antérieures où le compte actuel apparaît comme `nameOrig`. E et son ratio ne sont pas ajoutés. Les résultats ci-dessous concernent seulement les steps 1 à 504 ; aucun label ni score du test final n'a été lu pour ce diagnostic.

## Méthode

Le CSV est projeté sur `step` et `nameOrig`. Les transactions sont regroupées par compte et par step, sans supprimer les doublons apparents. Pour une transaction au step `t`, le compteur est la somme des effectifs de ce même émetteur aux steps strictement inférieurs à `t`. Toutes les transactions du même step reçoivent donc le même compteur préalable. L'ordre des lignes dans un step ne sert jamais de chronologie. Le compte qui n'apparaît pas auparavant reçoit zéro.

Le regroupement permet une vérification simple de la règle temporelle. Une alternative serait un parcours step par step avec un dictionnaire de compteurs, en mettant les compteurs à jour après chaque step ; ce parcours pourrait demander moins de mémoire, mais doit préserver exactement la même règle. Le calcul publié n'utilise aucun `nameDest`, label, montant, solde ou prédiction. Les identifiants ne sont pas enregistrés dans les résultats publiés.

## Couverture globale et distribution

Sur les **6 064 036** transactions des steps 1 à 504, **8 438** ont un compteur non nul, soit **0,1391 %**. Les autres **6 055 598** ont zéro. La distribution pondérée par transactions est :

| Compteur antérieur | Transactions |
| --- | ---: |
| 0 | 6 055 598 |
| 1 | 8 425 |
| 2 | 13 |
| 3 ou plus | 0 |

Le maximum observé est **2** et la moyenne sur toutes les transactions est **0,001394**. Cette moyenne inclut les zéros. Le zéro signifie seulement qu'aucune émission antérieure du compte n'est observée depuis le début du fichier disponible ; il ne prouve pas que le compte n'a jamais effectué d'autre opération.

## Couverture par fenêtre chronologique

Les entraînements croissants se recouvrent. Les réserves et validations correspondent aux trois portions fixées par le protocole. Le pourcentage est `transactions avec compteur > 0 / toutes les transactions de la portion`, sans pondération par compte distinct.

| Fenêtre | Apprentissage : non nul / total | Taux | Réserve : non nul / total | Taux | Validation : non nul / total | Taux |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 240 / 1 030 563 | 0,0233 % | 277 / 479 034 | 0,0578 % | 1 305 / 1 288 139 | 0,1013 % |
| 2 | 517 / 1 509 597 | 0,0342 % | 1 305 / 1 288 139 | 0,1013 % | 1 805 / 1 160 580 | 0,1555 % |
| 3 | 1 822 / 2 797 736 | 0,0651 % | 1 805 / 1 160 580 | 0,1555 % | 2 610 / 1 227 741 | 0,2126 % |
| 4 | 3 627 / 3 958 316 | 0,0916 % | 2 610 / 1 227 741 | 0,2126 % | 2 060 / 822 359 | 0,2505 % |
| 5 | 6 237 / 5 186 057 | 0,1203 % | 2 060 / 822 359 | 0,2505 % | 141 / 55 620 | 0,2535 % |

Les cinq validations sont disjointes. Parmi elles, le compteur vaut 2 pour respectivement **2, 1, 5, 4 et 0** transactions ; toutes les autres valeurs non nulles valent 1. La cinquième validation est bien plus petite que les autres. Le taux de couverture augmente au fil du temps, ce qui est attendu pour un compteur cumulatif, mais reste au plus **0,2535 %** dans ces validations. Cela ne renseigne pas encore sur l'utilité prédictive des rares lignes concernées.

## Vérifications et limites

Le SHA-256 du CSV est `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`. Les 504 steps, 6 064 036 transactions, effectifs des trois portions de chaque fenêtre et sommes des tranches de compteur sont contrôlés. Les tests synthétiques vérifient compte nouveau, compte déjà vu, doublons, exclusion du même step et du futur, invariance à l'ordre des lignes, et rejet d'une colonne destinataire ou label. Le calcul a été exécuté sur macOS Apple Silicon avec Python 3.11.15 et Polars 1.44.2. Il a pris **3,77 s** ; la mémoire résidente relevée après regroupement était **2,16 Gio**, ce qui n'est pas un pic mesuré en continu. La commande générique `uv run --locked`, Linux et Windows n'ont pas été testés pour ce diagnostic.

Le [résultat structuré](results/ml_sender_history_coverage.json) fournit les effectifs et tranches de chaque portion. Pour le reproduire depuis la racine du dépôt, après installation du CSV audité :

```sh
uv run --locked python -m unittest tests.test_ml_sender_history -v
uv run --locked python scripts/inspect_ml_sender_history.py
```

**Décision après discussion : F est mis de côté, sans entraîner de modèle.** Sa faible couverture limite le nombre de lignes auxquelles le compteur peut apporter une information distincte, mais elle ne démontre pas que cette variable est inutile pour ces lignes. Le diagnostic et ses données agrégées restent publiés. Aucun modèle final n'est choisi.
