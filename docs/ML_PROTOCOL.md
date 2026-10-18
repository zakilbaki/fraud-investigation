# Lot 4.1 : protocole ML proposé pour PaySim

**Statut : lot 4.1 révisé avant implémentation, sans entraînement.** L'[EDA 4.0](EDA.md) est clôturée. Les cinq fenêtres ci-dessous remplacent le découpage unique antérieur. L'utilisateur retient **précision, rappel et F1** comme seules métriques prédictives principales, avec **F1 moyen** pour sélectionner le modèle. Un seuil est choisi par F1 maximal **dans chaque train**, avant la validation extérieure. Aucun score de modèle ni gain prédictif n'est annoncé. Le travail futur aura deux temps : comparer largement des familles de modèles, puis expliquer leurs écarts avec des diagnostics mesurés et quelques expériences contrôlées. Le budget supplémentaire est de 0 € et l'exécution visée est locale.

## 1. Question et frontière des données

Le futur modèle produira un **score de suspicion avant l'exécution** d'une transaction. `isFraud` est seulement la cible hors ligne ; `isFlaggedFraud` est seulement la règle PaySim de comparaison pendant l'évaluation. Les scénarios de démonstration restent hors des métriques PaySim. Le CSV audité porte le SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`.

L'EDA a déjà examiné **tout le fichier, données et labels du futur test inclus**. Le test n'est donc pas entièrement aveugle pour l'analyste. À partir de ce protocole, ses scores ne guideront ni choix de modèle, de variable, de paramètre, de transformation ou de seuil. On le consultera une seule fois après gel du pipeline et du seuil. Les labels resteront absents des outils d'enquête.

## 2. Validation temporelle à entraînement croissant

Les bornes sont inclusives. Un step représente une heure simulée ; toutes les lignes d'un même step restent ensemble, car leur ordre dans le fichier ne prouve aucun ordre chronologique. Dans chaque fenêtre, le train précède strictement la **validation extérieure**. Le train est lui-même séparé chronologiquement en **apprentissage** puis **choix du seuil**. Les trains des cinq fenêtres se recouvrent intentionnellement : chaque essai dispose de tout le passé alors connu. Les validations extérieures sont disjointes, mais les cinq résultats **ne sont pas indépendants**, car les trains se recouvrent et les périodes adjacentes proviennent du même simulateur.

| Fenêtre | Ensemble | Steps | Transactions | Normales | Fraudes | Taux de fraude |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Train | 1 à 144 | 1 509 597 | 1 507 965 | 1 632 | 0,1081 % |
| 1 | Validation | 145 à 216 | 1 288 139 | 1 287 334 | 805 | 0,0625 % |
| 2 | Train | 1 à 216 | 2 797 736 | 2 795 299 | 2 437 | 0,0871 % |
| 2 | Validation | 217 à 288 | 1 160 580 | 1 159 738 | 842 | 0,0725 % |
| 3 | Train | 1 à 288 | 3 958 316 | 3 955 037 | 3 279 | 0,0828 % |
| 3 | Validation | 289 à 360 | 1 227 741 | 1 227 003 | 738 | 0,0601 % |
| 4 | Train | 1 à 360 | 5 186 057 | 5 182 040 | 4 017 | 0,0775 % |
| 4 | Validation | 361 à 432 | 822 359 | 821 519 | 840 | 0,1021 % |
| 5 | Train | 1 à 432 | 6 008 416 | 6 003 559 | 4 857 | 0,0808 % |
| 5 | Validation extérieure | 433 à 504 | 55 620 | 54 856 | 764 | 1,3736 % |

Dans chaque train, les **72 derniers steps** servent uniquement à choisir le seuil par F1 maximal. Le modèle et ses prétraitements apprennent sur les steps antérieurs. Ce choix garde la même durée interne que la validation extérieure, sans choisir les bornes selon les labels ou les résultats. Le seuil est figé avant toute prédiction sur la validation extérieure.

