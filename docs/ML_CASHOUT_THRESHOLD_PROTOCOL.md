# Seuil CASH_OUT : protocole exploratoire fixé avant les calculs

Cette expérience est proposée **après** l'examen du test final. Elle ne remplace ni le modèle CatBoost gelé, ni sa politique à seuil unique `0.3123179923852385`, ni les métriques du [rapport final](ML_FINAL_REPORT.md). Son résultat sur 505–743 n'est pas une nouvelle évaluation indépendante. Une période ultérieure serait nécessaire pour envisager son adoption.

## Règle fixée

Le pipeline, les sept prédicteurs, les paramètres et les prétraitements du [manifeste](results/ml_final_manifest.json) restent inchangés. Aucun ajustement de modèle ou de transformation n'est effectué. Pour les autres types, la décision reste `score >= 0.3123179923852385`.

Pour `CASH_OUT`, le modèle déjà entraîné produit des scores sur les steps **361–432** avec la même construction des variables que lors du gel. L'historique destinataire au step `t` ne contient que les steps `< t`. Les labels de cette réserve servent uniquement à choisir le seuil. Les candidats sont le seuil global et les scores distincts de `CASH_OUT` inférieurs ou égaux au seuil global. Chaque score égal est traité comme un groupe, selon la règle `score >= seuil`. On maximise `F1 = 2TP / (2TP + FP + FN)` sur les seuls `CASH_OUT`. En cas d'égalité exacte, on retient le seuil numérique le plus élevé. Ainsi, la politique peut rester identique à la référence. Aucun autre critère ne sera essayé après lecture du résultat.

Le seuil choisi est ensuite appliqué aux scores locaux déjà sauvegardés du test **505–743**, uniquement pour `CASH_OUT`. Le seuil global reste appliqué à tous les autres types. Avant la comparaison, on vérifie les empreintes du CSV et du pipeline, l'alignement des steps et labels des scores locaux avec le CSV et la reconstitution exacte de la matrice de confusion finale publiée. Les labels du test ne participent pas au choix du seuil. On publie seulement des agrégats : précision, rappel, F1, alertes, TP, FP, FN, TN pour `CASH_OUT` et le test complet, ainsi que les différences. Les prédictions individuelles restent hors Git.

Une baisse du seuil élargit l'ensemble des alertes `CASH_OUT` : elle ne peut donc pas supprimer de fraude détectée ni de fausse alerte existante, mais peut ajouter des deux. Le résultat observé sur ce test déjà examiné ne prouve ni une amélioration future, ni une probabilité calibrée.
