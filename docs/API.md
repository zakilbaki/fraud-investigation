# API locales des transactions

## Lot 5.1 : point d'entrée commun et contrats des outils

Le serveur principal lancé par `scripts/serve_api.py` expose toutes les routes
ci-dessous. Les routes de consultation et de dossiers sont les mêmes dans
`scripts/serve_transaction_api.py`, qui ne charge pas le modèle. Le premier
serveur charge le CatBoost gelé une fois au démarrage. Si son artefact manque,
les consultations et les dossiers fonctionnent encore, `/score` répond 503
et `/health` répond 503 avec la cause. Aucun modèle de remplacement n'est utilisé.
Les descriptions OpenAPI générées sont consultables à `/openapi.json` et `/docs`.

| Outil | Rôle | Entrées | Sorties |
| --- | --- | --- | --- |
| `GET /transactions/{transaction_id}` | Lire les faits d'une transaction | Identifiant hexadécimal de 32 caractères | Dix champs autorisés, HTTP 404 si inconnue |
| `GET /accounts/{account_id}/transactions` | Lire un historique limité | Compte, `before_step` obligatoire, `lookback_steps` de 1 à 168, `limit` de 1 à 100 | Liste, bornes, limite, `truncated` |
| `POST /score` | Calculer le score final existant | Identifiant de transaction | Score, seuil, alerte, versions |
| `POST /cases` | Créer un dossier et son premier événement | Identifiant de transaction, en-tête `Idempotency-Key` | Dossier ouvert et `first_event_id` |
| `GET /cases/{case_id}` | Consulter un dossier | Identifiant du dossier | Statut, transaction, dates UTC |
| `POST /cases/{case_id}/events` | Ajouter un commentaire ou résultat déclaré | Type, origine, contenu JSON, références, clé d'idempotence | Événement et provenance déclarée |
| `GET /cases/{case_id}/events` | Lire les événements | Dossier, `limit` de 1 à 100 | Liste ordonnée, limite, `truncated` |
| `GET /health` | Vérifier le modèle du serveur principal | Aucune | Santé du modèle ou erreur 503 |

Les deux routes d'écriture utilisent une clé d'idempotence persistante fournie
par l'appelant. Sa portée est globale pour `POST /cases`, et propre à chaque
dossier pour `POST /cases/{case_id}/events`. La même clé et le même contenu
normalisé renvoient la réponse initiale, sans doublon, même après redémarrage.
La même clé avec un contenu différent donne HTTP 409. La clé doit contenir
de 1 à 128 caractères. Un échec avant commit ne réserve pas la clé.

`event_type` accepte `comment` ou `tool_result`, et `origin` accepte `user`,
`agent` ou `tool`. `content` est un objet JSON ; `references` contient au plus
20 chaînes. La requête événement est limitée à 16 384 caractères JSON.
Tous ces événements portent `verification=caller_supplied` : une référence ou
une déclaration de résultat n'est pas une preuve vérifiée par le backend.
Seul l'événement initial `case_created`, créé par le backend après vérification
de la transaction, porte `verified_transaction_reference`. La date `occurred_at`
est en UTC. Les événements sont triés par date, puis identifiant ; `truncated`
signale la présence d'au moins un événement supplémentaire.

Exemple **entièrement synthétique**, avec identifiants et réponse illustratifs :

```http
POST /cases
Idempotency-Key: demo-case-1
Content-Type: application/json

{"transaction_id":"00000000000000000000000000000002"}
```

```json
{"case_id":"11111111111111111111111111111111","transaction_id":"00000000000000000000000000000002","status":"open","created_at":"2026-10-21T10:00:00.000+00:00","updated_at":"2026-10-21T10:00:00.000+00:00","first_event_id":"22222222222222222222222222222222"}
```

```http
POST /cases/11111111111111111111111111111111/events
Idempotency-Key: demo-event-1
Content-Type: application/json

{"event_type":"comment","origin":"agent","content":{"text":"À examiner"},"references":["00000000000000000000000000000002"]}
```