| Fenêtre | Apprentissage du modèle et des prétraitements | Transactions | Normales | Fraudes | Réserve interne de seuil | Transactions | Normales | Fraudes |
| ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 1 à 72 | 1 030 563 | 1 029 673 | 890 | 73 à 144 | 479 034 | 478 292 | 742 |
| 2 | 1 à 144 | 1 509 597 | 1 507 965 | 1 632 | 145 à 216 | 1 288 139 | 1 287 334 | 805 |
| 3 | 1 à 216 | 2 797 736 | 2 795 299 | 2 437 | 217 à 288 | 1 160 580 | 1 159 738 | 842 |
| 4 | 1 à 288 | 3 958 316 | 3 955 037 | 3 279 | 289 à 360 | 1 227 741 | 1 227 003 | 738 |
| 5 | 1 à 360 | 5 186 057 | 5 182 040 | 4 017 | 361 à 432 | 822 359 | 821 519 | 840 |

Les **deux classes sont présentes dans les dix portions internes**. La réserve de seuil de la fenêtre 2 est la validation extérieure de la fenêtre 1, et ainsi de suite. Elle est disponible à cette date sans fuite depuis le futur, mais cela renforce la dépendance entre les cinq résultats. Chaque variante de pipeline aura son propre seuil choisi dans sa réserve interne ; aucun seuil ne sera optimisé sur la validation extérieure dont on publie le F1.

Les **deux classes sont présentes dans chaque ensemble**. Une validation de 72 steps couvre seulement trois jours simulés et peut manquer un motif plus long. Les volumes et prévalences changent fortement : la cinquième validation a peu de transactions et un taux de fraude bien supérieur aux précédentes. Nous ne chercherons pas à égaliser ces taux par stratification et ne supprimerons aucune ligne selon son label. Moyenne et dispersion des cinq mesures seront descriptives, sans intervalle de confiance prétendant à cinq expériences indépendantes.

Le **test final** est constitué des steps **505 à 743** : 239 steps, **298 584** transactions, **295 992** normales et **2 592** fraudes, soit **0,8681 %**. Il conserve les périodes atypiques. Les steps 721 à 743, par exemple, contiennent **272 fraudes sur 272 transactions**. Pris seuls, ils ne permettent pas de mesurer des faux positifs ni la séparation des classes ; leur précision et leur F1 isolés seraient trompeurs. Cette tranche ne sera ni retirée ni utilisée seule pour classer les modèles. Le test complet contient les deux classes.

## 3. Informations et prétraitements communs

**Premier passage : mêmes lignes, mêmes fenêtres et mêmes informations `type` et `amount` pour tous les candidats.** Le `DummyClassifier` reçoit ces colonnes mais les ignore par construction. Les représentations peuvent varier selon les algorithmes : encodage indicateur de `type` avec catégories inconnues ignorées, `amount` brut pour les arbres, `log1p(amount)` et standardisation pour les modèles sensibles à l'échelle, ou traitement natif de `type` par CatBoost. Les comparaisons portent donc sur des **pipelines complets** ; un écart ne sera pas automatiquement attribué au seul algorithme. Les représentations exactes et types numériques seront enregistrés.

Tout encodeur, standardiseur, imputation éventuelle ou autre transformation **apprise** sera ajusté sur la seule portion d'apprentissage de chaque fenêtre, puis appliqué sans réajustement à sa réserve de seuil et à sa validation extérieure. `log1p` est déterministe et accepte les montants nuls. Le premier passage n'emploiera ni pondération de classes, ni suréchantillonnage. Une pondération ou un échantillonnage ultérieurs seront des variantes identifiées, appliquées à la portion d'apprentissage seulement ; réserves de seuil, validations et test garderont leur distribution naturelle.

Une variante **séparée** pourra ajouter l'heure simulée `h = (step - 1) % 24` sous forme `sin(2πh/24)` et `cos(2πh/24)`, en conservant `type` et `amount`. Cette convention ne représente pas une heure civile confirmée. Un motif de l'EDA ne vaut pas gain en validation. **Aucune variable hebdomadaire** n'entre dans la première comparaison. Le `step` brut sert seulement à l'ordre temporel et au calcul de cette variante préannoncée, pas d'entrée brute.

