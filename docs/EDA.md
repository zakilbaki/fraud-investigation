# Analyse exploratoire guidée de PaySim

## Lot 4.0, étape 1 : classes et montants globaux

Le notebook reproductible est [`notebooks/eda_paysim.ipynb`](../notebooks/eda_paysim.ipynb). Il lit le CSV brut sans le modifier, avec Polars, et produit des figures SVG à partir de la bibliothèque standard Python. Aucune installation de bibliothèque graphique n'est nécessaire. Depuis la racine du dépôt, après l'installation décrite dans le README, exécuter `uv run --locked python scripts/run_eda_notebook.py` pour recalculer les figures sans Jupyter. Le notebook peut aussi être ouvert avec un environnement Jupyter compatible. Le CSV attendu est `data/raw/PS_20174392719_1491204439457_log.csv`, téléchargé selon le README ; son empreinte SHA-256 est vérifiée dans le notebook. Les figures SVG sont aussi enregistrées dans `docs/figures/`, avec des exportations PNG pour leur affichage.

Les labels ne sont utilisés ici que pour l'analyse hors ligne. Ils restent absents des outils d'enquête et ne seront pas des variables du modèle.

### Observations vérifiées

Sur 6 362 620 transactions, `isFraud = 0` concerne 6 354 407 lignes (99,8709 %) et `isFraud = 1` concerne 8 213 lignes (0,1291 %). Le graphique des classes emploie une échelle logarithmique pour les effectifs afin que les deux points restent visibles ; leurs distances visuelles ne représentent pas les rapports linéaires entre effectifs. Les valeurs et pourcentages exacts sont indiqués près des points.

Les montants vont de 0 à 92 445 516,64 unités PaySim. La médiane est 74 871,94, le 90e percentile 365 423,29 et le 99e percentile 1 615 983,34. Les 16 montants nuls sont indiqués à part. Les montants positifs sont regroupés par puissances de dix : chaque tranche va d'une borne incluse à dix fois cette borne, exclue. L'axe vertical des effectifs est aussi logarithmique pour conserver la visibilité des tranches peu fréquentes. Le nombre de lignes, et non une densité, est représenté par tranche. Ces graphiques ne comparent pas encore les montants selon le label.

### Choix et vérifications

Un histogramme en tranches linéaires ferait disparaître visuellement les petits montants face à l'étendue observée. L'alternative serait une vue linéaire tronquée accompagnée d'une seconde vue des valeurs extrêmes ; elle oblige à choisir une coupure. Les tranches logarithmiques montrent toute l'étendue positive avec une règle fixe et vérifiable. Elles ne permettent pas de juger finement la forme de la distribution à l'intérieur d'une tranche.

Le notebook vérifie l'empreinte du CSV, le nombre total de lignes, les deux modalités du label, l'absence de montants négatifs et la somme des effectifs des tranches plus les zéros. Les observations portent sur PaySim, jeu synthétique, et ne caractérisent pas des transactions réelles. L'interprétation des montants nuls reste ouverte.

### Retour de l'utilisateur et vérification ciblée

L'utilisateur relève le fort déséquilibre des labels et propose de choisir une métrique adaptée. Il suggère aussi de garder le même pourcentage de fraude dans chaque ensemble temporel. La première idée justifie une future évaluation attentive à la classe rare, notamment la précision, le rappel, la PR-AUC et le volume d'alertes. La seconde est une hypothèse à discuter : si la fréquence change réellement avec `step`, imposer le même pourcentage par stratification mélangerait les périodes et masquerait ce changement. Les frontières temporelles ne seront pas choisies pour égaliser les taux ou améliorer les performances. L'audit précédent montre déjà des taux différents par fenêtres de 168 `step` ; aucun découpage n'est encore validé.

L'utilisateur suggère que le logarithme des montants pourrait être proche d'une distribution normale et devenir une variable transformée. Le premier graphique ne permettait pas ce diagnostic, car ses deux axes étaient logarithmiques. Le notebook ajoute donc un histogramme de `log10(amount)` pour les 6 362 604 montants positifs, avec des tranches régulières de 0,5 sur l'axe horizontal et un axe vertical **linéaire**. Les 16 zéros restent à part. Le logarithme de base 10 a une moyenne observée de 4,7080, une médiane de 4,8743 et une asymétrie mesurée de -0,5594. La vue montre une concentration centrale, mais aussi un pic marqué dans la tranche `[5,0 ; 5,5[` et une asymétrie. Elle ne justifie pas de qualifier la distribution de normale.

Une transformation `log1p(amount)` reste une candidate à tester plus tard pour une baseline linéaire : elle compresse les grands montants et accepte zéro. Son éventuel intérêt prédictif devra être mesuré sur validation après entraînement de la baseline sur le train. Pour un arbre tel que LightGBM, une transformation monotone du montant ne change généralement pas l'ordre des valeurs ; elle n'est donc pas une amélioration à présumer. Aucune variable sensible ni découpage temporel n'est validé à cette étape. Aucun entraînement n'a été effectué.

Les montants selon le label, les types, le temps et les soldes seront explorés progressivement avec l'utilisateur.

