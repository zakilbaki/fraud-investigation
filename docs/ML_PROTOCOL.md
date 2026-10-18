# Lot 4.1 : protocole ML proposé pour PaySim

**Statut : protocole avant implémentation, sans entraînement.** L'[EDA 4.0](EDA.md) est clôturée. Les cinq fenêtres ci-dessous remplacent le découpage unique antérieur. Le choix du critère de seuil reste à faire par l'utilisateur **avant l'implémentation**. Aucun score de modèle ni gain prédictif n'est annoncé. Le travail futur aura deux temps : comparer largement des familles de modèles, puis expliquer leurs écarts avec des diagnostics mesurés et quelques expériences contrôlées. Le budget supplémentaire est de 0 € et l'exécution visée est locale.

## 1. Question et frontière des données

Le futur modèle produira un **score de suspicion avant l'exécution** d'une transaction. `isFraud` est seulement la cible hors ligne ; `isFlaggedFraud` est seulement la règle PaySim de comparaison pendant l'évaluation. Les scénarios de démonstration restent hors des métriques PaySim. Le CSV audité porte le SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`.

L'EDA a déjà examiné **tout le fichier, données et labels du futur test inclus**. Le test n'est donc pas entièrement aveugle pour l'analyste. À partir de ce protocole, ses scores ne guideront ni choix de modèle, de variable, de paramètre, de transformation ou de seuil. On le consultera une seule fois après gel du pipeline et du seuil. Les labels resteront absents des outils d'enquête.

## 2. Validation temporelle à entraînement croissant

Les bornes sont inclusives. Un step représente une heure simulée ; toutes les lignes d'un même step restent ensemble, car leur ordre dans le fichier ne prouve aucun ordre chronologique. Dans chaque fenêtre, le train précède strictement la validation. Les trains se recouvrent intentionnellement : chaque essai apprend de tout le passé disponible à sa date. Les validations sont disjointes, mais les cinq résultats **ne sont pas indépendants**, car les trains se recouvrent et les périodes adjacentes proviennent du même simulateur.

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
| 5 | Validation et seuil | 433 à 504 | 55 620 | 54 856 | 764 | 1,3736 % |

Les **deux classes sont présentes dans chaque ensemble**. Une validation de 72 steps couvre seulement trois jours simulés et peut manquer un motif plus long. Les volumes et prévalences changent fortement : la cinquième validation a peu de transactions et un taux de fraude bien supérieur aux précédentes. Nous ne chercherons pas à égaliser ces taux par stratification et ne supprimerons aucune ligne selon son label. Moyenne et dispersion des cinq mesures seront descriptives, sans intervalle de confiance prétendant à cinq expériences indépendantes.

Le **test final** est constitué des steps **505 à 743** : 239 steps, **298 584** transactions, **295 992** normales et **2 592** fraudes, soit **0,8681 %**. Il conserve les périodes atypiques. Les steps 721 à 743, par exemple, contiennent **272 fraudes sur 272 transactions**. Pris seuls, ils ne permettent pas de mesurer des faux positifs ni la séparation des classes ; une Average Precision isolée y serait peu informative. Cette tranche ne sera ni retirée ni utilisée seule pour classer les modèles. Le test complet contient les deux classes.

## 3. Informations et prétraitements communs

**Premier passage : mêmes lignes, mêmes fenêtres et mêmes informations `type` et `amount` pour tous les candidats.** Le `DummyClassifier` reçoit ces colonnes mais les ignore par construction. Les représentations peuvent varier selon les algorithmes : encodage indicateur de `type` avec catégories inconnues ignorées, `amount` brut pour les arbres, `log1p(amount)` et standardisation pour les modèles sensibles à l'échelle, ou traitement natif de `type` par CatBoost. Les comparaisons portent donc sur des **pipelines complets** ; un écart ne sera pas automatiquement attribué au seul algorithme. Les représentations exactes et types numériques seront enregistrés.

Tout encodeur, standardiseur, imputation éventuelle ou autre transformation **apprise** sera ajusté sur le train de chaque fenêtre, puis appliqué sans réajustement à sa validation. `log1p` est déterministe et accepte les montants nuls. Le premier passage n'emploiera ni pondération de classes, ni suréchantillonnage. Une pondération ou un échantillonnage ultérieurs seront des variantes identifiées, appliquées au train seulement ; validations et test garderont leur distribution naturelle.

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