Les soldes avant transaction et leurs dérivés sont écartés de la première comparaison à cause du risque de **signature artificielle du simulateur**, même si un solde initial peut être disponible avant exécution. Les soldes après transaction et leurs dérivés posent un problème différent : ils sont indisponibles au scoring avant exécution. `nameOrig`, `nameDest`, identifiants de transaction, numéro de ligne et empreinte source servent à la traçabilité, jamais comme prédicteurs. `isFraud` et `isFlaggedFraud` ne sont jamais des entrées.

## 4. Phase 1 : comparaison large, peu de réglages

Le tableau fixe **un point de départ par candidat**, à confirmer contre les versions installées avant le premier score, puis à consigner avec une graine `42`. `OHE` signifie indicatrices pour les catégories, apprises sur le train ; `LS` signifie `log1p(amount)` puis standardisation ajustée sur le train ; `R` signifie montant brut. Les nombres d'arbres et profondeurs sont des **budgets initiaux**, pas des optima présumés. Les temps et la mémoire ci-dessous sont des risques à mesurer, pas des mesures déjà obtenues.

| Candidat | Principe et question pédagogique | Prétraitement | Configuration initiale prévue | Calcul, mémoire et installation |
| --- | --- | --- | --- | --- |
| `DummyClassifier` | Prédit la fréquence du train ; donne le niveau sans signal utile. | Entrées reçues, ignorées. | `strategy="prior"`. | Très léger ; scikit-learn. |
| Régression logistique | Effet linéaire additif sur le score ; référence lisible. | OHE + LS. | `solver="lbfgs", C=1, max_iter=300`. | Matrice compacte mais plusieurs passages ; scikit-learn. |
| `SGDClassifier` logistique | Même famille linéaire, optimisation par petits pas ; compare coût et convergence. | OHE + LS. | `loss="log_loss", alpha=1e-4, max_iter=30, tol=1e-3, random_state=42`. | Léger en mémoire ; surveiller non-convergence ; scikit-learn. |
| `GaussianNB` | Règle de Bayes avec hypothèse gaussienne par variable ; montre l'effet d'une hypothèse simplificatrice. | OHE dense + LS. | `var_smoothing=1e-9`. | Léger, mais indicatrices peu gaussiennes et scores potentiellement extrêmes ; scikit-learn. |
| Arbre de décision | Règles de seuils et interactions explicites ; référence non linéaire simple. | OHE + R. | `max_depth=8, min_samples_leaf=100, random_state=42`. | Risque de surapprentissage, taille bornée ; scikit-learn. |
| Random Forest | Moyenne d'arbres entraînés sur tirages ; mesure l'intérêt de réduire l'instabilité de l'arbre. | OHE + R. | `n_estimators=100, max_depth=12, min_samples_leaf=100, n_jobs=4, random_state=42`. | Arbres multiples coûteux en RAM et temps ; scikit-learn. |
| Extra Trees | Arbres à seuils plus aléatoires ; compare une autre forme de diversité. | OHE + R. | `n_estimators=100, max_depth=12, min_samples_leaf=100, n_jobs=4, random_state=42`. | Coût mémoire proche d'une forêt ; scikit-learn. |
| `HistGradientBoostingClassifier` | Ajoute des arbres correctifs sur des tranches numériques ; référence boosting scikit-learn. | OHE dense + R. | `max_iter=100, max_leaf_nodes=31, min_samples_leaf=100, early_stopping=False, random_state=42`. | Binning et tableau dense ; scikit-learn. Pas de découpage interne aléatoire de validation. |
| LightGBM | Boosting par histogrammes ; compare son compromis vitesse, mémoire et forme des règles. | OHE + R. | `n_estimators=100, num_leaves=31, min_child_samples=100, learning_rate=0.1, n_jobs=4, random_state=42`. | Bibliothèque native à installer ; mémoire et fils d'exécution à mesurer. |
| XGBoost | Boosting régularisé par arbres ; compare une autre implémentation et ses réglages de croissance. | OHE + R. | `n_estimators=100, max_depth=6, min_child_weight=10, learning_rate=0.1, tree_method="hist", n_jobs=4, random_state=42`. | Bibliothèque native et matrice interne ; CPU seulement au départ. |
| CatBoost | Boosting avec traitement interne du type catégoriel ; teste ce pipeline complet. | `type` natif + R. | `iterations=100, depth=6, learning_rate=0.1, loss_function="Logloss", task_type="CPU", thread_count=4, random_seed=42, allow_writing_files=False`. | Bibliothèque native, encodage interne et coût RAM à mesurer ; aucun GPU requis. |

