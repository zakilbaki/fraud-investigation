# Audit des données PaySim

## Provenance vérifiée

- Source : [Synthetic Financial Datasets For Fraud Detection, Kaggle](https://www.kaggle.com/datasets/ealaxi/paysim1), auteur Edgar Lopez-Rojas.
- URL de téléchargement utilisée : `https://www.kaggle.com/api/v1/datasets/download/ealaxi/paysim1`.
- Récupération : 16 octobre 2026, fuseau Europe/Paris.
- Licence affichée par [la fiche du jeu](https://www.kaggle.com/ealaxi/paysim1/metadata) et par l'API de métadonnées Kaggle : **CC BY-SA 4.0**. La réutilisation publique doit respecter cette licence et attribuer la source.
- Archive conservée dans `data/raw/paysim1.zip` : 186 385 561 octets, SHA-256 `f7eef9ffad5cfa64a034143a5c9b30491d189420b273d5ad5723ca40b596613d`.
- CSV brut conservé dans `data/raw/PS_20174392719_1491204439457_log.csv` : 493 534 783 octets, SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`.

Le serveur a répondu avec une archive ZIP (`HTTP 200`, `application/zip`). `unzip -t` a validé l'entrée et son contrôle d'intégrité. Le CSV extrait a été lu intégralement par Polars et contient une ligne d'en-tête plus 6 362 620 lignes de données. Aucun checksum de référence de l'auteur n'a été obtenu lors de ces vérifications pour une comparaison indépendante.

## Faits mesurés

Audit exécuté avec Polars 1.44.2 via `scripts/audit_paysim.py`. Le script utilise un scan CSV différé, agrège les mesures et ne réécrit aucune ligne. Le rapport JSON complet, dont les effectifs de chacun des 743 `step`, se régénère dans `data/audit.json` avec la commande du README.

| Colonne | Type détecté | Sens indiqué par la fiche Kaggle |
| --- | --- | --- |
| `step` | Int64 | Heure de simulation |
| `type` | String | Type de transaction |
| `amount` | Float64 | Montant en devise locale |
| `nameOrig` | String | Identifiant du compte à l'origine |
| `oldbalanceOrg` | Float64 | Solde d'origine avant transaction |
| `newbalanceOrig` | Float64 | Solde d'origine après transaction |
| `nameDest` | String | Identifiant du destinataire |
| `oldbalanceDest` | Float64 | Solde destinataire avant transaction |
| `newbalanceDest` | Float64 | Solde destinataire après transaction |
| `isFraud` | Int64 | Label de fraude simulée |
| `isFlaggedFraud` | Int64 | Signalement par la règle fournie dans PaySim |

Les 11 colonnes ont chacune **0 valeur manquante**, en traitant les champs CSV vides comme manquants. Le nombre de lignes mesuré est **6 362 620**.

`step` va de **1 à 743**, avec 743 valeurs distinctes et aucune valeur non positive. Distribution regroupée pour lecture :

| `step` | Lignes |
| --- | ---: |
| 1 à 168 | 1 930 180 |
| 169 à 336 | 2 854 595 |
| 337 à 504 | 1 279 261 |
| 505 à 672 | 232 135 |
| 673 à 743 | 66 449 |

Fenêtres descriptives de 168 `step` (sept jours simulés), avec une dernière fenêtre plus courte. Les taux correspondent à `isFraud = 1` divisé par l'effectif de la fenêtre ; ils ne définissent aucun découpage d'entraînement ou de test.

| `step` | Transactions | Fraudes | Taux de fraude |
| --- | ---: | ---: | ---: |
| 1 à 168 | 1 930 180 | 1 904 | 0,0986 % |
| 169 à 336 | 2 854 595 | 1 863 | 0,0653 % |
| 337 à 504 | 1 279 261 | 1 854 | 0,1449 % |
| 505 à 672 | 232 135 | 1 792 | 0,7720 % |
| 673 à 743 | 66 449 | 800 | 1,2039 % |

La proportion observée varie selon la fenêtre, tout comme son effectif. Il faudra en tenir compte lors de la conception du futur protocole d'évaluation, sans déduire de cet audit la cause de la variation.

| `type` | Lignes |
| --- | ---: |
| `CASH_IN` | 1 399 284 |
| `CASH_OUT` | 2 237 500 |
| `DEBIT` | 41 432 |
| `PAYMENT` | 2 151 495 |
| `TRANSFER` | 532 909 |

| Label | Valeur 0 | Valeur 1 | Autre valeur non nulle |
| --- | ---: | ---: | ---: |
| `isFraud` | 6 354 407 | 8 213 | 0 |
| `isFlaggedFraud` | 6 362 604 | 16 | 0 |

Pour `amount` et les quatre colonnes de soldes, le contrôle a trouvé **0 valeur négative** et **0 valeur non finie**. Le nombre de zéros est de 16 pour `amount`, 2 102 449 pour `oldbalanceOrg`, 3 609 566 pour `newbalanceOrig`, 2 704 388 pour `oldbalanceDest` et 2 439 433 pour `newbalanceDest`.

## Anomalies potentielles

- Les **16 montants nuls** méritent un examen contextuel. Le script les signale sans les supprimer ni les corriger.
- Les nombreux soldes nuls ne prouvent pas à eux seuls une erreur. La fiche Kaggle indique notamment que les informations de solde ne sont pas disponibles pour certains destinataires commerçants dont l'identifiant commence par `M`.
- Aucun label hors de `{0, 1}`, montant négatif ou nombre non fini n'a été observé. L'absence de ces anomalies ne prouve pas la cohérence métier de chaque ligne.

## Limites

- PaySim est synthétique. Ces distributions ne préjugent pas des performances sur des transactions réelles.
- La [fiche Kaggle](https://www.kaggle.com/ealaxi/paysim1/metadata) avertit que les soldes avant et après transaction peuvent révéler le traitement des fraudes annulées. Leur usage comme variables prédictives exige une analyse de fuite d'information avant le lot ML.
- `step` désigne une heure simulée. L'ordre physique des lignes dans un même `step` n'est pas considéré comme une chronologie fiable.
- Le contrôle des doublons n'a pas été entrepris. Deux lignes identiques ne seraient pas supprimées automatiquement.
- Les labels ont été lus par un outil d'audit hors ligne. Ils ne doivent jamais être exposés aux futurs agents d'enquête.

## Décisions proposées pour le prochain lot

1. Figer l'empreinte du CSV dans la provenance de l'import et conserver un numéro de ligne source pour l'audit, sans l'utiliser comme horodatage.
2. Concevoir la séparation physique ou logique des labels d'évaluation avant de créer les outils accessibles aux agents.
3. Étudier les 16 montants nuls et les soldes avant toute règle de nettoyage ou sélection de variables. Conserver les lignes brutes intactes.
4. Définir le schéma et les index SQLite à partir des requêtes d'enquête prévues. Aucune de ces décisions n'est implémentée dans ce lot.
