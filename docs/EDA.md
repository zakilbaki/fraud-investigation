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

### Discussion en attente

Les observations et hypothèses de l'utilisateur seront consignées ici avant de poursuivre l'exploration des montants par label, des types, du temps et des soldes. Aucune variable sensible ni découpage temporel n'est validé à cette étape. Aucun entraînement n'a été effectué.
