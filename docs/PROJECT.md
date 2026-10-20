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

## État du lot 4.0, étape 4

L'hypothèse de l'utilisateur sur les comptes à solde élevé a conduit à comparer le solde d'origine avant transaction au montant, pour `CASH_OUT` et `TRANSFER`. Une quasi-égalité apparaît pour la majorité des fraudes et aucune transaction normale de ces deux types à la précision vérifiée. [EDA.md](EDA.md) documente les effectifs, la limite d'interprétation et la recommandation provisoire d'écarter ce solde du futur modèle de portfolio à cause de la signature du simulateur. La traçabilité des transferts ne peut pas être vérifiée dans le CSV. Aucun modèle n'a été entraîné.

Une vérification complémentaire confirme que 8 008 des 8 197 fraudes de montant positif combinent un solde avant transaction proche du montant et un solde après transaction nul dans le CSV. La même valeur nulle après transaction apparaît aussi souvent dans les transactions normales ; elle ne suffit pas à qualifier une fraude. Les soldes après transaction restent exclus du futur modèle avant exécution.

## État du lot 4.0, étape 5

L'[EDA temporelle guidée](EDA.md) regroupe les steps en fenêtres descriptives fixes de 48 heures simulées. Deux figures montrent le volume et le taux de fraude global, puis les taux de `CASH_OUT` et `TRANSFER`, avec leurs effectifs. Des creux de volume et une dernière fenêtre courte de 272 transactions, toutes étiquetées fraude, rendent certains taux élevés délicats à interpréter. Les observations de l'utilisateur sont attendues avant d'approfondir les montants ou les soldes au fil du temps. Aucune frontière train/validation/test n'a été fixée et aucun modèle n'a été entraîné.

## État du lot 4.0, discussion temporelle complémentaire

Le contrôle au step individuel montre que les 23 derniers steps contiennent 272 fraudes sur 272 transactions, mais que 320 steps dans l'ensemble du CSV ne contiennent aussi que des fraudes, avec de très petits effectifs. Les nombres de fraudes `CASH_OUT` et `TRANSFER` sont identiques dans 721 des 743 steps ; 4 075 fraudes de chaque type sont appariables par même step et même montant, sans lien de comptes démontré. [EDA.md](EDA.md) documente ces résultats et les limites d'interprétation. Aucun step n'est exclu et l'usage de `step` comme variable prédictive reste ouvert ; son rôle pour un futur découpage temporel est distinct. Aucun entraînement n'a été effectué.

## État du lot 4.0, diagnostic des comptes candidats

Le [diagnostic limité](EDA.md) des fraudes `TRANSFER` et `CASH_OUT` de même step et montant compte 4 023 groupes candidats, dont 26 ambigus par répétition du montant. La vérification exacte `TRANSFER.nameDest = CASH_OUT.nameOrig` trouve zéro groupe et zéro transaction liée ; un contrôle indépendant par ensembles confirme ce résultat. Une correspondance de montant ne démontre donc ni une identité de compte ni l'ordre des opérations dans un step. Le notebook et la documentation sont mis à jour avec des exemples du CSV. Aucun scénario synthétique n'a été créé et aucun modèle n'a été entraîné ; les observations de l'utilisateur sont attendues avant de conclure l'EDA.

## Synthèse provisoire du lot 4.0 et protocole 4.1 en attente

Cette étape avait préparé une [synthèse EDA](EDA.md) des observations, hypothèses, risques de modélisation et limites de l'investigation des comptes. L'exploration avait exposé l'ensemble du CSV, labels compris, avant les profils cycliques simulés. Cette exposition reste déclarée dans le [protocole ML proposé](ML_PROTOCOL.md).

Une première version du protocole envisageait `type` et `amount`, `log1p(amount)` pour la baseline linéaire et un découpage unique train 1 à 336, validation 337 à 504, test 505 à 743. **Ce découpage unique a été remplacé au lot 4.1** par les cinq fenêtres walk-forward décrites dans [ML_PROTOCOL.md](ML_PROTOCOL.md). Les soldes, identifiants, provenance et `step` brut restent exclus des prédicteurs initiaux ; `step` conserve son rôle d'ordre temporel. Aucun entraînement ni choix de seuil n'a eu lieu à cette étape.

## État du lot 4.0, profils cycliques simulés

À cette étape, le lot 4.0 était encore ouvert. Le [notebook EDA](../notebooks/eda_paysim.ipynb) et [EDA.md](EDA.md) utilisent **uniquement comme convention d'analyse** `step = 1` lundi à 00 h, un step par heure, pour comparer les profils horaires et les jours de semaine simulés. Deux figures à trois panneaux affichent volumes, fraudes et taux ; les tableaux donnent les steps observés et les moyennes par step. Chaque regroupement retrouve les 6 362 620 transactions et 8 213 fraudes. La dernière journée, mercredi simulé incomplet de 23 heures avec 272 fraudes sur 272 transactions, est conservée et signalée. PaySim ne fournit pas de calendrier civil confirmant ces libellés. Aucune variable cyclique ni frontière ML définitive n'est retenue et aucun entraînement n'a eu lieu.

