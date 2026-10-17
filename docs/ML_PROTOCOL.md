# Lot 4.1 : protocole ML proposé pour PaySim

**Statut : proposition en attente pour le lot 4.1 ; l'EDA initiale du lot 4.0 est clôturée.** Les frontières et les variables décrites ci-dessous ne sont pas retenues définitivement. Les cinq fenêtres walk-forward envisagées, la sélection du modèle et le choix du seuil restent à définir ou valider au lot 4.1 ; le découpage unique plus bas est une proposition antérieure, pas un plan walk-forward finalisé. Aucun modèle, transformation ajustée, seuil ou résultat de prédiction n'a encore été produit. Le [bilan EDA](EDA.md) et l'[audit des données](DATA_AUDIT.md) établissent les faits descriptifs utilisés ici. Le protocole vise une démonstration locale et reproductible sur le CSV PaySim audité, pas une garantie sur des transactions réelles.

## 1. Question et périmètre

Prédire un score de suspicion **avant l'exécution** d'une transaction à partir de champs connus à ce moment. `isFraud` est uniquement la cible hors ligne. `isFlaggedFraud` est uniquement une règle PaySim de comparaison lors de l'évaluation ; elle n'entre ni dans les variables ni dans le réglage du modèle. Les scénarios de démonstration du prototype restent hors des calculs de performance PaySim.

