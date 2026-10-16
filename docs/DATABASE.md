# Stockage local PaySim

## Fichiers et séparation

L'application lit `data/app/fraud.sqlite`. Les labels résident uniquement dans `data/evaluation/labels.sqlite`, qui est réservé à l'évaluation et au futur travail ML. Ces deux fichiers et leurs auxiliaires sont exclus de Git. La séparation des fichiers devra être complétée par des restrictions explicites des futurs outils d'enquête : ils ne devront ouvrir que la base applicative.

Le CSV PaySim brut n'est jamais modifié. L'import construit d'abord des fichiers `.partial`, vérifie leurs contraintes et leurs effectifs, puis les renomme. Une interruption laisse les fichiers partiels visibles et bloque une nouvelle exécution jusqu'à leur examen. Une seconde exécution avec le même fichier valide les effectifs ainsi que la correspondance des identifiants et numéros de ligne entre les deux bases, puis ne change ni les transactions ni les enquêtes. Une source différente ou un fichier de labels incompatible est refusé.

Pour éviter des écritures dispersées pendant le chargement, les comptes distincts et les index sont construits après la lecture des transactions. Les clés étrangères et l'unicité des identifiants sont vérifiées avant le renommage final. Les fichiers temporaires utilisent des réglages SQLite favorisant la vitesse ; une interruption peut donc les rendre inutilisables, mais n'altère ni le CSV brut ni une base applicative déjà publiée.

## Provenance et identifiants

`source_sha256` contient les 32 octets de l'empreinte SHA-256 du CSV entier. `source_line_number` désigne la ligne physique du CSV, en commençant à **2** pour la première transaction, après l'en-tête en ligne 1. L'import exige qu'un enregistrement occupe une seule ligne physique ; il refuse un CSV dont le nombre d'enregistrements ne correspond pas au nombre de lignes. Le numéro de ligne sert à retrouver la source, pas à établir un ordre temporel au sein d'un `step`.

`transaction_id` contient les 16 premiers octets de `SHA-256(source_sha256_bytes || source_line_number_en_8_octets_big_endian)`. Les fonctions Python le présentent comme une chaîne hexadécimale de 32 caractères. Cet identifiant ne dépend ni de l'ordre d'insertion dans SQLite ni du contenu d'une seule ligne. Deux lignes identiques à des positions distinctes reçoivent donc deux identifiants distincts. La clé unique détecte une collision éventuelle plutôt que de fusionner des lignes.

## Schéma applicatif

| Table | Champs | Relations et contraintes |
| --- | --- | --- |
| `accounts` | `account_id` | Clé primaire textuelle non vide. Seul l'identifiant observé dans PaySim est conservé. Aucun profil de compte n'est créé. |
| `transactions` | `source_line_number`, `transaction_id`, `source_sha256`, `step`, `type`, `amount`, `name_orig`, `oldbalance_org`, `newbalance_orig`, `name_dest`, `oldbalance_dest`, `newbalance_dest` | Ligne source clé primaire ; identifiant de transaction unique ; `step > 0` ; comptes d'origine et de destination référencent `accounts`. |
| `investigation_cases` | `case_id`, `transaction_id`, `status`, `created_at`, `updated_at` | Clé primaire `case_id` ; transaction référencée ; statut parmi `open`, `in_progress`, `closed`. Vide après l'import PaySim. |
| `investigation_events` | `event_id`, `case_id`, `occurred_at`, `event_type`, `details_json` | Clé primaire `event_id` ; dossier référencé ; type non vide. Vide après l'import PaySim. |

Les cinq champs monétaires (`amount` et les soldes) sont conservés en `TEXT` avec leur écriture décimale d'origine. L'import vérifie avec `Decimal` qu'ils sont numériques, finis et non négatifs, sans arrondi ni conversion en virgule flottante. Les montants zéro sont gardés. Les labels sont vérifiés dans `{0, 1}` mais ne sont jamais écrits dans `fraud.sqlite`.

Le fichier d'évaluation contient une table `labels` avec `source_line_number`, `transaction_id`, `isFraud` et `isFlaggedFraud`. Une vérification compare les identifiants et les numéros de ligne des deux fichiers dans les deux sens.

## Recherches et ordre

`get_transaction` recherche par `transaction_id` unique. `get_account_transactions` recherche un compte comme expéditeur ou destinataire avec `step < before_step`, puis limite le nombre de résultats entre 1 et 500. Toutes les valeurs passent par des paramètres SQL.

Les index `transactions_orig_step_id` et `transactions_dest_step_id` portent sur le compte, le `step` décroissant et l'identifiant. L'index unique de `transaction_id` sert à la recherche directe. Les résultats sont triés par `step` décroissant, puis par identifiant croissant pour obtenir un ordre reproductible. Le second critère départage seulement les lignes d'un même `step` ; il ne représente pas leur chronologie réelle. Un compte présent dans les deux rôles sur une même transaction n'apparaît qu'une fois.

## Import complet vérifié

Le CSV dont le SHA-256 est `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b` a produit 6 362 620 transactions, 9 073 900 comptes distincts et 6 362 620 labels. Les tables d'enquête sont restées vides. Une seconde exécution a renvoyé `already_imported` avec les mêmes effectifs.

`PRAGMA foreign_key_check` et `PRAGMA quick_check` n'ont signalé aucune erreur. La jointure des identifiants et numéros de ligne entre la base applicative et le fichier de labels a trouvé zéro absence dans les deux sens. La base applicative ne contient aucune colonne `isFraud` ou `isFlaggedFraud`. Les index des deux rôles et l'index unique de transaction sont présents ; `EXPLAIN QUERY PLAN` utilise les deux index par compte avec la borne `step < ?`.
