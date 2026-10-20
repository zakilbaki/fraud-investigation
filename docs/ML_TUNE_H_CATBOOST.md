# Lot 4.4 : réglages CatBoost avec les variables de H

Les configurations des deux familles ont été figées dans [le protocole](ML_PROTOCOL.md) avant les nouveaux scores. Les quinze exécutions CatBoost sont achevées après l'échange sur XGBoost. H est réutilisée sans réentraînement. Les métriques d'apprentissage de H n'avaient pas été enregistrées ; son écart apprentissage/validation est donc non disponible.

## Moyennes des cinq validations

Les moyennes sont arithmétiques et distinctes des effectifs cumulés. Les cinq fenêtres se recouvrent par l'apprentissage et ne forment pas cinq expériences indépendantes.

| Configuration | Précision | Rappel | F1 | F1 min | Écart-type F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| H | 0.9519 | 0.8493 | 0.8976 | 0.8724 | 0.0224 |
| cat_depth4 | 0.9454 | 0.8253 | 0.8810 | 0.8509 | 0.0235 |
| cat_l2leaf10 | 0.9468 | 0.8473 | 0.8941 | 0.8732 | 0.0212 |
| cat_slow200 | 0.9581 | 0.8589 | 0.9056 | 0.8921 | 0.0166 |

![Moyennes](figures/ml_tune_h_catboost_means.png)

![F1 par fenêtre](figures/ml_tune_h_catboost_windows.png)

## Fenêtres, seuils et apprentissage

Chaque seuil maximise F1 sur la réserve interne seulement. Les prévalences sont `fraudes / transactions`. Les métriques d'apprentissage emploient ce même seuil, choisi après l'ajustement.

| Config | Fen. | Seuil | P val | R val | F1 val | P app. | R app. | F1 app. | Prév. app. % | Prév. val % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cat_depth4 | 1 | 0.280670 | 0.8858 | 0.8186 | 0.8509 | 0.8836 | 0.7933 | 0.8360 | 0.086 | 0.062 |
| cat_depth4 | 2 | 0.388144 | 0.9502 | 0.7933 | 0.8647 | 0.9432 | 0.8045 | 0.8684 | 0.108 | 0.073 |
| cat_depth4 | 3 | 0.354063 | 0.9448 | 0.8347 | 0.8863 | 0.9351 | 0.8104 | 0.8683 | 0.087 | 0.060 |
| cat_depth4 | 4 | 0.271342 | 0.9539 | 0.8381 | 0.8923 | 0.9220 | 0.8216 | 0.8689 | 0.083 | 0.102 |
| cat_depth4 | 5 | 0.262235 | 0.9923 | 0.8416 | 0.9108 | 0.8813 | 0.7926 | 0.8346 | 0.077 | 1.374 |
| cat_l2leaf10 | 1 | 0.281138 | 0.8966 | 0.8509 | 0.8732 | 0.8959 | 0.8124 | 0.8521 | 0.086 | 0.062 |
| cat_l2leaf10 | 2 | 0.345053 | 0.9314 | 0.8219 | 0.8732 | 0.9291 | 0.8346 | 0.8793 | 0.108 | 0.073 |
| cat_l2leaf10 | 3 | 0.381954 | 0.9433 | 0.8564 | 0.8977 | 0.9419 | 0.8256 | 0.8799 | 0.087 | 0.060 |
| cat_l2leaf10 | 4 | 0.367834 | 0.9674 | 0.8476 | 0.9036 | 0.9411 | 0.8228 | 0.8780 | 0.083 | 0.102 |
| cat_l2leaf10 | 5 | 0.286769 | 0.9955 | 0.8599 | 0.9228 | 0.8943 | 0.8148 | 0.8527 | 0.077 | 1.374 |
| cat_slow200 | 1 | 0.353509 | 0.9324 | 0.8571 | 0.8932 | 0.9309 | 0.8472 | 0.8871 | 0.086 | 0.062 |
| cat_slow200 | 2 | 0.447765 | 0.9515 | 0.8397 | 0.8921 | 0.9559 | 0.8499 | 0.8998 | 0.108 | 0.073 |
| cat_slow200 | 3 | 0.453777 | 0.9374 | 0.8726 | 0.9039 | 0.9538 | 0.8469 | 0.8972 | 0.087 | 0.060 |
| cat_slow200 | 4 | 0.558895 | 0.9753 | 0.8452 | 0.9056 | 0.9635 | 0.8286 | 0.8910 | 0.083 | 0.102 |
| cat_slow200 | 5 | 0.312318 | 0.9941 | 0.8796 | 0.9333 | 0.9034 | 0.8354 | 0.8681 | 0.077 | 1.374 |

### Écarts à H sur les mêmes fenêtres

Un écart positif de F1 ou de TP et un écart négatif de FP n'ont pas la même signification. Les seuils diffèrent entre H et chaque variante.