Les 11 candidats restent au programme de la phase 1 sous réserve d'un **contrôle de faisabilité**. Celui-ci commence par une installation locale compatible et un essai sur la première fenêtre **complète**, avec ses trois portions chronologiques et toutes leurs lignes, sans lecture du test. Pour protéger le Mac, entraînement et prédiction s'exécutent séquentiellement, avec quatre fils au maximum, un plafond provisoire de **30 minutes par ajustement** et un arrêt si le processus dépasse **75 % de la RAM physique**. Ces limites sont des budgets de prototype, pas des mesures de performance. Une erreur d'installation, de mémoire ou de temps sera consignée avec la version, l'étape et le coût observé ; le candidat sera marqué **non comparable sur cinq fenêtres**, sans être effacé de la liste. Un petit sous-ensemble peut servir à vérifier une API ou estimer la faisabilité, jamais à annoncer un résultat comparable aux cinq fenêtres complètes.

Trois modèles supplémentaires sont évalués pour leur intérêt pédagogique, avec la même exigence de faisabilité :

| Modèle | Intérêt et décision prévue |
| --- | --- |
| KNN (`k=25`, distance sur OHE + LS) | Montre une méthode locale et l'effet de l'échelle. L'entraînement stocke les millions de lignes et la prédiction cherche des voisins ; tester une requête chronométrée sur un sous-ensemble **sans métrique de performance**, puis l'inclure sur cinq fenêtres seulement si le coût projeté respecte le budget. |
| SVM à noyau RBF (`SVC`, `C=1`, `gamma="scale"`) | Teste une frontière non linéaire différente des arbres. La documentation scikit-learn indique un entraînement au moins quadratique avec le nombre de lignes ; un test de faisabilité limité peut illustrer le coût, mais aucun résultat sur sous-ensemble ne sera classé avec les résultats complets. Une inclusion complète exige une mesure montrant qu'elle respecte le même budget. |
| Petit réseau `MLPClassifier` (`hidden_layer_sizes=(16,), max_iter=30`, graine 42) | Teste une interaction apprise sans architecture profonde. OHE + LS ; mesurer convergence, coût et stabilité sur première fenêtre complète, puis inclure dans les cinq si faisable. Pas de GPU ni de bibliothèque profonde supplémentaire prévue. |