## État du lot 4.0, contrôle du motif hebdomadaire

Le [contrôle par journée et par semaine](EDA.md) conserve les 743 steps et compare les normales et fraudes par heure observée, séparément dans quatre semaines complètes et la cinquième semaine partielle. Parmi les deux plus faibles positions de chaque semaine complète, vendredi revient quatre fois, tandis que la seconde position alterne entre mercredi et samedi. Deux positions fixes de creux ne sont donc pas établies. Les fraudes par heure varient beaucoup moins que le volume normal ; les hausses de taux correspondent surtout aux petits dénominateurs. Les figures signalent la dernière journée de 23 h, avec 0 normale et 272 fraudes, et les positions absentes de la dernière semaine. Le notebook vérifie 6 362 620 transactions, 8 213 fraudes et 743 steps. Aucune variable cyclique, frontière ML définitive ou phase d'entraînement n'a été engagée.

## Clôture du lot 4.0 : EDA initiale

Le [notebook reproductible](../notebooks/eda_paysim.ipynb), les [figures](figures/) et la [synthèse finale](EDA.md) couvrent le déséquilibre des classes, les montants, les types, les soldes, les variations temporelles, les profils simulés et le diagnostic limité des comptes. Le CSV analysé contient **6 362 620 transactions, dont 8 213 fraudes**, sur **743 steps**. Le vendredi simulé est régulièrement dans les deux positions hebdomadaires de plus faible volume normal, mais l'autre position varie ; aucun effet civil ou mécanisme de fraude n'est établi. Les soldes avant transaction portent une forte signature synthétique ; les soldes après transaction sont indisponibles pour un score avant exécution. Les égalités de step et montant entre transferts et retraits ne démontrent pas une chaîne financière. Les données et labels du futur test ont été vus pendant l'EDA, exposition déclarée dans le [protocole ML provisoire](ML_PROTOCOL.md).

L'analyse a été réexécutée depuis un espace de variables neuf avec `scripts/run_eda_notebook.py` et le Python de l'environnement local, sur macOS Apple Silicon avec Python 3.11. La commande générique `uv run --locked` du README n'a pas abouti dans cet environnement restreint à cause du cache et d'une tentative d'accès réseau ; elle n'est donc pas comptée comme vérification réussie. Les contrôles du notebook ont passé, notamment l'empreinte SHA-256, les totaux, les 743 steps, les zéros et les durées incomplètes. Les figures SVG sont régénérées par le script ; les PNG publiés servent à la lecture. Aucun modèle n'a été entraîné, aucune performance prédictive n'est mesurée. Au lot 4.1, il restera à finaliser le protocole, notamment les cinq fenêtres walk-forward envisagées, les variantes, la sélection du modèle et le seuil. Le lot 4.1 ne commence pas avec cette clôture.

## État du lot 4.1 : protocole ML avant entraînement

Le [protocole révisé](ML_PROTOCOL.md) remplace le découpage unique par **cinq validations de 72 steps**, chacune précédée d'un entraînement croissant : 1 à 144 puis 145 à 216, jusqu'à 1 à 432 puis 433 à 504. Les effectifs et taux des dix ensembles ont été recalculés sur le CSV audité ; **les deux classes sont présentes partout**. La cinquième validation ne contient que **55 620 transactions**, dont **764 fraudes (1,3736 %)**, ce qui rend indispensable la lecture des résultats par fenêtre avec leur prévalence. Le test **505 à 743** reste réservé à l'évaluation finale : 298 584 transactions, 2 592 fraudes (0,8681 %), y compris sa dernière tranche uniquement frauduleuse. L'exposition antérieure de ses données et labels pendant l'EDA reste déclarée.

La phase 1 prévoit **11 candidats**, du `DummyClassifier` aux modèles linéaires, probabilistes, arbres et ensembles scikit-learn, puis LightGBM, XGBoost et CatBoost. KNN, SVM à noyau et petit réseau de neurones font l'objet d'une décision de faisabilité documentée ; un résultat sur sous-ensemble ne rejoindra pas le classement des cinq fenêtres complètes. Chaque candidat part des mêmes informations `type` et `amount`, avec un prétraitement adapté et ajusté uniquement sur son train. La phase 2 est bornée à trois candidats retenus plus la référence logistique éventuelle, avec au plus deux variantes par candidat. L'heure simulée en sinus/cosinus est une variante séparée ; aucune variable hebdomadaire ni solde n'est retenu dans la comparaison initiale.

Cette version initiale prévoyait l'Average Precision pour sélectionner les pipelines et F1 maximal sur 433 à 504 pour choisir le seuil final. Elle a été **remplacée par la révision ci-dessous**, qui choisit chaque seuil avant la validation extérieure et classe les pipelines selon leur F1 moyen. Aucun modèle n'a été entraîné, aucune métrique prédictive n'a été calculée et aucune dépendance ML n'a été ajoutée.