La réponse synthétique ajoute `event_id`, `case_id`, `occurred_at`,
`event_type=comment`, `origin=agent`, `content`, `references` et
`verification=caller_supplied`. Une transaction inconnue donne 404 et
ne crée aucun dossier. Un dossier inconnu donne 404. Une base indisponible
donne 503. Les erreurs ne contiennent pas de trace Python.

Exemple d'historique **synthétique** :

```json
{"account_id":"A","before_step":3,"lookback_steps":168,"limit":1,"truncated":true,"transactions":[{"transaction_id":"00000000000000000000000000000002","source_sha256":"0000000000000000000000000000000000000000000000000000000000000000","source_line_number":2,"step":2,"type":"TRANSFER","amount":"10.00","name_orig":"A","oldbalance_org":"20.00","name_dest":"B","oldbalance_dest":"0.00"}]}
```

Un événement antérieur à la migration avec un ancien `details_json` reste
consultable : son contenu est conservé sous `content`, avec `origin=legacy`
et `verification=caller_supplied`.

Commandes de lancement vérifiées localement avec le Python 3.11 de `.venv`,
sur macOS Apple Silicon, avec les artefacts présents :

```sh
.venv/bin/python scripts/serve_api.py --database data/app/fraud.sqlite \
  --model data/ml_final_catboost/pipeline.joblib \
  --manifest docs/results/ml_final_manifest.json --port 8766
.venv/bin/python scripts/serve_transaction_api.py --database data/app/fraud.sqlite --port 8767
```

Ces deux commandes ont été lancées et contrôlées par HTTP sur `127.0.0.1` :
le serveur principal a renvoyé 200 pour santé, recherche et historique, et
404 pour une transaction inconnue ; le serveur de consultation a renvoyé
200 pour la recherche et `/openapi.json`. Elles lient `127.0.0.1` seulement.
Les chemins sont des paramètres de lancement de confiance, jamais des entrées
des outils HTTP. Aucun accès direct depuis Copilot Studio n'est établi.

## Consultation locale d'une transaction, lot backend initial

Une API de lecture indépendante du modèle ML expose `GET /transactions/{transaction_id}`.
Elle utilise le contrat de [DATABASE.md](DATABASE.md) et ouvre uniquement la base
applicative SQLite en lecture seule. L'identifiant est une chaîne de 32 caractères
hexadécimaux. La réponse contient dix champs du contrat : identifiant, provenance,
step, type, montant, deux comptes et deux soldes avant transaction. Les montants
restent des chaînes décimales exactes. Les soldes après transaction et les labels
d'évaluation ne figurent dans aucune réponse destinée aux agents.

`GET /accounts/{account_id}/transactions?before_step=3&limit=50` renvoie les
opérations de ce compte aux steps strictement antérieurs à 3. `before_step` est
obligatoire et doit être compris entre 1 et 1 000 000 ; `lookback_steps` vaut 168 par défaut et doit être compris entre
1 et 168. La fenêtre est `max(1, before_step - lookback_steps) <= step < before_step`.
`limit` vaut 50 par défaut et doit être compris entre 1 et 100.
La réponse fournit `account_id`, `before_step`, `lookback_steps`, `limit`, `truncated` et une liste
`transactions` soumise au même contrat de dix champs. `truncated=true` signifie
qu'au moins une autre ligne satisfait la recherche. Le tri est par step décroissant,
puis identifiant croissant : au sein d'un step, il est déterministe mais ne démontre
aucune chronologie. Une opération sur soi-même apparaît une seule fois. Une liste
limitée ne constitue jamais un historique complet. Le compteur exact distinct
du scoring n'utilise pas cette limite.

Depuis la racine du dépôt, après l'import PaySim :

```sh
uv run --locked python scripts/serve_transaction_api.py --database data/app/fraud.sqlite
curl http://127.0.0.1:8000/transactions/d83a6871a919fd644c774f3e65fbe41b
```