Le CSV brut vérifié par SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b` est la source reproductible. Les labels ne seront chargés que par le parcours ML hors ligne ; ils restent absents des outils d'enquête. Aucun chemin personnel, identifiant de compte ou numéro de ligne ne deviendra une variable.

## 2. Entrées de la première baseline

| Champ | Décision | Motif et limite |
| --- | --- | --- |
| `type` | Inclure | Connu à la création ; les fraudes observées sont concentrées dans deux types. Le type seul ne suffit pas à identifier une fraude. |
| `amount` | Inclure | Connu avant exécution ; son effet descriptif varie selon la tranche et le type. |
| `log1p(amount)` | Transformation candidate de `amount` pour la baseline linéaire | `log(1 + amount)` garde zéro défini et comprime l'étendue de 0 à 92 445 516,64 unités PaySim. Il peut rendre un effet du montant plus facile à représenter linéairement, sans garantir une meilleure prédiction. Il ne s'agit pas d'un troisième champ indépendant. |
| `step` | Conserver pour le découpage et les audits, exclure comme prédicteur initial | Les heures simulées montrent un calendrier des labels et des volumes atypique. L'utiliser comme entrée risquerait d'apprendre ce calendrier. Sa disponibilité au scoring ne suffit pas à justifier son inclusion. |
| Encodage cyclique de l'heure ou de la position hebdomadaire simulée | Variante à comparer sur validation, hors première baseline | Les profils agrégés suggèrent des motifs, mais ne démontrent ni un calendrier réel ni un gain prédictif. Sa définition et son évaluation restent à fixer au lot 4.1. |
| Soldes avant et après transaction, ainsi que différences, ratios et autres dérivés | Exclure | Les soldes après transaction ne sont pas disponibles pour un score avant exécution. Les soldes avant transaction montrent une signature du simulateur liée à la fraude, même s'ils semblent temporellement disponibles. |
| `nameOrig`, `nameDest`, identifiants de transaction, numéro de ligne source et empreinte du fichier | Exclure | Identifiants et provenance peuvent soutenir l'audit ou des consultations, mais risquent la mémorisation et n'apportent pas une variable métier démontrée pour cette première baseline. Le numéro de ligne n'est pas une chronologie. |
| `isFraud`, `isFlaggedFraud` | Exclure des prédicteurs | Cible et référence d'évaluation seulement. |

La baseline sera une **régression logistique** simple : encodage des cinq valeurs de `type` observées sur le train et transformation `log1p(amount)`, avec une éventuelle mise à l'échelle du montant ajustée sur le train. Un pipeline scikit-learn enregistrera l'ordre des colonnes et les transformations. Les catégories inconnues en validation ou test devront être prises en charge sans réajuster l'encodeur. Les paramètres statistiques de transformation, s'il y en a, seront estimés **uniquement sur le train**. `log1p` lui-même est déterministe et ne requiert pas d'ajustement.

Ce choix est explicable : on pourra voir l'effet du type et du montant, puis mesurer si LightGBM, entraîné plus tard avec les **mêmes informations de départ**, apporte quelque chose au-delà d'une relation logistique simple. Alternative pertinente : une règle manuelle sur type et montant serait très lisible, mais ses bornes seraient choisies à partir d'observations déjà faites sur tout le fichier. La régression logistique évite de figer ici une règle issue de l'EDA. La première baseline ne modélise pas directement les historiques de comptes, les interactions complexes entre type et montant ni les autres causes de fraude. Aucun niveau de performance n'est présumé. Le premier essai ne rééquilibrera pas les classes ; toute pondération ou autre variante devra être annoncée comme essai distinct, ajusté sur le train et choisi sans consulter le test.

## 3. Proposition de séparation chronologique

Les frontières suivent des semaines simulées complètes de 168 steps déjà décrites dans l'audit : deux premières semaines pour le train, troisième pour la validation, puis tout le reste pour le test. Elles fournissent des bornes simples, sans mélanger de steps et **sans rechercher des taux égaux ou un meilleur score**. Aucun ordre entre lignes d'un même step n'est supposé.

| Ensemble | Steps inclus | Steps distincts | Transactions | Normales `isFraud=0` | Fraudes `isFraud=1` | Taux de fraude | Part des lignes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 1 à 336 | 336 | 4 784 775 | 4 781 008 | 3 767 | 0,0787 % | 75,20 % |
| Validation | 337 à 504 | 168 | 1 279 261 | 1 277 407 | 1 854 | 0,1449 % | 20,11 % |
| Test | 505 à 743 | 239 | 298 584 | 295 992 | 2 592 | 0,8681 % | 4,69 % |
| Total | 1 à 743 | 743 | 6 362 620 | 6 354 407 | 8 213 | 0,1291 % | 100 % |

Ces effectifs et taux ont été **recalculés sur le CSV audité avec Polars** ; ce ne sont pas des résultats de modèle. Les sommes des trois ensembles retrouvent les totaux de l'audit. La forte baisse du volume vers la fin explique que le test couvre davantage d'heures que la validation mais beaucoup moins de transactions. Les taux augmentent aussi ; la validation et le test garderont leur distribution naturelle. Aucun tirage stratifié, sur-échantillonnage ou suppression de ligne n'y sera appliqué.

La référence `isFlaggedFraud` comporte respectivement 3, 3 et 10 signalements dans train, validation et test. Ces comptes décrivent la règle fournie par PaySim ; ils ne sont ni des labels de fraude supplémentaires ni des résultats de la future baseline.

Les périodes atypiques restent dans l'évaluation principale. En complément, le rapport décrira des tranches temporelles **définies par step avant tout score** : 505 à 672 (232 135 transactions, 1 792 fraudes), 673 à 720 (66 177, 528) et 721 à 743 (272, 272). Leur choix est informé par l'EDA déjà exposée et ne guidera aucun réglage du modèle. Leur somme retrouve le test. Les 23 derniers steps constituent une tranche à une seule classe ; elle ne sera ni supprimée ni utilisée seule pour classer les modèles. Des diagnostics par step pourront signaler les heures de faible volume selon leur effectif total, sans sélectionner ou supprimer des lignes selon `isFraud`. Ces diagnostics ne changent pas la métrique principale calculée sur tout le test.

**Exposition préalable :** l'EDA a examiné **l'ensemble du fichier, y compris les labels des futures périodes de validation et de test**, pour décrire montants, types, temps et soldes. Les bornes proposées sont donc informées par cette connaissance descriptive ; le test n'est pas entièrement aveugle pour l'analyste. À partir de l'approbation du protocole, le futur test restera exclu de l'ajustement des transformations, de l'entraînement, du choix de variables, du réglage des paramètres, du choix du seuil et de la comparaison de variantes. Il sera évalué une seule fois après gel du modèle et du seuil. Cela limite la fuite pendant le développement, sans effacer l'exposition EDA déjà survenue.

## 4. Comparaisons prévues et mesures

1. Entraîner la régression logistique sur le **train seulement**. Conserver sa sortie comme **score** ; ne pas l'appeler probabilité fiable sans examen de calibration.
2. Calculer sur validation les mêmes mesures pour la baseline, puis pour LightGBM entraîné avec `type` et `amount` seulement. Les deux modèles verront les mêmes informations, même si la représentation numérique du montant peut différer. Limiter et consigner les essais de paramètres sur validation pour réduire l'adaptation à cette période.
3. Évaluer séparément la règle binaire `isFlaggedFraud` comme référence PaySim, avec sa précision, son rappel, son nombre d'alertes et ses faux positifs. Il ne s'agit pas d'un modèle appris ni d'un score continu comparable en classement.
4. Après choix de la méthode et du seuil sur validation, conserver le pipeline **entraîné uniquement sur le train**, le seuil figé et les versions des données et bibliothèques ; appliquer cet ensemble une seule fois au test complet. Aucun réentraînement sur train + validation n'est prévu avant ce test, car il modifierait les scores associés au seuil choisi.

Définitions communes, avec `TP` fraude alertée, `FP` normale alertée, `FN` fraude non alertée et `TN` normale non alertée :

| Mesure | Définition et lecture |
| --- | --- |
| Prévalence | `(TP + FN) / N` : part réelle de fraudes de la période. Toujours publier avec les métriques. |
| PR-AUC opérationnelle ici : **Average Precision (AP)** | Somme des précisions pondérées par chaque augmentation du rappel lorsque le seuil parcourt les scores classés : `Σ (Rᵢ − Rᵢ₋₁) × Pᵢ`. Elle décrit le classement de la classe fraude sans fixer de seuil ; ce n'est pas l'aire obtenue par interpolation trapézoïdale. Publier aussi le nombre de positifs. |
| Précision au seuil | `TP / (TP + FP)` : parmi les alertes, part de fraudes. Si aucune alerte, elle est notée non définie, avec volume zéro. |
| Rappel au seuil | `TP / (TP + FN)` : parmi les fraudes, part alertée. |
| Volume d'alertes | `TP + FP`, en nombre et en part des transactions ; c'est la charge d'examen qu'impliquerait le seuil. |
| Faux positifs | `FP`, en nombre et, si des normales existent, `FP / (FP + TN)` ; ils constituent des alertes inutiles dans ce jeu étiqueté. |

Le seuil sera choisi **sur validation uniquement** à partir d'un tableau de compromis entre rappel, précision, alertes et faux positifs. Deux critères possibles à discuter avant de voir les résultats de modèle sont : maximiser le rappel sous une capacité d'alertes explicitement convenue, ou choisir un compromis de démonstration explicite si aucune capacité métier n'existe. Nous ne fixons pas ici de capacité, de coût de fraude ou d'objectif métier fictif. Une fois le critère convenu, la règle de départage et le seuil seront enregistrés avant l'accès aux résultats de test.

Un changement de prévalence modifie généralement la précision, même avec rappel et taux de faux positifs inchangés : `précision = (rappel × prévalence) / (rappel × prévalence + taux_FP × (1 − prévalence))`. Les seuils et volumes d'alertes peuvent aussi réagir à un changement de distribution des scores. Comparer la précision ou l'AP de validation et de test sans rappeler leurs taux de fraude serait trompeur. Une éventuelle évaluation de calibration sera un travail distinct avant toute présentation des scores comme probabilités fiables.

La tranche 721 à 743 contient uniquement des fraudes. Sans transactions normales, elle ne permet pas de mesurer les faux positifs ni une capacité à séparer les deux classes. Sa précision, lorsqu'il y a des alertes, et une éventuelle AP seraient mécaniquement peu informatives ; elles ne serviront pas à annoncer la performance. Les effectifs, alertes et rappels de cette tranche pourront être décrits comme diagnostic, tandis que les métriques principales utiliseront le test complet, qui contient les deux classes.

## 5. Vérification et prochaine décision

La vérification de ce lot porte sur le SHA-256 et les effectifs déjà audités, le recalcul des comptes par bornes, l'absence de step partagé et la somme des sous-périodes du test. Les comptes se reproduisent depuis la racine du dépôt, après téléchargement du CSV et installation selon le README, par exemple avec :

```sh
uv run --locked python - <<'PY'
import polars as pl