## Clôture du lot 4.1 : choix du seuil

Le choix intermédiaire était **F1 maximal sur 433 à 504** après une sélection des modèles par Average Precision. La révision demandée ensuite le remplace : cette période est maintenant une **validation extérieure uniquement**, dont le seuil a été choisi sur 361 à 432. Les autres fenêtres suivent la même séparation interne. Le [protocole courant](ML_PROTOCOL.md) fait foi ; aucun entraînement ni score prédictif n'a été produit à cette étape.

## Révision du lot 4.1 : métriques et réserves internes

Les seules métriques prédictives principales seront **précision, rappel et F1**. Elles seront publiées pour chacun des 11 modèles prévus sur chacune des cinq validations extérieures, puis moyennées arithmétiquement sur les cinq fenêtres. Le **F1 moyen** décidera du modèle, avec régularité, coût et simplicité pour départager des résultats proches. Alertes, faux positifs et faux négatifs resteront visibles. L'Average Precision ne sert plus à la sélection.

Chaque train réserve ses **72 derniers steps** au choix du seuil F1, après l'apprentissage du modèle et de ses prétraitements sur les steps antérieurs. Les cinq réserves internes et les cinq portions d'apprentissage contiennent chacune normales et fraudes ; leurs effectifs vérifiés figurent dans [ML_PROTOCOL.md](ML_PROTOCOL.md). La validation extérieure n'ajuste ni modèle, ni transformation, ni seuil. Pour le pipeline final, le protocole conserve l'ajustement sur **1 à 360**, le seuil choisi sur **361 à 432**, puis évalue sans nouveau réglage sur **433 à 504** et enfin sur le test préservé **505 à 743**. Cette procédure utilise moins de données pour l'ajustement final, mais évite d'optimiser le seuil sur la période dont le F1 de comparaison est annoncé. Aucun entraînement n'a eu lieu pendant cette révision.

## Lot 4.2 : première comparaison des modèles

Le [rapport détaillé](ML_BENCHMARK.md) et ses [résultats structurés](results/ml_benchmark.json) présentent **13 candidats terminés sur les cinq fenêtres complètes** : les onze familles obligatoires du protocole, un petit réseau de neurones et KNN. Le SVM à noyau a été essayé sur la première fenêtre complète puis interrompu lors du contrôle de coût, sans score comparable. Les graphiques montrent les moyennes de précision, rappel et F1 ainsi que le F1 de chaque période. Les alertes, faux positifs, fraudes manquées, temps et tailles de modèles restent visibles.

Selon la règle préannoncée, XGBoost est le **choix provisoire de phase 1** avec un F1 moyen de **0,2818**, contre **0,2814** pour CatBoost. Le départage entre ces deux résultats proches passe par le temps médian d'ajustement : **2,0 s** contre **11,5 s** sur ce Mac. Le rappel moyen XGBoost n'est que **0,1752** ; ses cinq validations totalisent **3 289 fraudes manquées**. Ce résultat ne démontre ni une supériorité générale de l'algorithme, ni une performance bancaire réelle. Les modèles utilisent les mêmes colonnes `type` et `amount`, mais des représentations et paramètres initiaux adaptés à leurs familles. Plusieurs candidats varient fortement entre périodes ; les causes restent à tester après discussion avec l'utilisateur.

Les métriques proviennent uniquement des validations extérieures jusqu'au step 504. Les seuils ont été choisis dans les réserves internes antérieures ; aucun score du test 505 à 743 n'a été calculé. Les labels de ce futur test avaient déjà été exposés pendant l'EDA, limite toujours déclarée. Le CSV conserve l'empreinte attendue. L'exécution locale a utilisé Python 3.11, au plus quatre fils, une limite de 30 minutes par fenêtre et 75 % de RAM physique par processus ; les 65 comparaisons complètes ont réussi sous ces plafonds. Les contrôles unitaires du seuil et du départage, ainsi que les tests existants, ont réussi. Linux et Windows restent non testés. La prochaine étape est de lire ensemble les écarts observés et de fixer les expériences d'approfondissement prévues au protocole ; aucun modèle final ni score de test n'est encore produit.

## Lot 4.3 en cours : vérification et première lecture

Le [diagnostic guidé](ML_DIAGNOSTICS.md) a vérifié les 65 résultats de modèles, les trois portions chronologiques de chaque fenêtre, les quatre cases des matrices de confusion et les moyennes. Les règles du protocole maintiennent XGBoost comme choix provisoire sans modifier les scores ni le classement. La précision de `isFlaggedFraud` est désormais indiquée **non définie** aux fenêtres 3 et 5, où il n'y a aucune alerte ; cette correction ne touche aucun résultat de modèle. Le SVM a été interrompu avant le plafond de 30 minutes, sans dépassement démontré. Une figure compare précision, rappel et F1 de cinq modèles sur les cinq fenêtres avec effectifs et taux de fraude. La discussion de cette première lecture précède les diagnostics par type et montant. Aucun entraînement supplémentaire ni score du test final n'a été produit à cette étape.