L'identifiant de cet exemple appartient au CSV PaySim audité indiqué dans le README.
Le serveur écoute seulement `127.0.0.1`. Un identifiant mal formé donne HTTP 400,
un identifiant valide mais absent HTTP 404 avec `Transaction introuvable`, et une
base absente ou illisible HTTP 503. Les réponses 200 reflètent la base locale :
elles ne prouvent pas une fraude et ne déclenchent aucune action sur un compte.
Les tests logiciels utilisent une base synthétique temporaire. Cette API ne donne
pas encore de recherche liée ni de rapport. Elle ne rend pas le
serveur local directement accessible depuis Copilot Studio ; cette connexion
requiert une vérification séparée des capacités disponibles.

Vérification ciblée :

```sh
python -m unittest tests.test_transaction_api -v
```

## Lot 5.0 : API locale de scoring d'une transaction connue

L'API prend l'identifiant hexadécimal d'une transaction déjà importée dans `data/app/fraud.sqlite`. Elle retourne un **score de suspicion** et une alerte selon le seuil global final **0,3123179923852385**. Le modèle est le CatBoost `cat_slow200` gelé. La [variante CASH_OUT](ML_CASHOUT_THRESHOLD_EXPLORATORY.md) reste exploratoire et n'est pas utilisée ici. Un score inférieur au seuil ne certifie pas que la transaction est légitime. La calibration du score comme probabilité n'a pas été évaluée.

## Calcul et choix techniques

Le service ouvre uniquement la base applicative en lecture seule. Il lit `step`, `type`, `amount`, `oldbalance_org` et `name_dest`, puis compte les lignes du même destinataire avec `step < step_courant`. Il compte les **transactions**, sans limite de 500 résultats ni ordre supposé à l'intérieur d'un step. La requête utilise l'index `transactions_dest_step_id` existant. Les labels et la base d'évaluation ne sont jamais ouverts par le service.

Le transformateur H est celui sauvegardé dans le pipeline : `type`, `amount` et `oldbalanceOrg` en conversions identiques, heure simulée en sinus/cosinus, ratio montant/solde manquant si le solde vaut zéro, compteur destinataire brut. Seules ces sept colonnes entrent dans CatBoost. Le numéro de step et l'identifiant du destinataire servent aux calculs, sans être transmis bruts comme prédicteurs. Le modèle et le manifeste sont chargés une fois au démarrage. L'empreinte du modèle, ses paramètres, l'ordre des colonnes, le seuil et la provenance de la base sont comparés au manifeste. Un artefact absent ou incompatible provoque une erreur explicite, jamais un entraînement automatique.

Une alternative serait de conserver les historiques dans une table mise à jour à chaque transaction. Ce prototype dispose déjà des transactions et de l'index nécessaire ; le comptage SQL exact évite une seconde source d'état. Il reste dépendant de la disponibilité du solde initial et des transactions antérieures dans la base. L'API ne reçoit pas encore de nouvelles transactions.

## Installation et lancement

Depuis la racine du dépôt, avec un Python compatible avec `pyproject.toml`, `uv` et les données importées localement. Seul Python 3.11 a été vérifié ici :

```sh
uv sync --locked
uv run --locked python scripts/serve_api.py \
  --database data/app/fraud.sqlite \
  --model data/ml_final_catboost/pipeline.joblib \
  --manifest docs/results/ml_final_manifest.json \
  --port 8000
```

Le serveur écoute **127.0.0.1**. Les trois chemins sont configurables ; les valeurs affichées sont aussi les valeurs par défaut. `uv run --locked` et `uv sync --locked` ont réussi ici avec un cache temporaire accessible ; si le cache par défaut est inaccessible, utiliser `uv --cache-dir <répertoire-temporaire> sync --locked` puis `uv --cache-dir <répertoire-temporaire> run --locked python scripts/serve_api.py`. Le modèle `pipeline.joblib`, le CSV et la base sont locaux et exclus de Git. Si le modèle manque, reprendre le [parcours de gel documenté](ML_FINAL_FREEZE.md) avec le CSV audité : `uv run --locked python scripts/freeze_ml_final.py`. Le script refuse de remplacer un modèle local existant ; si le [manifeste publié](results/ml_final_manifest.json) est déjà présent, il exige une reconstruction identique, y compris l'empreinte du modèle, sans réécrire ce manifeste. Une version de bibliothèque ou une plateforme différente peut empêcher cette identité. Cette reconstruction n'a pas été relancée pour ce lot.

