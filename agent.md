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

## Périmètre du travail

Cette règle Git autorise la sauvegarde et la publication des changements relevant du lot confié. Elle n'autorise pas à commencer un nouveau lot ou à élargir la mission sans instruction de l'utilisateur.

Le fichier AGENTS.md à la racine est généré par l'environnement. Le présent fichier agent.md conserve les consignes propres au projet dans Git ; il doit être lu explicitement, sans supposer un chargement automatique par tous les outils.