## Lot 4.3 : réorientation vers les ajouts contrôlés

Le responsable du projet remplace la suite descriptive annoncée ci-dessus par trois expériences séparées sur les cinq premiers modèles du F1 moyen initial : XGBoost, CatBoost, Extra Trees, Random Forest et KNN. L'[amendement du protocole](ML_PROTOCOL.md) fixe, avant les mesures, A = référence `type + amount` plus heure simulée en sinus/cosinus, puis B = référence plus `oldbalanceOrg`, puis C = référence plus `oldbalanceDest`. Chaque ajout repart de la référence, conserve les cinq fenêtres et choisit son seuil dans la réserve interne. Le précédent budget de deux variantes par candidat est remplacé pour cette étape. Les soldes restent exclus de la baseline et ne sont autorisés que dans les expériences de sensibilité B et C. L'expérience A est la seule engagée maintenant ; B et C attendent chacune une discussion. Aucun score du test 505 à 743 ne sera utilisé.

### Expérience A terminée, discussion attendue

Les [25 validations et leurs écarts à la référence](ML_FEATURE_HOUR.md), les [résultats structurés](results/ml_feature_hour.json) et deux [figures](figures/) sont publiés. Les cinq F1 moyens augmentent avec l'heure simulée : XGBoost de **0,2818 à 0,4065**, CatBoost de **0,2814 à 0,4042**, Extra Trees de **0,2580 à 0,3147**, Random Forest de **0,2483 à 0,2652** et KNN de **0,2263 à 0,2938**. Les rappels moyens augmentent aussi, mais les précisions moyennes baissent. Pour XGBoost, les cinq validations cumulent **1 219 fausses alertes** contre **288** en référence, et **2 653 fraudes manquées** contre **3 289**. L'amélioration F1 de XGBoost et CatBoost apparaît dans chaque fenêtre ; Extra Trees et Random Forest subissent en revanche une forte dégradation en fenêtre 3, avec respectivement **8 729** et **9 418** faux positifs dans cette validation. Le seul F1 moyen masquerait ce risque.

L'exécution sur macOS Apple Silicon avec Python 3.11 a achevé les 25 ajustements sous les plafonds de 30 minutes et 75 % de RAM par processus. Les 13 tests du dépôt passent ; l'empreinte du CSV, les bornes, effectifs, versions, colonnes, cases de confusion, moyennes et fichiers JSON publiés ont été vérifiés. Les premières références n'ont pas été réentraînées. Cette étape a utilisé le Python de l'environnement local ; la commande générique `uv run --locked` du README n'a pas été réexécutée pour A. Les cinq fenêtres restent dépendantes et la dernière validation a une prévalence particulière. L'heure est une position simulée, sans calendrier civil ni preuve de cause métier. Aucun score du test final n'a été consulté ; ses labels avaient néanmoins été vus pendant l'EDA. Linux et Windows ne sont pas testés. Les expériences B et C n'ont pas commencé et attendent le retour de l'utilisateur sur A.

### Expérience B engagée, protocole préalable

L'utilisateur demande maintenant B seule, `type + amount + oldbalanceOrg`, contre la référence initiale. Le [protocole](ML_PROTOCOL.md) conserve les cinq modèles, leurs paramètres et les trois portions de chaque fenêtre. Les arbres et CatBoost recevront le solde initial brut ; KNN recevra `log1p(oldbalanceOrg)` standardisé sur l'apprentissage seul, comme prévu avant les résultats. Le contrôle des **6 064 036** lignes jusqu'au step 504 ne trouve ni solde manquant ni valeur négative. Les résultats de A restent séparés. Aucun score de B n'est encore annoncé à ce stade ; C et le test final restent en attente.

**Révision en cours de B :** KNN est retiré des nouvelles exécutions pour son coût de prédiction et de stockage, et pour simplifier le prototype, sans conclusion générale sur sa qualité prédictive. Ses résultats complets de référence et de A restent conservés ; trois fenêtres B achevées avant l'interruption seront rapportées séparément, sans moyenne sur cinq fenêtres. B continue sur XGBoost, CatBoost, Extra Trees et Random Forest. C n'est pas commencée et, si autorisée, utilisera ces quatre modèles. L'interruption a ciblé KNN ; les vingt fenêtres B des quatre autres modèles sont terminées et sauvegardées localement.

### Expérience B terminée, discussion attendue