Les 11 candidats restent au programme de la phase 1 sous réserve d'un **contrôle de faisabilité**. Celui-ci commence par une installation locale compatible et un essai sur la première fenêtre **complète**, avec toutes ses lignes, sans lecture du test. Pour protéger le Mac, entraînement et prédiction s'exécutent séquentiellement, avec quatre fils au maximum, un plafond provisoire de **30 minutes par ajustement** et un arrêt si le processus dépasse **75 % de la RAM physique**. Ces limites sont des budgets de prototype, pas des mesures de performance. Une erreur d'installation, de mémoire ou de temps sera consignée avec la version, l'étape et le coût observé ; le candidat sera marqué **non comparable sur cinq fenêtres**, sans être effacé de la liste. Un petit sous-ensemble peut servir à vérifier une API ou estimer la faisabilité, jamais à annoncer un résultat comparable aux cinq fenêtres complètes.

Trois modèles supplémentaires sont évalués pour leur intérêt pédagogique, avec la même exigence de faisabilité :

| Modèle | Intérêt et décision prévue |
| --- | --- |
| KNN (`k=25`, distance sur OHE + LS) | Montre une méthode locale et l'effet de l'échelle. L'entraînement stocke les millions de lignes et la prédiction cherche des voisins ; tester une requête chronométrée sur un sous-ensemble **sans métrique de performance**, puis l'inclure sur cinq fenêtres seulement si le coût projeté respecte le budget. |
| SVM à noyau RBF (`SVC`, `C=1`, `gamma="scale"`) | Teste une frontière non linéaire différente des arbres. La documentation scikit-learn indique un entraînement au moins quadratique avec le nombre de lignes ; un test de faisabilité limité peut illustrer le coût, mais aucun résultat sur sous-ensemble ne sera classé avec les résultats complets. Une inclusion complète exige une mesure montrant qu'elle respecte le même budget. |
| Petit réseau `MLPClassifier` (`hidden_layer_sizes=(16,), max_iter=30`, graine 42) | Teste une interaction apprise sans architecture profonde. OHE + LS ; mesurer convergence, coût et stabilité sur première fenêtre complète, puis inclure dans les cinq si faisable. Pas de GPU ni de bibliothèque profonde supplémentaire prévue. |