source = pl.scan_csv("data/raw/PS_20174392719_1491204439457_log.csv")
period = (
    pl.when(pl.col("step") <= 336).then(pl.lit("train"))
    .when(pl.col("step") <= 504).then(pl.lit("validation"))
    .otherwise(pl.lit("test"))
)
result = (
    source.select("step", "isFraud", "isFlaggedFraud")
    .with_columns(period.alias("ensemble"))
    .group_by("ensemble")
    .agg(
        pl.col("step").min().alias("premier_step"),
        pl.col("step").max().alias("dernier_step"),
        pl.len().alias("transactions"),
        (pl.col("isFraud") == 0).sum().alias("normales"),
        pl.col("isFraud").sum().alias("fraudes"),
        pl.col("isFlaggedFraud").sum().alias("signalees"),
    )
    .sort("premier_step")
    .collect()
)
print(result)
PY
```

Le contrôle de l'empreinte source reste celui de l'audit et du notebook EDA. Aucune dépendance ML n'est ajoutée et aucun entraînement n'est lancé. Lors de l'implémentation, enregistrer le pipeline avec `joblib`, l'ordre et la définition des variables, les frontières temporelles, le seuil, l'empreinte source, les versions Python/Polars/scikit-learn/LightGBM/joblib et les limites d'usage. SHAP viendra seulement après validation du parcours de prédiction, pour expliquer des scores sans les présenter comme causes.

**Décisions demandées avant implémentation :** valider ou modifier les bornes proposées, puis choisir le type de compromis de seuil à démontrer sans inventer de capacité d'enquête. Le reste du protocole reste sujet à discussion avant le lot d'entraînement.