Le [rapport B](ML_FEATURE_BALANCE_ORG.md), ses [résultats structurés](results/ml_feature_balance_org.json) et trois figures présentent **20 validations complètes** pour les quatre modèles conservés, comparées aux résultats vérifiés de `type + amount`. Les F1 moyens passent de **0,2818 à 0,6137** pour XGBoost, de **0,2814 à 0,5774** pour CatBoost, de **0,2580 à 0,3454** pour Extra Trees et de **0,2483 à 0,4812** pour Random Forest. XGBoost, CatBoost et Random Forest progressent en F1 dans les cinq fenêtres ; Extra Trees baisse en fenêtre 3 à **0,0452**, avec **9 347 fausses alertes** sur cette période. Sur cinq validations, XGBoost réduit les fraudes manquées de **3 289 à 1 863**, en faisant passer les faux positifs de **288 à 859**. CatBoost réduit les fraudes manquées de **3 290 à 2 232**, avec **351** faux positifs contre **287** en référence. Ces différences décrivent les pipelines enrichis avec leurs seuils internes réestimés, sans prouver une meilleure généralisation hors de PaySim.

Les trois premières fenêtres KNN de B sont conservées comme **résultats partiels**, sans moyenne ni classement avec les quatre autres modèles. La troisième a demandé **51,1 s de prédiction extérieure** et la représentation sérialisée en mémoire atteint **284,8 Mio** ; sa réserve interne a aussi demandé du temps de prédiction. Le benchmark de référence avait mesuré **467,2 Mio** pour KNN en fenêtre 5. Ces coûts motivent son retrait pratique, sans affirmer qu'il est toujours moins précis. L'empreinte du CSV, les bornes, colonnes, transformations, matrices de confusion, métriques, versions et liens sont vérifiés. L'exécution de B a utilisé le Python 3.11 de l'environnement local sur macOS Apple Silicon. La commande générique `uv run --locked` du README n'a pas été relancée pour B ; Linux et Windows restent non testés. Aucun score des steps 505 à 743 n'a été consulté. Le test reste imparfaitement aveugle pour l'analyste du fait de l'EDA. C attend le retour de l'utilisateur.

## Lot 4.3, expérience C : préparation

L'utilisateur autorise C seule : `type + amount + oldbalanceDest`, comparée à la référence pour XGBoost, CatBoost, Extra Trees et Random Forest. KNN reste exclu des prochains calculs ; ses résultats antérieurs sont conservés. Avant les résultats, le [protocole](ML_PROTOCOL.md) fixe le solde destinataire brut en `float32`, sans remplacement des zéros, et les mêmes cinq fenêtres, paramètres et réserves de seuil que la référence. Sur les steps 1 à 504, 2 047 519 identifiants destinataires préfixés `M` ont tous un solde enregistré nul ; 522 724 autres destinataires ont aussi zéro. La fiche du jeu indique que certains soldes commerçants ne sont pas disponibles : zéro n'établit donc pas un compte vide. Aucun score de C ni du test final n'est encore annoncé à ce stade.

### Expérience C terminée, discussion attendue

Le [rapport C](ML_FEATURE_BALANCE_DEST.md), les [résultats structurés](results/ml_feature_balance_dest.json) et [trois figures](figures/) comparent les vingt validations de C aux résultats de référence déjà vérifiés. Le F1 moyen passe de 0,2818 à 0,2836 pour XGBoost, de 0,2814 à 0,2447 pour CatBoost, de 0,2580 à 0,2489 pour Extra Trees et de 0,2483 à 0,2661 pour Random Forest. Dans la troisième fenêtre, C produit 2 894 FP pour CatBoost, 2 341 pour Extra Trees et 1 465 pour Random Forest ; les moyennes seules masquent ces dégradations. Les résultats A et B restent séparés. Aucun ajout n'est retenu automatiquement et aucun modèle combinant les variables n'a été entraîné.

Les vingt calculs se terminent sans dépassement des plafonds. Les tests ciblés, l'empreinte du CSV, les bornes, effectifs, colonnes, prétraitements, paramètres, matrices de confusion, métriques, versions et rapports ont été vérifiés sur macOS Apple Silicon avec le Python 3.11 de l'environnement local. Les commandes génériques `uv run --locked` du README, Linux et Windows n'ont pas été testés dans cette étape. Aucun score du test 505 à 743 n'a été consulté ; ses labels avaient déjà été vus pendant l'EDA. C reste une analyse de sensibilité au simulateur et à la disponibilité ambiguë du solde destinataire. La prochaine décision appartient à la discussion avec l'utilisateur.

## Lot 4.3, expérience D : préparation

L'utilisateur autorise D seule, comparée principalement à [B](ML_FEATURE_BALANCE_ORG.md) : ajouter à `type + amount + oldbalanceOrg` les deux coordonnées de l'heure simulée déjà définies pour A. Le [protocole](ML_PROTOCOL.md) fixe ce traitement avant les résultats, sur XGBoost, CatBoost, Extra Trees et Random Forest, avec les mêmes paramètres, cinq fenêtres et choix de seuil interne. B est réutilisée sans réentraînement. `oldbalanceDest`, les soldes après transaction, ratios, identifiants et labels restent hors des prédicteurs. Aucun résultat D ni score du test final n'est encore annoncé à ce stade.

### Expérience D terminée, discussion attendue