## Lot 4.0, étape 2 : montants selon le label

L'utilisateur observe une forte concentration dans `[5 ; 5,5[` sur `log10(amount)`, soit de 100 000 à environ 316 228 unités PaySim, sans en déduire une cause ni un risque accru. Pour vérifier les deux idées séparément, le notebook emploie les mêmes tranches de largeur 0,5 que le graphique précédent, avec les zéros isolés.

La **part dans la classe** divise l'effectif d'une tranche par toutes les transactions de la même classe : `P(tranche | label)`. Chaque classe somme à 100 %, ce qui permet de comparer les formes malgré 6 354 407 normales contre 8 213 fraudes. Le **taux de fraude dans la tranche** divise les fraudes de la tranche par toutes les transactions de cette tranche : `P(label = fraude | tranche)`. Ces deux pourcentages répondent à des questions différentes.

Par exemple, `[5 ; 5,5[` contient 1 798 fraudes, soit 21,8921 % de toutes les fraudes, mais 1 995 765 transactions au total. Son taux de fraude observé est 0,0901 %. La tranche `[6,5 ; 7[` contient moins de fraudes, 834, mais seulement 15 256 transactions au total ; son taux observé est 5,4667 %. Un grand **nombre** de fraudes peut donc provenir surtout d'un grand volume de transactions.

Les 16 montants nuls sont tous étiquetés fraude dans ce fichier : ils représentent 0,1948 % des fraudes et un taux observé de 100 % parmi 16 transactions. Cet effectif réduit et le caractère synthétique de PaySim interdisent d'en faire une règle de fraude générale. Les tranches avec peu de transactions et les taux proches des bornes sont également fragiles. Aucun intervalle d'incertitude ni contrôle des effets du type de transaction ou du temps n'est encore réalisé. Ces résultats descriptifs calculés sur l'ensemble du CSV ne servent pas à sélectionner un seuil ou à annoncer des performances de modèle.

Le tableau donne les effectifs exacts et les deux normalisations. Pour les montants positifs, les intervalles indiquent les bornes de `log10(amount)` ; chaque borne haute est exclue. Par exemple `[5 ; 5,5[` signifie `100 000 ≤ amount < 316 227,77`.

| Tranche de `log10(amount)` | Normales | Fraudes | Part des normales | Part des fraudes | Total | Taux de fraude |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `0` | 0 | 16 | 0,0000 % | 0,1948 % | 16 | 100,0000 % |
| `[-2 ; -1,5[` | 6 | 0 | 0,0001 % | 0,0000 % | 6 | 0,0000 % |
| `[-1,5 ; -1[` | 4 | 0 | 0,0001 % | 0,0000 % | 4 | 0,0000 % |
| `[-1 ; -0,5[` | 31 | 0 | 0,0005 % | 0,0000 % | 31 | 0,0000 % |
| `[-0,5 ; 0[` | 75 | 0 | 0,0012 % | 0,0000 % | 75 | 0,0000 % |
| `[0 ; 0,5[` | 298 | 0 | 0,0047 % | 0,0000 % | 298 | 0,0000 % |
| `[0,5 ; 1[` | 908 | 0 | 0,0143 % | 0,0000 % | 908 | 0,0000 % |
| `[1 ; 1,5[` | 3 165 | 0 | 0,0498 % | 0,0000 % | 3 165 | 0,0000 % |
| `[1,5 ; 2[` | 9 598 | 2 | 0,1510 % | 0,0244 % | 9 600 | 0,0208 % |
| `[2 ; 2,5[` | 30 590 | 20 | 0,4814 % | 0,2435 % | 30 610 | 0,0653 % |
| `[2,5 ; 3[` | 97 913 | 20 | 1,5409 % | 0,2435 % | 97 933 | 0,0204 % |
| `[3 ; 3,5[` | 308 710 | 62 | 4,8582 % | 0,7549 % | 308 772 | 0,0201 % |
| `[3,5 ; 4[` | 834 427 | 158 | 13,1315 % | 1,9238 % | 834 585 | 0,0189 % |
| `[4 ; 4,5[` | 1 141 809 | 437 | 17,9688 % | 5,3208 % | 1 142 246 | 0,0383 % |
| `[4,5 ; 5[` | 1 096 015 | 992 | 17,2481 % | 12,0784 % | 1 097 007 | 0,0904 % |
| `[5 ; 5,5[` | 1 993 967 | 1 798 | 31,3793 % | 21,8921 % | 1 995 765 | 0,0901 % |
| `[5,5 ; 6[` | 708 971 | 2 002 | 11,1572 % | 24,3760 % | 710 973 | 0,2816 % |
| `[6 ; 6,5[` | 108 135 | 1 585 | 1,7017 % | 19,2987 % | 109 720 | 1,4446 % |
| `[6,5 ; 7[` | 14 422 | 834 | 0,2270 % | 10,1546 % | 15 256 | 5,4667 % |
| `[7 ; 7,5[` | 5 066 | 287 | 0,0797 % | 3,4945 % | 5 353 | 5,3615 % |
| `[7,5 ; 8[` | 297 | 0 | 0,0047 % | 0,0000 % | 297 | 0,0000 % |