Les paramètres d'essai de ces trois modèles seront figés avant leurs mesures. Le coût d'une méthode peut justifier son exclusion du **classement complet**, sans préjuger sa qualité prédictive. Les [notes sur les voisins](https://scikit-learn.org/stable/modules/neighbors.html), le [coût de `SVC`](https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVC.html), les [histogrammes scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html), et les API [LightGBM](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMClassifier.html), [XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html) et [CatBoost](https://catboost.ai/docs/en/references/training-parameters/) motivent ces contrôles de compatibilité et coût ; aucun temps ni gain PaySim n'en est déduit.

## 5. Phase 2 : approfondissement borné

Après la phase 1, retenir **au plus trois candidats complets** classés par F1 moyen sur les validations extérieures, avec les départages de la section 7 si nécessaire ; conserver en plus la régression logistique comme référence explicative si elle n'est pas parmi eux. Pour chacun de ces **au plus quatre** candidats, tester **au plus deux configurations supplémentaires** sur les cinq fenêtres, soit **au plus huit configurations et quarante ajustements supplémentaires**. Une configuration est définie avant son premier score de validation ; aucune recherche automatique illimitée, aucun changement décidé en lisant le test et aucun essai supplémentaire après le budget.

Les expériences prioritaires sont : (1) `amount` brut contre `log1p(amount)` pour un candidat sensible à l'échelle, en conservant le même type d'encodage et les mêmes lignes ; (2) interaction explicite `type × log1p(amount)` pour un modèle linéaire, contre le modèle additif ; (3) profondeur ou nombre de feuilles différent pour un modèle d'arbres, à budget égal d'itérations, pour examiner les relations non linéaires. Si la variante horaire `sin/cos` est testée, elle occupe **une des deux places** du candidat, sans ajouter une fenêtre ou une variable hebdomadaire. Pondération de classe ou échantillonnage, s'ils sont finalement testés, occupent eux aussi une place identifiée ; leur application est limitée au train. Les choix exacts de deux variantes par candidat et leurs paramètres seront consignés **avant** de regarder leurs scores.

Cette seconde phase utilise les mêmes validations et peut leur adapter le choix : elle reste exploratoire. Les résultats par fenêtre, les variantes abandonnées, les dépassements de budget et les différences de pipeline resteront visibles. Un résultat sur sous-ensemble n'entrera ni dans la moyenne ni dans la sélection.

## 6. Métriques et plan d'explication

Les **trois métriques prédictives principales** sont calculées sur chaque validation extérieure, avec le seuil déjà choisi dans la réserve interne correspondante : `précision = TP/(TP+FP)`, `rappel = TP/(TP+FN)` et `F1 = 2TP/(2TP+FP+FN)`. `TP` est une fraude alertée, `FP` une normale alertée et `FN` une fraude non alertée. Publier pour **chaque modèle et chaque fenêtre** les trois valeurs, puis leur **moyenne arithmétique non pondérée sur les cinq fenêtres**. Publier aussi le nombre de transactions, de fraudes, la prévalence et le seuil interne qui a produit les alertes. Aucun seuil ne sera ajusté sur les labels de la validation extérieure. Aucune Average Precision ni aire de courbe ne sert à classer les modèles.

La convention de compte rendu pour une validation sans alerte est : précision **0 pour le tableau et sa moyenne**, rappel 0 et F1 0, avec `alertes = 0` explicitement indiqué. Mathématiquement, `TP/(TP+FP)` y est non défini ; utiliser 0 comme convention de comparaison évite de retirer une fenêtre défavorable de la moyenne. Les cinq validations contiennent des fraudes, donc leurs rappels sont définis. Rapporter aussi `alertes = TP+FP`, `FP` et `FN` en effectifs, afin de rendre chaque résultat concret. Les moyennes des métriques ne remplacent pas ces cinq lignes : elles ne sont **pas** les métriques d'une confusion matrix fusionnant les validations, dont les volumes diffèrent.

Le futur benchmark devra expliquer les écarts, pas seulement classer les F1 :

| Diagnostic sur apprentissages, réserves de seuil et validations extérieures | Question testée et précaution |
| --- | --- |
| Précision, rappel et F1 par fenêtre, avec prévalence et seuil interne | Une amélioration est-elle régulière ou portée par une seule période ? Les entraînements et réserves successifs se recouvrent. |
| Résultats par `type` et tranches de montant fixées depuis l'EDA | Où apparaissent TP, FP et FN ? Toujours afficher les dénominateurs ; une tranche à une seule classe ne permet pas toutes les lectures. |
| Effectifs, montants et distributions de scores | Un changement de mélange, de montant ou de score accompagne-t-il l'écart ? Graphiques et quantiles descriptifs, zéro isolé. |
| Métriques sur la portion d'apprentissage et sur la validation extérieure, au seuil interne | Y a-t-il un écart compatible avec surapprentissage ? Les prévalences différentes et le seuil choisi sur la réserve interne limitent la lecture brute. |
| Temps d'ajustement, de choix du seuil et de prédiction, mémoire maximale, taille sérialisée | Le gain descriptif justifie-t-il le coût local mesuré ? Mesurer les mêmes étapes et le même matériel. |
| Contrôles ciblés brut/log, additif/interaction, profondeur limitée/élargie | Une hypothèse sur la non-linéarité ou `type × amount` tient-elle quand seule cette composante change ? Même fenêtre, mêmes lignes, même règle interne de seuil. |

`type` est catégoriel : une corrélation de Pearson sur des codes arbitraires 0, 1, 2, etc. n'explique rien. Employer plutôt des tableaux et taux par type avec effectifs, ou une comparaison contrôlée avec indicatrices ; pour `amount`, examiner formes, quantiles et relations par tranches. Une importance de variable ou une valeur SHAP ultérieure ne prouve pas une causalité. Chaque conclusion sera étiquetée **hypothèse**, **observation mesurée** ou **explication soutenue par une expérience contrôlée**. Les diagnostics servant aux choix utilisent seulement les données avant le test. Après gel, des diagnostics descriptifs sur le test peuvent expliquer l'évaluation finale, jamais relancer la sélection.

La précision, et donc souvent F1, peut changer avec la prévalence. Même avec rappel et taux de faux positifs constants, `précision = rappel × prévalence / (rappel × prévalence + taux_FP × (1 − prévalence))`. Toujours afficher les taux de fraude avant de comparer des périodes. Un score ne sera pas nommé **probabilité fiable** sans étude de calibration. `isFlaggedFraud` sera rapporté séparément comme règle binaire, avec précision, rappel, F1, alertes, FP et FN, sans participer à la sélection du pipeline.

## 7. Choix interne du seuil, sélection et test final

**Seuil dans chaque fenêtre.** Pour chaque pipeline candidat, ajuster modèle et prétraitements sur la portion d'apprentissage de la section 2. Produire ensuite ses scores sur la réserve interne de 72 steps. Examiner les seuils correspondant aux **scores distincts** et le cas zéro alerte ; maximiser `F1 = 2TP/(2TP+FP+FN)` sur les labels de cette réserve seulement. En cas de F1 égal, choisir le **seuil numérique le plus haut**, donc le plus petit volume d'alertes. Une transaction est alertée si `score ≥ seuil` ; les scores identiques restent groupés et l'ordre des lignes ne les départage jamais. Le seuil au-dessus du score maximal représente zéro alerte et F1 = 0 quand des fraudes existent. Si tous les scores sont identiques, seuls « tout alerter » et « ne rien alerter » sont possibles. Les cinq réserves contiennent les deux classes. Figer le seuil avant de calculer précision, rappel et F1 sur la validation extérieure.

**Sélection préannoncée.** Seuls les pipelines ayant terminé les cinq fenêtres complètes avec prétraitements et seuils internes sans fuite entrent au classement. Le **F1 moyen non arrondi** des cinq validations extérieures est le critère principal. Soit `M` le meilleur F1 moyen. Des candidats dont la moyenne est à moins de **0,005 F1 absolu** de `M` sont considérés proches ; ce voisinage pratique n'est pas un test de significativité. Parmi eux, choisir le plus fort **minimum de F1** sur les cinq fenêtres. Si les minima diffèrent de moins de 0,005, choisir le plus faible écart-type descriptif (`ddof=1`) des cinq F1. Si les écarts-types diffèrent de moins de 0,005, choisir le temps médian d'ajustement le plus court ; si les temps diffèrent de moins de 20 %, choisir le modèle sérialisé le plus petit ; si les tailles diffèrent de moins de 20 %, choisir le pipeline le plus simple selon l'ordre fixé : Dummy, GaussianNB, régression logistique, SGD, arbre, HistGradientBoosting, Extra Trees, Random Forest, LightGBM, XGBoost, CatBoost, MLP, KNN, SVM à noyau. Les trois derniers n'entrent dans cet ordre que s'ils ont passé les cinq fenêtres. Un dernier cas exactement indiscernable est départagé par le nom du candidat. Le minimum et la dispersion décrivent la régularité observée, sans faire des cinq fenêtres des expériences indépendantes. Publier aussi les cinq précisions et rappels, avec leurs moyennes, même s'ils ne servent pas au premier rang.

**Déroulement final sans réutiliser une validation extérieure pour son propre seuil :**

1. Comparer les candidats de phase 1 avec leurs seuils internes, puis exécuter au plus le budget de phase 2. Choisir et figer configuration et paramètres d'après les cinq validations extérieures, sans consulter le test.
2. Conserver, pour le pipeline retenu, son ajustement de la **fenêtre 5 sur 1 à 360** et son seuil choisi sur **361 à 432**. Si nécessaire, reconstruire exactement cet ajustement avec les mêmes données, versions et graine, sans apprendre de 433 à 504.
3. Garder **433 à 504 uniquement comme validation extérieure** de comparaison. Son F1 publié provient du seuil fixé sur 361 à 432. Aucun nouveau seuil ni réentraînement n'y est choisi pour annoncer une métrique sur cette même période.
4. Figer le pipeline et le seuil, puis les appliquer **une fois** au test complet **505 à 743**. Rapporter précision, rappel, F1, prévalence, alertes, FP et FN, avec les limites de la période 721 à 743.

Le modèle final apprend donc moins de lignes qu'un réentraînement sur 1 à 432 ou 1 à 504. C'est le coût assumé pour conserver une réserve interne de seuil et une validation extérieure qui sert seulement à l'évaluation. Un réentraînement sur une plage plus longue modifierait potentiellement les scores et exigerait un **nouveau** protocole de seuil ; il n'est pas prévu ici. La fenêtre 5 a déjà participé au choix du pipeline, donc son résultat ne constitue pas une estimation indépendante. L'exposition des labels du test pendant l'EDA reste déclarée, mais les scores du test ne serviront à aucun choix.

## 8. Reproductibilité et vérifications de ce lot

Les effectifs ont été **recalculés**, sans modèle, sur le CSV local audité avec Polars et Python 3.11. Les 743 steps et les totaux **6 362 620 transactions / 8 213 fraudes** ont été retrouvés ; chaque portion d'apprentissage, chaque réserve interne et chaque validation extérieure compte ses deux classes. Leurs bornes sont strictement ordonnées dans une fenêtre ; le test commence après toutes les validations. Les sommes des deux portions internes retrouvent les trains du premier tableau. Le taux de la validation 217 à 288 reste **0,0725 %** après recalcul. Ces effectifs sont des données descriptives, **pas des performances ML**.

La réexécution de l'EDA 4.0 avait réussi avec le **Python local**. La commande générique `uv run --locked` n'avait **pas** été validée dans l'environnement restreint à cause du cache et d'une tentative d'accès réseau. Linux et Windows n'ont pas été testés. Ce lot n'ajoute ni dépendance ML, ni entraînement, ni score, ni seuil. À l'implémentation, figer les versions installées, la graine, les types et noms de colonnes, les bornes, les configurations, les temps et tailles mesurés. Le pipeline final sera enregistré avec `joblib`, accompagné de la source, de ses limites et du seuil. SHAP ne viendra qu'après validation du parcours de prédiction, comme outil d'explication de scores, pas de causalité.

**Décision de seuil révisée :** maximiser F1 dans la réserve interne de chaque train, avec départage par le seuil le plus haut. Le F1 moyen des validations extérieures sélectionnera le pipeline. Les choix de variantes en phase 2 suivront le budget et les règles ci-dessus, sans consulter le test. L'implémentation et l'entraînement relèvent d'un travail ultérieur.