Le [rapport D](ML_FEATURE_BALANCE_ORG_HOUR.md), ses [résultats structurés](results/ml_feature_balance_org_hour.json) et trois figures documentent vingt validations complètes. Face à B, le F1 moyen passe de 0,6137 à 0,7022 pour XGBoost, de 0,5774 à 0,6683 pour CatBoost, de 0,3454 à 0,3710 pour Extra Trees et de 0,4812 à 0,4778 pour Random Forest. XGBoost et CatBoost progressent sur les cinq fenêtres ; Extra Trees garde 9 064 fausses alertes et un F1 de 0,0651 dans la troisième. Le gain n'est donc ni universel ni suffisant pour annoncer un modèle final. Les seuils ont été réestimés dans chaque réserve interne. Aucun score du test 505 à 743 n'a été consulté.

Le contrôle de l'empreinte du CSV, les tests ciblés, les bornes, effectifs, colonnes, transformations, versions, paramètres, matrices de confusion et moyennes ont été vérifiés avec le Python 3.11 local sur macOS Apple Silicon. B a été réutilisée sans réentraînement. Les commandes génériques `uv run --locked` du README, Linux et Windows n'ont pas été testés pour D. Les fichiers bruts, journaux, bases, prédictions individuelles, environnements et secrets restent hors de Git. La signature du simulateur entre montant et solde émetteur, l'heure simulée, les apprentissages qui se recouvrent, les validations réutilisées et l'exposition ancienne des labels du test limitent l'interprétation. La prochaine décision appartient à la discussion avec l'utilisateur.

## Lot 4.4 : plan interrompu et nouveau parcours E, F, G

**Plan interrompu et remplacé avant toute exécution.** Le commit `6810dff` avait figé des variantes d'hyperparamètres, mais aucun code, entraînement, score ni résultat partiel d'optimisation n'a été produit. Le dépôt était propre lors de la reprise. Les commandes de liste des processus ont été refusées par l'environnement restreint ; aucun processus d'optimisation lancé dans cette conversation n'était encore suivi. Aucun fichier n'a été supprimé ni historique Git réinitialisé.

**Nouveau plan 4.4.** Le [protocole](ML_PROTOCOL.md) fixe E = D plus `amount / oldbalanceOrg` défini uniquement pour un solde positif, puis F = D plus nombre de sorties antérieures de l'émetteur, puis G = D plus nombre d'entrées antérieures du destinataire. Ces ajouts sont séparés et limités à XGBoost et CatBoost aux paramètres de D. E seule est autorisée maintenant ; F et G attendent une discussion après chaque résultat. Le test 505 à 743 reste réservé.

Historique du plan abandonné : la proposition initiale fixait trois variantes de réglage par modèle, au plus 30 ajustements, XGBoost avant CatBoost. Elle n'a pas été exécutée et ne guide plus le lot.

### Expérience E terminée, discussion attendue

Le [rapport E](ML_FEATURE_BALANCE_SHARE.md), les [résultats structurés](results/ml_feature_balance_share.json) et trois figures comparent D à D plus `part_solde`, séparément sur XGBoost et CatBoost. Le F1 moyen passe de **0,7022 à 0,8674** pour XGBoost et de **0,6683 à 0,8634** pour CatBoost ; chaque fenêtre progresse. Les rappels moyens passent respectivement de **0,5924 à 0,8520** et de **0,5463 à 0,8450**. Sur les cinq validations, XGBoost détecte 3 395 fraudes contre 2 356 avec D, avec 466 fausses alertes contre 364 ; CatBoost détecte 3 370 fraudes contre 2 176, avec 459 fausses alertes contre 350. Le ratio peut rendre particulièrement visible une signature artificielle du simulateur ; ce gain ne démontre pas une généralisation réelle.

Les dix exécutions terminent sous les plafonds de 30 minutes et 75 % de RAM par processus. Les tests synthétiques, le traitement natif des valeurs manquantes par les deux modèles, l'empreinte du CSV, les trois portions de chaque fenêtre, les colonnes, paramètres, versions, matrices de confusion et moyennes ont été vérifiés avec le Python 3.11 local sur macOS Apple Silicon. La commande générique `uv run --locked` n'a pas été exécutée pour E ; Linux et Windows ne sont pas testés. D a été réutilisée sans réentraînement. Aucun score des steps 505 à 743 n'a été consulté, mais leurs labels avaient été vus lors de l'EDA. F reste en attente des observations de l'utilisateur ; G n'a pas commencé. Aucun modèle final n'est retenu.

### Expérience F : couverture préalable, entraînement suspendu

À la demande de l'utilisateur, le [diagnostic de couverture](ML_SENDER_HISTORY_COVERAGE.md) précède tout entraînement F. Le compteur d'émissions du même compte aux steps strictement antérieurs est non nul pour **8 438 / 6 064 036 transactions**, soit **0,1391 %** sur les steps 1 à 504, et vaut au maximum **2**. Sur les cinq validations extérieures, la couverture va de **0,1013 %** à **0,2535 %**. Le regroupement par compte et step conserve les doublons apparents et ne s'appuie pas sur l'ordre des lignes. Les tests synthétiques et les effectifs des portions sont vérifiés ; le calcul n'a lu que `step` et `nameOrig`, sans labels, autres prédicteurs ni données du test final. Cette faible couverture doit être discutée avant les modèles F. G n'a pas commencé.