## Requêtes et réponses

```sh
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/score \
  -H 'Content-Type: application/json' \
  -d '{"transaction_id":"<32 caractères hexadécimaux d’une transaction importée>"}'
```

Remplacer la valeur entre chevrons par un identifiant déjà présent dans la base. L'exemple suivant illustre **uniquement le jeu synthétique du test logiciel** : requête `{"transaction_id":"00000000000000000000000000000003"}`. Son modèle factice renvoie exactement le seuil ; cet identifiant n'est pas une transaction PaySim publiée. La forme de réponse est :

```json
{
  "transaction_id": "00000000000000000000000000000003",
  "suspicion_score": 0.3123179923852385,
  "threshold": 0.3123179923852385,
  "alert": true,
  "model_version": "cat_slow200:<12 caractères de l'empreinte>",
  "policy_version": "final_global_f1_v1"
}
```

`GET /health` répond 200 avec `status=ready`, `model_available=true` et la version du modèle si le chargement a réussi. Les erreurs prévues sont 400 pour un identifiant mal formé, 404 pour un identifiant absent, 422 pour une ligne incompatible avec le pipeline et 503 pour un modèle ou une base indisponibles ou incompatibles. Une requête JSON incorrecte peut recevoir 422. Les réponses ne contiennent pas de trace Python interne. Le service ne fournit ni preuve de fraude ni décision de blocage.

## Vérifications exécutées

- Les **54 tests** du dépôt passent avec le Python 3.11 local sur macOS Apple Silicon. Les tests API utilisent une base synthétique sans fichier de labels. Ils couvrent un destinataire nouveau, deux lignes au même step, plus de 500 antécédents, un ratio manquant, un montant nul, l'égalité exacte au seuil, l'identifiant mal formé ou absent, une ligne incompatible, un artefact absent ou modifié et le rechargement des artefacts. Un test distinct vérifie que la reconstruction ne réécrit pas un manifeste publié.
- Sur **quatre transactions des steps 1 à 212**, les champs lus dans SQLite correspondent au CSV sans labels, les comptes strictement antérieurs sont recalculés depuis ce CSV, et les scores et décisions correspondent exactement à ceux du service. Dans la dernière exécution locale, le chargement et la vérification du modèle et de la base prennent **3,44 ms**. Par requête, médianes sur ces quatre cas : lecture et historique **6,92 ms**, construction des variables **0,43 ms**, prédiction **0,19 ms**. Une autre exécution a donné **11,09 ms**, **2,47 ms**, **0,47 ms** et **0,20 ms** respectivement : ces petits échantillons varient et ne mesurent ni débit, ni contention, ni latence garantie.
- `EXPLAIN QUERY PLAN` indique `SEARCH transactions USING COVERING INDEX transactions_dest_step_id (name_dest=? AND step<?)` pour le comptage. Le serveur a été lancé sur `127.0.0.1:8765` et les requêtes HTTP réelles ont renvoyé 200 pour `/health`, 200 pour `/score` et 400 pour un identifiant invalide. L'environnement restreint a nécessité une autorisation pour l'accès local au port.
- `uv lock --check`, `uv sync --locked` et `uv run --locked` ont réussi ici avec un cache temporaire. Linux et Windows n'ont pas été testés. Une alerte de dépréciation de `TestClient` concernant `httpx` apparaît, sans échec des tests.

La procédure de cohérence locale, sans label, est `python scripts/check_scoring_api.py`. Elle ne publie ni identifiants, ni scores individuels. Le script de service n'ouvre pas le CSV et le script de vérification n'ouvre pas la base de labels. Aucun réentraînement ou nouveau score global du test n'a été effectué.
