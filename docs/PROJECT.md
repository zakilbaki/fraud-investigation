# Cadrage du prototype Fraud Investigation

## Objectif

Permettre à des agents d'examiner une transaction PaySim, de consulter des faits locaux, d'appeler ultérieurement un modèle ML et de produire un rapport qui distingue observations, calculs et limites. Le projet sert aussi de support pour expliquer les choix techniques en entretien.

## Périmètre et contraintes

- Exécution locale sur un MacBook Air M4, avec un budget supplémentaire de 0 €.
- Python, `uv`, Polars et SQLite. La bibliothèque standard Python fournit l'accès SQLite. L'application vise peu d'écritures simultanées.
- Aucun service cloud payant ni service supplémentaire sans besoin démontré.
- PaySim est synthétique. Un résultat sur PaySim ne démontre pas une performance sur des transactions bancaires réelles.
- Aucun profil de compte ne sera inventé. Les comptes seront déduits uniquement des identifiants et faits effectivement présents dans les données.
- Les scénarios ajoutés seront stockés à part des lignes PaySim originales et porteront une provenance distincte.

## Frontière des données

Les colonnes `isFraud` et `isFlaggedFraud` sont réservées à l'évaluation. Elles ne doivent figurer ni dans les vues, ni dans les outils, ni dans les requêtes de l'agent. `isFlaggedFraud` est une baseline fournie par PaySim, pas une prédiction du futur modèle. Une zone d'évaluation séparée, inaccessible aux agents, conservera ces deux valeurs lorsque l'import sera conçu.

Chaque transaction recevra un identifiant stable indépendant de sa position physique dans SQLite. L'import conservera la provenance de la ligne source, notamment la version ou empreinte du fichier et un numéro de ligne. Ce numéro servira à l'audit, jamais à établir une chronologie. `step` représente le pas temporel PaySim, mais l'ordre des lignes au sein d'un même `step` ne sera pas traité comme fiable.

## Données et stockage prévus

Le prochain lot devra d'abord inspecter le fichier PaySim réellement disponible, vérifier son origine et documenter ses colonnes avant de fixer le schéma. L'import reproductible utilisera Polars pour la lecture et SQLite pour le stockage local. Les tables visées sont `transactions`, `accounts`, `investigation_cases` et `investigation_events`. Les index seront choisis à partir des requêtes réelles par transaction et par compte. Les événements d'enquête garderont leur propre horodatage, distinct du `step` PaySim.

Les données volumineuses, les bases générées, les secrets et le miroir `sources/` sont exclus de Git. Un petit échantillon publiable ne sera ajouté que si son origine et sa licence le permettent.

## État du lot 1

Le dépôt, la configuration Python, le paquet vide, les exclusions Git et ce document constituent le seul livrable. Aucun import, schéma, index, outil d'agent ou modèle ML n'est implémenté. Aucun fichier PaySim n'était présent dans `sources/` lors de l'inspection initiale. `uv` n'était pas disponible, donc la résolution des dépendances et le verrouillage sont reportés.

## État du lot 2

`uv` est désormais installé localement, les dépendances sont verrouillées et PaySim est conservé dans `data/raw/`, hors de Git. L'audit descriptif et sa provenance sont documentés dans [DATA_AUDIT.md](DATA_AUDIT.md). Le schéma SQLite, l'import en base et le ML restent à faire dans des lots ultérieurs.

## Consignes des agents de développement

Avant chaque lot, lire les [consignes de travail et de versionnement](../agent.md). Après chaque changement de code cohérent, terminé et vérifié, créer un commit et le pousser sur le dépôt GitHub existant, sans attendre la fin du lot. Les tests et la documentation associés suivent la même règle ; les données et secrets restent exclus de Git.