**Décision : F est mis de côté sans entraînement.** La faible couverture ne démontre pas que le compteur est inutile pour les rares transactions concernées. Le diagnostic reste publié. La prochaine étape autorisée est uniquement le contrôle de couverture de G, avant toute décision d'entraînement.

### Expérience G : couverture préalable, aucun entraînement

Le [rapport de couverture G](ML_RECIPIENT_HISTORY_COVERAGE.md), les [agrégats structurés](results/ml_recipient_history_coverage.json) et la [figure](figures/ml_recipient_history_distribution.png) décrivent uniquement le compteur des réceptions de `nameDest` aux steps strictement antérieurs. Sur les steps 1 à 504, **3 427 028 / 6 064 036 transactions**, soit **56,5140 %**, ont un historique non nul ; la valeur maximale est **112**. Dans les cinq validations extérieures, la couverture varie de **54,430 % à 57,372 %**. Cette présence permet d'envisager l'expérience G, sans préjuger de son gain ni de sa généralisation. Le diagnostic ne lit que `step` et `nameDest`, sans labels ni lignes analytiques du test final ; le fichier entier est seulement haché pour vérifier son identité. Les tests synthétiques et les totaux sont vérifiés. F reste mis de côté. Aucun modèle G ou final n'a été entraîné.

**G autorisée après discussion, avant les scores.** Le protocole fixe le compteur brut en `float32`, sans transformation apprise, ajouté seul aux cinq entrées de D pour XGBoost et CatBoost. Les mêmes cinq triples chronologiques, paramètres et seuils internes s'appliquent. F reste sans entraînement ; E n'est pas combinée. Aucun score G n'est encore annoncé à ce stade.

### Expérience G terminée, discussion attendue

Le [rapport G](ML_FEATURE_RECIPIENT_HISTORY.md), ses [résultats structurés](results/ml_feature_recipient_history.json) et trois figures comparent les dix validations G aux dix résultats D déjà vérifiés. XGBoost passe d'un F1 moyen de **0,7022 à 0,7835**, avec **2 909** fraudes détectées contre **2 356**, et **550** fausses alertes contre **364** sur les cinq validations. CatBoost passe de **0,6683 à 0,7123**, avec **2 528** fraudes détectées contre **2 176**, et **596** fausses alertes contre **350**. Le F1 progresse dans chaque fenêtre pour les deux modèles, mais la précision moyenne baisse et la dispersion des F1 augmente. Le compteur a une couverture élevée, sans que cela prouve à lui seul une valeur prédictive ou une cause liée au destinataire.

Les dix calculs finissent sous les plafonds de 30 minutes et 75 % de RAM. La construction répétée de l'historique demande **10,0 s** au total dans les cinq processus XGBoost et **9,8 s** dans les cinq processus CatBoost ; le pic RSS échantillonné est respectivement **2,08 Gio** et **2,63 Gio**. Les tests synthétiques, l'empreinte du CSV, les bornes, effectifs, colonnes, prétraitements, paramètres, versions, couvertures, matrices de confusion et moyennes sont vérifiés avec le Python 3.11 local sur macOS Apple Silicon. La commande générique `uv run --locked`, Linux et Windows ne sont pas testés pour G. D n'a pas été réentraînée ; les steps 505 à 743 n'ont pas été évalués. Leurs labels avaient été vus pendant l'EDA. F reste mis de côté, E n'est pas combinée et aucun modèle final n'est annoncé.

### Expérience H : protocole préalable

L'utilisateur autorise H seule pour mesurer si l'historique destinataire de G apporte encore quelque chose en présence du ratio de E. Le [protocole](ML_PROTOCOL.md) fixe avant les scores la combinaison D plus le ratio exact de E et le compteur strictement antérieur exact de G, sans autre entrée. XGBoost et CatBoost gardent leurs paramètres, cinq fenêtres et seuils internes ; E et G seront réutilisées sans réentraînement. F reste mis de côté et le test final est réservé. Aucun score H n'est encore annoncé à ce stade.

### Expérience H terminée, discussion attendue

Le [rapport H](ML_FEATURE_RATIO_RECIPIENT_HISTORY.md), les [résultats structurés](results/ml_feature_ratio_recipient_history.json) et trois figures comparent H surtout à E, puis à G. Pour XGBoost, le F1 moyen passe de **0,8674 (E) à 0,8948 (H)** ; pour CatBoost, de **0,8634 à 0,8976**. H réduit les fausses alertes cumulées de **466 à 203** pour XGBoost et de **459 à 173** pour CatBoost ; les fraudes détectées passent respectivement de **3 395 à 3 388** et de **3 370 à 3 385**. XGBoost améliore son F1 dans quatre fenêtres sur cinq face à E, avec une légère baisse de **0,0013** dans la cinquième ; CatBoost progresse dans les cinq. Le F1 minimum augmente et sa dispersion descriptive diminue pour les deux. Ces résultats soutiennent une complémentarité pratique du compteur et du ratio dans PaySim, sans effet causal démontré ni garantie sur des données réelles.

