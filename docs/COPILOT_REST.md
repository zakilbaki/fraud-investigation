# Premier outil REST pour Copilot Studio

## Périmètre

La passerelle `scripts/serve_copilot_api.py` expose uniquement
`GET /transactions/{transaction_id}` sur `127.0.0.1`. Les routes de score,
dossiers, historiques et rapports ne sont pas présentes sur ce port.
La réponse contient les dix champs de consultation du [contrat API](API.md),
sans labels ni soldes après transaction. Cette passerelle lit seulement la
base applicative SQLite et ne charge pas le modèle ML.

La route exige l'en-tête `X-API-Key`. Le serveur compare sa valeur au secret
`FRAUD_INVESTIGATION_API_KEY` fourni par variable d'environnement. Un secret
absent, vide ou de moins de 32 caractères empêche le démarrage. Une clé absente
ou incorrecte renvoie HTTP 401, sans révéler sa valeur. Le secret ne figure ni
dans le dépôt, ni dans le fichier OpenAPI, ni dans les réponses. Ce secret
partagé protège la démonstration locale ; il ne fournit pas d'identité propre
à chaque utilisateur.

## Lancement et contrôle local

Depuis la racine du dépôt, avec l'environnement Python et la base applicative
déjà préparés, créer une clé aléatoire d'au moins 32 caractères et la conserver
hors de Git, par exemple dans un gestionnaire de mots de passe. Dans le
terminal zsh, la saisir sans l'afficher :

```sh
read -s "FRAUD_INVESTIGATION_API_KEY?Clé API : "
export FRAUD_INVESTIGATION_API_KEY
.venv/bin/python scripts/serve_copilot_api.py --database data/app/fraud.sqlite --port 8768
```

Dans un second terminal local, après avoir chargé la même clé dans une variable
d'environnement, remplacer l'identifiant par une transaction de la base :

```sh
curl -i http://127.0.0.1:8768/transactions/d83a6871a919fd644c774f3e65fbe41b
curl -i -H "X-API-Key: $FRAUD_INVESTIGATION_API_KEY" \
  http://127.0.0.1:8768/transactions/d83a6871a919fd644c774f3e65fbe41b
```

Le premier appel doit donner 401 et le second 200 si la base PaySim locale
auditée contient cet identifiant. Une clé fausse donne aussi 401 ; une transaction
inconnue avec la bonne clé donne 404. La passerelle lie toujours l'adresse
locale `127.0.0.1` et ne fournit pas elle-même HTTPS.

## Fichier OpenAPI à importer

[Le modèle Swagger v2](copilot/transaction_lookup.swagger.template.json) est
un JSON en anglais avec un unique `operationId`, `getTransactionById`, et une
définition `apiKey` placée dans l'en-tête `X-API-Key`. Son hôte `.invalid` est
volontairement inutilisable. **Ne pas importer le modèle tel quel.**

Une fois l'URL HTTPS réelle du futur tunnel connue, générer le fichier final :

```sh
.venv/bin/python scripts/export_copilot_openapi.py \
  --base-url "https://HOTE-REEL-DU-TUNNEL"
```

Remplacer la valeur entre guillemets par l'URL réelle, à la racine du tunnel.
Le script refuse HTTP, un chemin supplémentaire, les paramètres d'URL et un
hôte `.invalid`. Il écrit par défaut
`data/copilot/transaction_lookup.swagger.json`, exclu de Git. **C'est ce
fichier généré qu'il faudra importer dans Copilot Studio.** Il contient
l'hôte HTTPS, jamais la clé d'API. Si l'URL du tunnel change, régénérer le
fichier et revoir la connexion avant de la réutiliser.

La [documentation Microsoft actuelle sur l'outil REST](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-rest-api)
demande un fichier OpenAPI v2 en JSON. Elle propose l'authentification `API key`
avec un nom de paramètre et un emplacement `Header` ou `Query`. Pour cette API,
choisir `Header`, nom `X-API-Key`, et saisir la valeur de la clé uniquement lors
de la création de la connexion. Les descriptions et noms de champs de l'outil
sont en anglais, comme l'agent Copilot Studio. L'import réel et la création
de la connexion n'ont pas été effectués dans ce lot.

## Ce qu'il faudra pour le tunnel HTTPS

- Un service de tunnel accessible gratuitement dans les conditions de votre
  compte, capable de publier une URL HTTPS vers `127.0.0.1:8768` tout en
  transmettant l'en-tête `X-API-Key`.
- Le Mac et la passerelle doivent rester actifs pendant les essais. Le tunnel
  doit viser **ce port seulement**, pas les serveurs locaux qui exposent les
  autres routes du prototype.
- Une URL HTTPS réellement joignable depuis le service Copilot Studio, pas
  `localhost`. Si l'URL est temporaire, l'import et la connexion devront être
  mis à jour à chaque changement.
- Un essai de 401 sans clé et de 200 avec clé à travers le tunnel avant la
  connexion dans Copilot Studio. Il faudra ensuite tester la recherche d'une
  transaction existante et la réponse 404 pour un identifiant inconnu depuis
  l'outil importé.

Ce document ne choisit ni n'ouvre de tunnel. Il ne garantit pas que l'offre
gratuite d'un fournisseur reste disponible ni que l'import fonctionne dans
votre environnement Copilot Studio avant un essai réel.
