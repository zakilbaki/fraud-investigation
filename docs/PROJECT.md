# Cadrage du prototype Fraud Investigation

## Objectif

Permettre à des agents d'examiner une transaction PaySim, de consulter des faits locaux, d'appeler ultérieurement un modèle ML et de produire un rapport qui distingue observations, calculs et limites. Le projet sert aussi de support pour expliquer les choix techniques en entretien. Une autre personne doit pouvoir cloner le dépôt GitHub et reproduire l'installation et les données dérivées à partir des prérequis documentés, sans accès aux dossiers ou comptes personnels du développeur.

## Périmètre et contraintes

- Exécution locale avec un budget supplémentaire de 0 €. Le MacBook Air M4 est la machine de développement et de test, pas un prérequis du projet.
- Python, `uv`, Polars et SQLite. La bibliothèque standard Python fournit l'accès SQLite. L'application vise peu d'écritures simultanées.
- Aucun service cloud payant ni service supplémentaire sans besoin démontré.
- PaySim est synthétique. Un résultat sur PaySim ne démontre pas une performance sur des transactions bancaires réelles.
- Aucun profil de compte ne sera inventé. Les comptes seront déduits uniquement des identifiants et faits effectivement présents dans les données.
- Les scénarios ajoutés seront stockés à part des lignes PaySim originales et porteront une provenance distincte.
- Plateforme effectivement vérifiée pour les lots 2 et 3 : macOS sur Apple Silicon, Python 3.11. Les autres plateformes sont des cibles possibles, mais leur compatibilité n'est pas encore vérifiée.

## Frontière des données

Les colonnes `isFraud` et `isFlaggedFraud` sont réservées à l'évaluation. Elles ne doivent figurer ni dans les vues, ni dans les outils, ni dans les requêtes de l'agent. `isFlaggedFraud` est une baseline fournie par PaySim, pas une prédiction du futur modèle. Un fichier d'évaluation séparé conserve ces deux valeurs ; les futurs outils d'enquête devront en interdire l'accès.

Chaque transaction recevra un identifiant stable indépendant de sa position physique dans SQLite. L'import conservera la provenance de la ligne source, notamment la version ou empreinte du fichier et un numéro de ligne. Ce numéro servira à l'audit, jamais à établir une chronologie. `step` représente le pas temporel PaySim, mais l'ordre des lignes au sein d'un même `step` ne sera pas traité comme fiable.

## Données et stockage prévus

Le fichier PaySim disponible a été inspecté, sa provenance vérifiée et ses colonnes documentées avant la fixation du schéma. L'import reproductible utilise Polars pour la lecture et SQLite pour le stockage local. Les tables créées sont `transactions`, `accounts`, `investigation_cases` et `investigation_events`. Les index servent les recherches par transaction et par compte. Les événements d'enquête garderont leur propre horodatage, distinct du `step` PaySim.

Les données volumineuses, les bases générées, les secrets et le miroir `sources/` sont exclus de Git. Un petit échantillon publiable ne sera ajouté que si son origine et sa licence le permettent.

## État du lot 1

Le dépôt, la configuration Python, le paquet vide, les exclusions Git et ce document constituent le seul livrable. Aucun import, schéma, index, outil d'agent ou modèle ML n'est implémenté. Aucun fichier PaySim n'était présent dans `sources/` lors de l'inspection initiale. `uv` n'était pas disponible, donc la résolution des dépendances et le verrouillage sont reportés.

## État du lot 2

`uv` est désormais installé localement, les dépendances sont verrouillées et PaySim est conservé dans `data/raw/`, hors de Git. L'audit descriptif et sa provenance sont documentés dans [DATA_AUDIT.md](DATA_AUDIT.md). Le schéma SQLite, l'import en base et le ML restent à faire dans des lots ultérieurs.

## Consignes des agents de développement

Avant chaque lot, lire les [consignes de travail et de versionnement](../agent.md). Après chaque changement de code cohérent, terminé et vérifié, créer un commit et le pousser sur le dépôt GitHub existant, sans attendre la fin du lot. Les tests et la documentation associés suivent la même règle ; les données et secrets restent exclus de Git.

## État du lot 3

Le schéma, l'import par lots et les consultations Python sont documentés dans [DATABASE.md](DATABASE.md). Les fichiers SQLite générés restent locaux. Les labels sont dans un fichier d'évaluation séparé. Aucun modèle ML, endpoint HTTP ou agent Copilot Studio n'est inclus.

## État du lot 3.1

Le réimport vérifie désormais dans les deux sens les identifiants de transaction et les numéros de ligne entre la base applicative et le fichier de labels avant de retourner `already_imported`. Les ouvertures SQLite en lecture seule encodent le chemin avant d'ajouter `mode=ro`, y compris pour le fichier de labels attaché pendant ce contrôle. Le schéma et les données PaySim importées n'ont pas été modifiés.

Sur macOS Apple Silicon avec Python 3.11, les six tests légers ont réussi. Ils comprennent le refus de labels provenant d'une autre source synthétique de même taille, ainsi que l'import, les consultations et le réimport avec des chemins contenant des espaces, `#` et `é`. Le test vérifie aussi l'absence de fichier parasite et le refus d'une écriture par une connexion en lecture seule. Les bases PaySim complètes n'ont pas été reconstruites pour ce lot. Linux et Windows restent non vérifiés.

## État du lot 4.0, étape 1

L'[analyse exploratoire guidée](EDA.md) a commencé avec un notebook reproductible, la répartition des labels et la distribution globale des montants. Les figures sont montrées à l'utilisateur avant de poursuivre les comparaisons par label, type, temps et soldes. La sélection des variables et le découpage temporel restent provisoires. Aucun modèle n'a été entraîné.

Le retour de l'utilisateur sur le déséquilibre et le logarithme des montants a été consigné. Une vue à effectifs linéaires de `log10(amount)` vérifie la seconde hypothèse. Le maintien artificiel d'un même taux de fraude entre ensembles temporels n'est pas retenu comme contrainte ; les frontières restent à justifier après l'exploration.

## État du lot 4.0, étape 2

L'exploration compare maintenant les montants normaux et frauduleux avec des tranches communes et une normalisation par classe, puis calcule le taux de fraude et les effectifs de chaque tranche. Les montants nuls sont isolés. Les deux graphiques, le tableau des effectifs et leurs limites sont documentés dans [EDA.md](EDA.md) et le notebook. Les observations de l'utilisateur restent attendues avant l'exploration suivante. Aucun entraînement ni choix définitif de variable ou de découpage n'a eu lieu.

## État du lot 4.0, étape 3

L'hypothèse sur le rôle du type de transaction a été vérifiée par des effectifs et taux de fraude par type et tranche de montant. La composition des types varie avec le montant, mais les taux changent aussi à type comparable. Les figures et tableaux sont dans [EDA.md](EDA.md) et le notebook ; les limites du simulateur et des petits effectifs sont explicitées. La discussion avec l'utilisateur précède toute exploration supplémentaire. Aucun entraînement n'a eu lieu.