Les dix calculs finissent sous les plafonds existants. La construction de l'historique prend **10,5 s** au total pour les cinq processus XGBoost et **10,1 s** pour les cinq processus CatBoost ; la construction des tableaux de variables ajoute respectivement **1,6 s** et **0,7 s**. Les pics RSS échantillonnés sont **2,12 Gio** et **2,77 Gio**. Les tests ciblés et généraux, l'empreinte du CSV, les bornes, effectifs, colonnes, versions, paramètres, compteurs, ratios manquants, matrices de confusion et moyennes ont été vérifiés avec le Python 3.11 local sur macOS Apple Silicon. La commande générique `uv run --locked`, Linux et Windows n'ont pas été testés pour H. E et G ont été réutilisées, F n'a pas été entraînée, aucun score 505 à 743 n'a été consulté et aucun modèle final n'est annoncé.

### Réglages limités de H : protocole préalable

Le [protocole](ML_PROTOCOL.md) fige avant les nouveaux scores trois variantes par famille, profondeur réduite, régularisation renforcée et couple pas réduit avec davantage d'arbres, soit au plus 30 ajustements. H reste la référence avec ses sept entrées et ses cinq fenêtres. XGBoost sera exécuté et discuté avant tout calcul CatBoost. L'ancien plan interrompu sur D demeure historique et ne doit pas être relancé. Le test 505 à 743 reste réservé.

### Réglages XGBoost terminés, retour utilisateur attendu

Les [quinze validations XGBoost](ML_TUNE_H_XGBOOST.md), leurs [résultats agrégés](results/ml_tune_h_xgboost.json) et quatre figures sont publiés. `xgb_depth4` atteint un F1 moyen de **0,9000** contre **0,8948** pour H, avec un minimum de **0,8731** contre **0,8622**. Les cumuls passent de **3 388 TP et 203 FP** pour H à **3 418 TP et 194 FP**. Le F1 de `depth4` baisse toutefois dans deux fenêtres. `lambda10` atteint **0,8953** et `slow200` **0,8988** ; l'ajustement médian de `slow200` est plus long et sa taille sérialisée médiane plus grande. Avec la règle préannoncée, `depth4` est le candidat XGBoost provisoire, pas un modèle final. Les métriques d'apprentissage H n'avaient pas été enregistrées et H n'a pas été réentraînée pour les compléter.

L'empreinte du CSV, les quinze configurations et fenêtres, les colonnes, ratios manquants, historiques strictement antérieurs, matrices de confusion, moyennes, graines, versions, temps et tailles ont été vérifiés sur macOS Apple Silicon avec le Python 3.11 local. Les 35 tests passent. La commande générique `uv run --locked`, Linux et Windows restent non vérifiés pour ce passage. CatBoost n'a pas commencé ; aucun score du test 505 à 743 n'a été consulté.

### Réglages CatBoost terminés, sélection proposée à discuter

Les [quinze validations CatBoost](ML_TUNE_H_CATBOOST.md), la [comparaison des huit configurations](ML_TUNE_H_SELECTION.md), les [résultats structurés](results/ml_tune_h_selection.json) et les figures sont publiés. CatBoost profondeur 4 réduit le F1 moyen à **0,8810** et `l2_leaf_reg=10` à **0,8941**, face à **0,8976** pour H CatBoost. Le couple `learning_rate=0.05`, `iterations=200` atteint **0,9056** de F1 moyen et **0,8921** au minimum, avec **3 423 TP et 151 FP** cumulés. Face à H CatBoost, cela représente **38 TP de plus et 22 FP de moins**. Face au candidat XGBoost profondeur 4, cela représente **5 TP de plus et 43 FP de moins**, mais le F1 de CatBoost baisse dans les fenêtres 3 et 5.

La règle préannoncée propose `cat_slow200` car son F1 moyen dépasse XGBoost profondeur 4 de **0,0056**, au-delà de la marge de proximité de 0,005. Ce n'est pas un choix final : son ajustement médian est de **87,74 s** contre **3,01 s** pour XGBoost profondeur 4, et sa taille sérialisée médiane est de **0,255 Mio** contre **0,122 Mio**. Les trente nouveaux ajustements ont respecté les limites de 30 minutes et 75 % de RAM par processus. L'empreinte, les colonnes, paramètres, bornes, historiques, ratios, matrices de confusion, moyennes et la règle de sélection ont été revérifiés ; les 38 tests passent avec le Python 3.11 local sur macOS Apple Silicon. `uv run --locked`, Linux et Windows ne sont pas testés pour ce passage. Aucune nouvelle configuration ni score du test 505 à 743 ; discussion attendue avant toute suite.