Les paramètres d'essai de ces trois modèles seront figés avant leurs mesures. Le coût d'une méthode peut justifier son exclusion du **classement complet**, sans préjuger sa qualité prédictive. Les [notes sur les voisins](https://scikit-learn.org/stable/modules/neighbors.html), le [coût de `SVC`](https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVC.html), les [histogrammes scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html), et les API [LightGBM](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMClassifier.html), [XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html) et [CatBoost](https://catboost.ai/docs/en/references/training-parameters/) motivent ces contrôles de compatibilité et coût ; aucun temps ni gain PaySim n'en est déduit.

## 5. Phase 2 : approfondissement borné

Après la phase 1, retenir **au plus trois candidats complets** classés par moyenne d'AP, avec les départages de la section 7 si nécessaire ; conserver en plus la régression logistique comme référence explicative si elle n'est pas parmi eux. Pour chacun de ces **au plus quatre** candidats, tester **au plus deux configurations supplémentaires** sur les cinq fenêtres, soit **au plus huit configurations et quarante ajustements supplémentaires**. Une configuration est définie avant son premier score de validation ; aucune recherche automatique illimitée, aucun changement décidé en lisant le test et aucun essai supplémentaire après le budget.

Les expériences prioritaires sont : (1) `amount` brut contre `log1p(amount)` pour un candidat sensible à l'échelle, en conservant le même type d'encodage et les mêmes lignes ; (2) interaction explicite `type × log1p(amount)` pour un modèle linéaire, contre le modèle additif ; (3) profondeur ou nombre de feuilles différent pour un modèle d'arbres, à budget égal d'itérations, pour examiner les relations non linéaires. Si la variante horaire `sin/cos` est testée, elle occupe **une des deux places** du candidat, sans ajouter une fenêtre ou une variable hebdomadaire. Pondération de classe ou échantillonnage, s'ils sont finalement testés, occupent eux aussi une place identifiée ; leur application est limitée au train. Les choix exacts de deux variantes par candidat et leurs paramètres seront consignés **avant** de regarder leurs scores.

Cette seconde phase utilise les mêmes validations et peut leur adapter le choix : elle reste exploratoire. Les résultats par fenêtre, les variantes abandonnées, les dépassements de budget et les différences de pipeline resteront visibles. Un résultat sur sous-ensemble n'entrera ni dans la moyenne ni dans la sélection.

## 6. Mesures et plan d'explication

La mesure principale est l'**Average Precision (AP)** de la classe fraude, à partir des scores continus et sans seuil. C'est la somme `Σ (rappel_i − rappel_(i−1)) × précision_i` sur les niveaux de score distincts, **pas** l'aire trapézoïdale interpolée sous la courbe précision-rappel. Pour chaque pipeline et chaque validation, publier AP, transactions, fraudes et taux de fraude. Publier aussi la moyenne arithmétique non pondérée des cinq AP, leur écart-type descriptif (`ddof=1`) et leur minimum. Ces cinq nombres ne justifient pas une inférence statistique forte.

Pour comparer les charges d'alerte **avant le choix du seuil final**, rapporter sur chaque validation deux points de diagnostic : les niveaux de score qui alertent environ **0,1 %** et **1 %** des lignes, sans consulter les labels pour fixer ces volumes. À chaque point, publier le seuil numérique, précision `TP/(TP+FP)`, rappel `TP/(TP+FN)`, alertes `TP+FP`, faux positifs `FP` et faux négatifs `FN`, ainsi que les effectifs réels. Tous les scores égaux à la frontière sont alertés ensemble : le volume réel peut dépasser la fraction visée. Ces points sont des diagnostics comparables, **pas** des capacités métier ni le seuil final.

Le futur benchmark devra expliquer les écarts, pas seulement classer les AP :

| Diagnostic sur train et validation seulement | Question testée et précaution |
| --- | --- |
| Résultats par fenêtre et prévalence | Une amélioration est-elle régulière ou portée par une seule période ? Les trains se recouvrent. |
| Résultats par `type` et tranches de montant fixées depuis l'EDA | Où apparaissent TP, FP et FN ? Toujours afficher dénominateurs ; une tranche à une classe ne permet pas toutes les métriques. |
| Effectifs, montants et scores | Un changement de mélange, de montant ou de score accompagne-t-il un écart d'AP ? Graphiques et quantiles descriptifs, zéro isolé. |
| AP du train et de la validation, avec prévalences | Y a-t-il un écart compatible avec surapprentissage ? Les prévalences différentes limitent la lecture d'une différence brute. |
| Temps d'ajustement, temps de score, mémoire maximale, taille sérialisée | Le gain descriptif justifie-t-il le coût local mesuré ? Mesurer les mêmes étapes et le même matériel. |
| Contrôles ciblés brut/log, additif/interaction, profondeur limitée/élargie | Une hypothèse sur la non-linéarité ou `type × amount` tient-elle quand seule cette composante change ? Même fenêtre, mêmes lignes, même budget d'essais. |

`type` est catégoriel : une corrélation de Pearson sur des codes arbitraires 0, 1, 2, etc. n'explique rien. Employer plutôt des tableaux et taux par type avec effectifs, ou une comparaison contrôlée avec indicatrices ; pour `amount`, examiner formes, quantiles et relations par tranches. Une importance de variable, une valeur SHAP ultérieure ou une différence d'AP ne prouvent pas une causalité. Chaque conclusion sera étiquetée **hypothèse**, **observation mesurée** ou **explication soutenue par une expérience contrôlée**. Les diagnostics servant aux choix utilisent train et validations uniquement. Après gel, des diagnostics descriptifs sur le test peuvent expliquer l'évaluation finale, jamais relancer une sélection.

La précision et l'AP changent souvent avec la prévalence. Même avec rappel et taux de faux positifs constants, `précision = rappel × prévalence / (rappel × prévalence + taux_FP × (1 − prévalence))`. L'AP a une référence aléatoire proche de la prévalence et dépend du mélange de positifs et négatifs dans le classement. Toujours afficher ces taux avant de comparer des périodes. Un score ne sera pas nommé **probabilité fiable** sans étude de calibration. `isFlaggedFraud` sera rapporté séparément comme règle binaire, avec alertes, précision, rappel, FP et FN ; elle ne produit pas une courbe de classement comparable à l'AP des scores continus.

## 7. Sélection, seuil et test final

**Sélection préannoncée.** Seuls les pipelines ayant terminé les cinq fenêtres complètes et leurs prétraitements sans fuite entrent au classement. La moyenne d'AP non arrondie est la mesure principale. Le meilleur niveau `M` est le maximum de ces moyennes. Sont dits **proches** les candidats dont la moyenne est à moins de **0,005 AP absolue** de `M` ; ce voisinage est un choix pratique de démonstration, pas un test de significativité. Parmi eux, choisir le plus fort **minimum d'AP** sur les cinq fenêtres ; si les minima diffèrent de moins de 0,005, choisir le plus faible écart-type. Si les écarts-types diffèrent de moins de 0,005, choisir le temps médian d'ajustement le plus court ; si les temps diffèrent de moins de 20 %, choisir le modèle sérialisé le plus petit ; si les tailles diffèrent de moins de 20 %, choisir le pipeline le plus simple selon l'ordre fixé : Dummy, GaussianNB, régression logistique, SGD, arbre, HistGradientBoosting, Extra Trees, Random Forest, LightGBM, XGBoost, CatBoost, MLP, KNN, SVM à noyau. Les trois derniers n'entrent dans cet ordre que s'ils ont passé les cinq fenêtres. Un dernier cas exactement indiscernable est départagé par le nom du candidat. Le minimum et la dispersion décrivent la stabilité observée, sans faire des fenêtres des expériences indépendantes. Toutes les AP par fenêtre resteront publiées, y compris pour les candidats non retenus.

Le déroulement final est le suivant :

1. Comparer les candidats de phase 1 sur les cinq fenêtres, puis exécuter au plus le budget de phase 2. Choisir et figer configuration, prétraitements et paramètres sans score du test.
2. Ajuster à neuf le pipeline retenu sur les steps **1 à 432** seulement, avec transformations apprises sur ces steps. Mesurer ses scores sur **433 à 504**.
3. Choisir **un seuil** sur 433 à 504 selon **un seul** des critères ci-dessous, à sélectionner par l'utilisateur avant l'implémentation. Figer modèle, seuil, versions et règle de décision.
4. Évaluer **une fois** sur le test complet 505 à 743. Rapporter AP, prévalence, précision, rappel, alertes, FP et FN au seuil, avec les limites de la période 721 à 743.

La cinquième validation sert à la fois à sélectionner la configuration et à choisir le seuil : **ce n'est pas une validation imbriquée** et le seuil peut être optimiste. Ne pas réentraîner sur 1 à 504 avec ce même seuil sans un autre protocole : les scores changeraient potentiellement.

| Critère à choisir avant implémentation | Règle sur 433 à 504 | Conséquence |
| --- | --- | --- |
| **Statistique : F1 maximal** | Maximiser `F1 = 2TP/(2TP+FP+FN)` sur les seuils correspondant aux scores distincts ; en cas d'égalité, choisir le **seuil le plus haut**, donc le plus petit nombre d'alertes. | Compromis mathématique entre précision et rappel, sans garantie sur la charge. La prévalence de cette validation influence le seuil. |
| **Plafond d'alertes de démonstration** | Fixer avant les résultats un entier `C ≥ 0` d'alertes sur les 72 steps ; parmi les seuils donnant `alertes ≤ C`, maximiser le rappel, puis choisir le seuil le plus haut. | Rend une charge de démonstration explicite, sans prétendre à une capacité métier. Le même seuil sur 239 steps de test ne garantit pas `C` alertes. |

Une transaction est alertée si **score ≥ seuil**. Les transactions ayant le même score restent ensemble ; l'ordre des lignes ne les départage jamais. Ajouter un seuil au-dessus du score maximal pour représenter **zéro alerte**. Si tous les scores sont identiques, seuls « tout alerter » et « ne rien alerter » sont possibles. Pour F1, zéro alerte donne F1 = 0 quand des fraudes existent ; le maximum reste défini. Pour un plafond `C` inférieur à la taille du groupe de scores le plus haut, aucune alerte positive n'est admissible : retenir zéro alerte, déclarer le rappel nul et signaler que le critère ne peut produire d'alerte avec ces scores. Ne pas assouplir silencieusement `C`. Une précision sans alerte est **non définie**, pas zéro ; tout autre taux à dénominateur nul est non défini.

## 8. Reproductibilité et vérifications de ce lot

Les effectifs ont été **recalculés**, sans modèle, sur le CSV local audité avec Polars et Python 3.11. Les 743 steps et les totaux **6 362 620 transactions / 8 213 fraudes** ont été retrouvés ; chaque train et validation compte ses deux classes ; leurs bornes ne se recouvrent pas dans une fenêtre et le test commence après toutes les validations. Le taux de la validation 217 à 288 a été corrigé à **0,0725 %** après recalcul. Ces effectifs sont des données descriptives, **pas des performances ML**.

La réexécution de l'EDA 4.0 avait réussi avec le **Python local**. La commande générique `uv run --locked` n'avait **pas** été validée dans l'environnement restreint à cause du cache et d'une tentative d'accès réseau. Linux et Windows n'ont pas été testés. Ce lot n'ajoute ni dépendance ML, ni entraînement, ni score, ni seuil. À l'implémentation, figer les versions installées, la graine, les types et noms de colonnes, les bornes, les configurations, les temps et tailles mesurés. Le pipeline final sera enregistré avec `joblib`, accompagné de la source, de ses limites et du seuil. SHAP ne viendra qu'après validation du parcours de prédiction, comme outil d'explication de scores, pas de causalité.

**Décision restante avant l'implémentation :** choisir entre F1 maximal et plafond d'alertes de démonstration ; dans le second cas, fixer aussi `C` avant tout résultat de modèle. Les choix de phase 2 suivront le budget et les règles ci-dessus. Le lot s'arrête ici.
