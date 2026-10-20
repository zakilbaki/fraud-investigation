# Fiche du modèle CatBoost PaySim, lot 4.5

## Usage visé

Prototype pédagogique de classement de transactions PaySim pour investigation. Le score déclenche une alerte selon un seuil fixé ; sa calibration comme probabilité fiable n'a pas été évaluée. Aucun déploiement ou usage réel n'est validé.

## Entrées et état nécessaire

`type`, `amount`, `oldbalanceOrg`, heure cyclique simulée, ratio montant/solde et nombre de réceptions antérieures du destinataire. Les sept colonnes finales et leur ordre sont dans le [manifeste](results/ml_final_manifest.json). Pour une prédiction, l'application devrait disposer des transactions précédentes par `nameDest` et mettre à jour ce compteur après avoir prédit tout le step. Un nouveau destinataire reçoit zéro. Le solde nul donne un ratio manquant. Aucun label, identifiant brut ou solde après transaction n'entre dans le modèle.

## Ajustement et seuil

CatBoost CPU, 200 itérations, pas 0,05, profondeur 6, graine 42. Ajustement sur steps 1–360 ; seuil F1 maximal **0.312317992385** sur 361–432, avec scores égaux groupés et seuil le plus haut à égalité. Aucun ajustement sur 433–504. Pipeline local sauvegardé et rechargé avant le test ; empreintes et versions dans le manifeste.

## Mesure réservée

Sur steps 505–743 : 298584 transactions, 2592 fraudes, 2219 alertes, 2190 TP, 29 FP, 402 FN et 295963 TN. Précision 0.9869, rappel 0.8449, F1 0.9104. Voir le [rapport final](ML_FINAL_REPORT.md) pour les dénominateurs et diagnostics.

## Limites

PaySim est un simulateur. Le ratio montant/solde et les dernières périodes portent des signatures artificielles possibles. L'heure ne correspond pas à un calendrier civil connu. Les validations temporelles ont été réutilisées pour les choix ; les labels du futur test avaient été examinés pendant l'EDA. La disponibilité et la qualité en temps réel des soldes et historiques ne sont pas démontrées. Le test a une période entièrement frauduleuse. Aucun résultat ne garantit une généralisation réelle.
