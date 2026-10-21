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

Au lot 5.1, une migration non destructive ajoute `investigation_idempotency`
à la première création de dossier ou d'événement. Sa clé primaire est
`(operation, idempotency_key)` ; elle conserve l'empreinte SHA-256 du contenu
normalisé, la réponse d'origine et la date UTC. `operation` vaut `create_case`
pour les dossiers ou `add_event:<case_id>` pour les événements. La migration
utilise `CREATE TABLE IF NOT EXISTS` dans une transaction d'écriture. Elle ne
modifie aucune table existante et garde les enquêtes préexistantes. L'import
PaySim ne crée pas cette table : elle apparaît lors de la première écriture API.

Les écritures API activent `PRAGMA foreign_keys = ON`, vérifient qu'il est actif,
puis utilisent `BEGIN IMMEDIATE` et des paramètres SQL. La création du dossier,
de son événement `case_created` et de la réponse d'idempotence est une seule
transaction ; un échec annule les trois. Les événements supplémentaires gardent
dans `details_json` une enveloppe JSON avec `origin`, `verification`, `content`
et `references`. Les événements fournis par un appelant portent toujours
`verification=caller_supplied`, même si leur type est `tool_result`.

Au lot 5.2, une seconde migration non destructive ajoute
`investigation_tool_runs`, indexée par dossier, date de début et identifiant.
Chaque ligne conserve l'opération choisie parmi quatre noms fermés, sa version,
les paramètres bornés, un identifiant stable, les dates UTC, le résultat ou
l'erreur et son état. `(case_id, idempotency_key)` est unique. La réservation
`running` est commise avant l'exécution de l'outil ; le résultat est écrit dans
une autre transaction courte. Aucun verrou d'écriture SQLite n'est maintenu
pendant le calcul ML. Si le processus s'arrête entre ces deux écritures, la
ligne reste `running` et est présentée comme incomplète, sans faux résultat.
La même clé ne relance pas cette exécution ; une nouvelle clé est nécessaire.
La création de cette table garde les dossiers et événements existants.

Les cinq champs monétaires (`amount` et les soldes) sont conservés en `TEXT` avec leur écriture décimale d'origine. L'import vérifie avec `Decimal` qu'ils sont numériques, finis et non négatifs, sans arrondi ni conversion en virgule flottante. Les montants zéro sont gardés. Les labels sont vérifiés dans `{0, 1}` mais ne sont jamais écrits dans `fraud.sqlite`.

Le fichier d'évaluation contient une table `labels` avec `source_line_number`, `transaction_id`, `isFraud` et `isFlaggedFraud`. Une vérification compare les identifiants et les numéros de ligne des deux fichiers dans les deux sens.

Les bases existantes sont ouvertes en lecture seule au moyen d'URI SQLite dont le chemin est encodé avant l'ajout de `mode=ro`. Les espaces, `#` et les caractères accentués des chemins sont ainsi préservés. Le réimport attache également le fichier de labels en lecture seule pour sa vérification.

## Recherches et ordre

`get_transaction` recherche par `transaction_id` unique. `get_account_transactions` recherche un compte comme expéditeur ou destinataire avec `step < before_step`, puis limite le nombre de résultats entre 1 et 500. Toutes les valeurs passent par des paramètres SQL.

L'API d'historique limite à 100 lignes retournées et une fenêtre de 168 steps,
et demande une ligne
supplémentaire à cette fonction pour calculer `truncated`. Ce booléen ne
constitue pas un nombre total. La lecture de score conserve son `COUNT(*)`
exact et indépendant.
Sur la base PaySim locale, `EXPLAIN QUERY PLAN` de la nouvelle fenêtre montre
`transactions_orig_step_id` et `transactions_dest_step_id` avec les deux bornes
de step. SQLite utilise aussi un tri temporaire pour l'ordre final ; aucun
gain de latence n'est déduit de ce seul plan.

Les index `transactions_orig_step_id` et `transactions_dest_step_id` portent sur le compte, le `step` décroissant et l'identifiant. L'index unique de `transaction_id` sert à la recherche directe. Les résultats sont triés par `step` décroissant, puis par identifiant croissant pour obtenir un ordre reproductible. Le second critère départage seulement les lignes d'un même `step` ; il ne représente pas leur chronologie réelle. Un compte présent dans les deux rôles sur une même transaction n'apparaît qu'une fois.

Pour le scoring local, `get_scoring_transaction` ne lit que les colonnes nécessaires au modèle et à la vérification de provenance. `count_prior_receipts` exécute `COUNT(*) WHERE name_dest = ? AND step < ?`, sans `LIMIT` et sans labels. Il compte chaque réception, y compris si plusieurs transactions ont le même step antérieur. Les opérations du step courant sont toutes exclues. Sur la base importée, `EXPLAIN QUERY PLAN` signale l'index couvrant `transactions_dest_step_id` pour cette requête ; son coût exact dépend encore du nombre de lignes antérieures du destinataire. Voir la [documentation API](API.md).

## Import complet vérifié

Le CSV dont le SHA-256 est `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b` a produit 6 362 620 transactions, 9 073 900 comptes distincts et 6 362 620 labels. Les tables d'enquête sont restées vides. Une seconde exécution a renvoyé `already_imported` avec les mêmes effectifs.

`PRAGMA foreign_key_check` et `PRAGMA quick_check` n'ont signalé aucune erreur. La jointure des identifiants et numéros de ligne entre la base applicative et le fichier de labels a trouvé zéro absence dans les deux sens. La base applicative ne contient aucune colonne `isFraud` ou `isFlaggedFraud`. Les index des deux rôles et l'index unique de transaction sont présents ; `EXPLAIN QUERY PLAN` utilise les deux index par compte avec la borne `step < ?`.