| Config | Fen. | ΔP | ΔR | ΔF1 | ΔTP | ΔFP | F1 H |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cat_depth4 | 1 | -0.0465 | -0.0186 | -0.0313 | -15 | 36 | 0.8822 |
| cat_depth4 | 2 | 0.0236 | -0.0309 | -0.0077 | -26 | -20 | 0.8724 |
| cat_depth4 | 3 | 0.0000 | -0.0230 | -0.0128 | -17 | -1 | 0.8991 |
| cat_depth4 | 4 | -0.0122 | -0.0107 | -0.0114 | -9 | 9 | 0.9037 |
| cat_depth4 | 5 | 0.0026 | -0.0366 | -0.0199 | -28 | -2 | 0.9307 |
| cat_l2leaf10 | 1 | -0.0356 | 0.0137 | -0.0090 | 11 | 30 | 0.8822 |
| cat_l2leaf10 | 2 | 0.0048 | -0.0024 | 0.0008 | -2 | -4 | 0.8724 |
| cat_l2leaf10 | 3 | -0.0015 | -0.0014 | -0.0014 | -1 | 1 | 0.8991 |
| cat_l2leaf10 | 4 | 0.0013 | -0.0012 | -0.0001 | -1 | -1 | 0.9037 |
| cat_l2leaf10 | 5 | 0.0058 | -0.0183 | -0.0079 | -14 | -4 | 0.9307 |
| cat_slow200 | 1 | 0.0002 | 0.0199 | 0.0110 | 16 | 1 | 0.8822 |
| cat_slow200 | 2 | 0.0250 | 0.0154 | 0.0197 | 13 | -19 | 0.8724 |
| cat_slow200 | 3 | -0.0074 | 0.0149 | 0.0047 | 11 | 6 | 0.8991 |
| cat_slow200 | 4 | 0.0092 | -0.0036 | 0.0019 | -3 | -7 | 0.9037 |
| cat_slow200 | 5 | 0.0044 | 0.0013 | 0.0027 | 1 | -3 | 0.9307 |

![Écart F1 apprentissage et validation](figures/ml_tune_h_catboost_train_gap.png)

Un écart peut aussi provenir du changement de prévalence et de période ; il ne prouve pas seul un surapprentissage.

## Alertes et coûts

| Config | Fen. | Alertes | TP | FP | FN | TN | Fit s | Préd. val s | Total s | Pic Gio | Taille Mio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cat_depth4 | 1 | 744 | 659 | 85 | 146 | 1287249 | 3.54 | 0.10 | 7.35 | 1.82 | 0.04 |
| cat_depth4 | 2 | 703 | 668 | 35 | 174 | 1159703 | 5.22 | 0.10 | 8.05 | 2.12 | 0.04 |
| cat_depth4 | 3 | 652 | 616 | 36 | 122 | 1226967 | 10.12 | 0.11 | 13.09 | 2.41 | 0.04 |
| cat_depth4 | 4 | 738 | 704 | 34 | 136 | 821485 | 14.53 | 0.07 | 17.60 | 2.83 | 0.04 |
| cat_depth4 | 5 | 648 | 643 | 5 | 121 | 54851 | 19.64 | 0.01 | 22.97 | 3.25 | 0.04 |
| cat_l2leaf10 | 1 | 764 | 685 | 79 | 120 | 1287255 | 4.88 | 0.13 | 8.10 | 2.08 | 0.11 |
| cat_l2leaf10 | 2 | 743 | 692 | 51 | 150 | 1159687 | 6.48 | 0.10 | 9.40 | 2.05 | 0.11 |
| cat_l2leaf10 | 3 | 670 | 632 | 38 | 106 | 1226965 | 12.48 | 0.11 | 15.44 | 2.80 | 0.11 |
| cat_l2leaf10 | 4 | 736 | 712 | 24 | 128 | 821495 | 19.32 | 0.08 | 22.49 | 2.88 | 0.11 |
| cat_l2leaf10 | 5 | 660 | 657 | 3 | 107 | 54853 | 25.31 | 0.01 | 29.59 | 2.83 | 0.12 |
| cat_slow200 | 1 | 740 | 690 | 50 | 115 | 1287284 | 28.29 | 0.15 | 31.93 | 2.43 | 0.24 |
| cat_slow200 | 2 | 743 | 707 | 36 | 135 | 1159702 | 42.81 | 0.14 | 46.60 | 2.32 | 0.25 |
| cat_slow200 | 3 | 687 | 644 | 43 | 94 | 1226960 | 87.74 | 0.16 | 91.81 | 3.03 | 0.26 |
| cat_slow200 | 4 | 728 | 710 | 18 | 130 | 821501 | 129.04 | 0.10 | 133.14 | 4.21 | 0.25 |
| cat_slow200 | 5 | 676 | 672 | 4 | 92 | 54852 | 165.13 | 0.01 | 169.19 | 5.38 | 0.26 |

Les cumuls de la référence H et des variantes sont :

| Config | TP | FP | FN | Alertes | Fit médian s | Taille médiane Mio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H | 3385 | 173 | 604 | 3558 | 12.89 | 0.11 |
| cat_depth4 | 3290 | 195 | 699 | 3485 | 10.12 | 0.04 |
| cat_l2leaf10 | 3378 | 195 | 611 | 3573 | 12.48 | 0.11 |
| cat_slow200 | 3423 | 151 | 566 | 3574 | 87.74 | 0.25 |

![Fraudes, fausses alertes et temps](figures/ml_tune_h_catboost_counts_cost.png)

## Lecture provisoire

Les trois variantes et H sont comparées selon la règle figée, puis avec les configurations XGBoost dans le [rapport de sélection](ML_TUNE_H_SELECTION.md). Aucun autre essai n'a été ajouté.

## Limites et suite

Les seuils sont réestimés par configuration. Les mesures de coût proviennent d'exécutions séparées et ne constituent pas un benchmark contrôlé de vitesse. Le pic RSS est échantillonné et peut manquer un pic bref. Ratio montant/solde et heure peuvent refléter des signatures du simulateur. Les validations ont déjà guidé plusieurs choix ; les labels du test ont été examinés en EDA, sans score du test 505 à 743 ici. Aucune généralisation réelle ni modèle final ne sont annoncés.

Réexécution locale : `python scripts/run_ml_tune_h_catboost_all.py`, puis `python scripts/report_ml_tune_h_catboost.py`, avec les prérequis du README. Aucun fichier de transaction ni prédiction individuelle n'est publié.