Les effectifs de chaque classe et de chaque tranche sont vérifiés par sommation dans le notebook. Les figures SVG et leurs exportations PNG se trouvent dans `docs/figures/`. La sélection des variables, le découpage temporel et l'entraînement restent en attente de la discussion avec l'utilisateur.

## Lot 4.0, étape 3 : hypothèse sur le type de transaction

**Hypothèse testée :** la relation globale entre montant et fraude peut dépendre du mélange des types de transaction. Le notebook conserve les mêmes tranches de `log10(amount)` et compte chaque combinaison `type × tranche`, y compris les montants nuls. Les figures se concentrent sur les cinq tranches allant de 100 000 à environ 31,6 millions d'unités PaySim, qui couvrent les montants discutés avec l'utilisateur. Le calcul et les contrôles couvrent toutes les tranches.

### Résultats observés par type

| Type | Transactions | Fraudes étiquetées | Taux observé |
| --- | ---: | ---: | ---: |
| `CASH_IN` | 1 399 284 | 0 | 0 % |
| `CASH_OUT` | 2 237 500 | 4 116 | 0,1840 % |
| `DEBIT` | 41 432 | 0 | 0 % |
| `PAYMENT` | 2 151 495 | 0 | 0 % |
| `TRANSFER` | 532 909 | 4 097 | 0,7688 % |

Les 8 213 fraudes étiquetées se trouvent uniquement dans `CASH_OUT` et `TRANSFER` dans ce CSV. Cela décrit le jeu de données, pas une règle universelle sur ces opérations. Les 16 montants nuls sont des `CASH_OUT` étiquetés fraude et restent hors des tranches logarithmiques.

La composition change avec le montant. Dans `[5 ; 5,5[`, `CASH_OUT` et `CASH_IN` forment l'essentiel du volume ; dans `[6 ; 6,5[`, `TRANSFER` domine très largement. Cette différence contribue à la variation du taux global par montant. Mais le taux varie **aussi au sein d'un même type** : pour `CASH_OUT`, il passe de 904 / 1 146 832 (0,0788 %) dans `[5 ; 5,5[` à 790 / 1 093 (72,2781 %) dans `[6 ; 6,5[`. Pour `TRANSFER`, il passe de 894 / 126 679 (0,7057 %) à 795 / 108 508 (0,7327 %) entre ces mêmes tranches, puis à 421 / 14 843 (2,8364 %) dans `[6,5 ; 7[`. Le type explique donc une partie du mélange, mais ne suffit pas à expliquer toute la forme observée.

### Effectifs des tranches présentées

| Tranche de `log10(amount)` | Type | Transactions | Fraudes | Taux observé |
| --- | --- | ---: | ---: | ---: |
| `[5 ; 5,5[` | `CASH_IN` | 721 076 | 0 | 0 % |
| `[5 ; 5,5[` | `CASH_OUT` | 1 146 832 | 904 | 0,0788 % |
| `[5 ; 5,5[` | `DEBIT` | 142 | 0 | 0 % |
| `[5 ; 5,5[` | `PAYMENT` | 1 036 | 0 | 0 % |
| `[5 ; 5,5[` | `TRANSFER` | 126 679 | 894 | 0,7057 % |
| `[5,5 ; 6[` | `CASH_IN` | 180 683 | 0 | 0 % |
| `[5,5 ; 6[` | `CASH_OUT` | 314 951 | 1 002 | 0,3181 % |
| `[5,5 ; 6[` | `DEBIT` | 11 | 0 | 0 % |
| `[5,5 ; 6[` | `TRANSFER` | 215 328 | 1 000 | 0,4644 % |
| `[6 ; 6,5[` | `CASH_IN` | 119 | 0 | 0 % |
| `[6 ; 6,5[` | `CASH_OUT` | 1 093 | 790 | 72,2781 % |
| `[6 ; 6,5[` | `TRANSFER` | 108 508 | 795 | 0,7327 % |
| `[6,5 ; 7[` | `CASH_OUT` | 413 | 413 | 100 % |
| `[6,5 ; 7[` | `TRANSFER` | 14 843 | 421 | 2,8364 % |
| `[7 ; 7,5[` | `CASH_OUT` | 142 | 142 | 100 % |
| `[7 ; 7,5[` | `TRANSFER` | 5 211 | 145 | 2,7826 % |

Un type absent d'une tranche a zéro transaction dans cette combinaison ; son taux n'est donc pas défini. Les taux de 100 % reposent sur 413 et 142 transactions `CASH_OUT` et pourraient refléter une particularité du simulateur. Cette EDA ne contrôle pas encore les effets du `step`, des soldes ou du mécanisme de génération des labels. Les taux sont descriptifs sur l'ensemble du CSV, sans valeur causale ni garantie de calibration pour de nouvelles transactions.

Le notebook vérifie que les sommes par type et par tranche retrouvent les 6 362 620 transactions et 8 213 fraudes de l'audit, et que les 16 montants nuls sont comptés une seule fois. Aucun modèle n'a été entraîné ; la sélection des variables et le découpage temporel restent ouverts.
