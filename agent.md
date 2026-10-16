# Consignes des agents de développement

Ces consignes concernent les assistants qui construisent le prototype Fraud Investigation. Lire ce document avant chaque lot, avec docs/PROJECT.md et les fichiers pertinents pour la mission.

## Versionnement continu

- Après chaque changement de code cohérent, terminé et vérifié, créer un commit avec un message explicite et le pousser sur le dépôt GitHub existant : https://github.com/zakilbaki/fraud-investigation.
- Ne pas attendre la fin du lot pour publier les changements validés.
- Inclure les tests et la documentation associés lorsqu'ils sont nécessaires. Versionner aussi les changements de documentation autonomes et utiles.
- Avant chaque commit, exécuter les vérifications adaptées au changement et examiner précisément les fichiers et différences préparés.
- Si une vérification échoue, corriger le problème avant de publier. Si la correction est bloquée, expliquer le blocage sans annoncer un succès.
- Ne jamais inclure de données PaySim, archives, bases SQLite ou fichiers auxiliaires, fichiers de labels, environnements Python ou secrets. Respecter les exclusions Git existantes.
- Préserver l'historique, ne pas créer de commit vide et ne pas utiliser de push forcé.
- Après chaque push, vérifier que le commit est présent sur GitHub et que la branche locale est synchronisée. Signaler explicitement un push bloqué ou échoué.
- Fournir dans le bilan les identifiants et liens des commits publiés, avec les vérifications réellement exécutées et les limites restantes.

## Explication des choix techniques et participation

Le projet sert à apprendre et à préparer des entretiens. Construire une fonctionnalité ne suffit pas : l'utilisateur doit comprendre les décisions prises.

- Expliquer chaque choix technique important avant sa mise en œuvre ou au moment de le réaliser, dans les échanges, sans attendre le bilan final. Ne pas laisser cette explication uniquement dans le code ou les fichiers de documentation.
- Pour chaque choix, préciser en langage simple : le problème à résoudre, la solution retenue, pourquoi elle convient au prototype, une alternative pertinente, les avantages, les limites et la manière de vérifier le résultat. Définir les termes nouveaux et utiliser un petit exemple concret lorsque cela aide.
- Couvrir aussi les décisions moins visibles : index et clés SQL, types de stockage, import par lots, identifiants et provenance, séparation des labels, variables ML, découpage temporel, métriques, seuils et limites des outils des agents. Adapter les explications aux décisions effectivement prises dans le lot.
- Distinguer ce qui est prévu, ce qui est implémenté et ce qui est réellement vérifié. Ne pas annoncer de gain de vitesse, de mémoire ou de qualité sans mesure. Par exemple, pour un index, expliquer la recherche visée, les colonnes indexées, son coût et vérifier son utilisation avec le plan de requête lorsque pertinent.
- Conserver une trace courte des décisions et de leur justification dans le document concerné, par exemple docs/DATABASE.md ou le document du protocole ML. Dans le bilan de chaque lot, inclure les choix techniques expliqués, les vérifications et une formulation simple que l'utilisateur peut reprendre dans ses notes ou en entretien.
- Pour l'analyse exploratoire, afficher les graphiques produits dans la conversation, expliquer leur lecture et faire participer l'utilisateur à leur interprétation. Procéder par petites étapes et attendre son retour aux points de discussion prévus.
- Les explications ne doivent pas transformer chaque détail courant en demande d'autorisation. Respecter le lot confié et les moments de validation convenus avec l'utilisateur.

## Périmètre du travail

Cette règle Git autorise la sauvegarde et la publication des changements relevant du lot confié. Elle n'autorise pas à commencer un nouveau lot ou à élargir la mission sans instruction de l'utilisateur.

Préserver la reproductibilité : aucun chemin personnel ni dépendance implicite à la machine du développeur. Documenter les prérequis, les paramètres nécessaires et les plateformes réellement vérifiées.

Le fichier AGENTS.md à la racine est généré par l'environnement. Le présent fichier agent.md conserve les consignes propres au projet dans Git ; il doit être lu explicitement, sans supposer un chargement automatique par tous les outils.
