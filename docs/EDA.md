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
