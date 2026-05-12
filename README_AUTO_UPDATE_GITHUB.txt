RL Overlay Studio - Mise à jour automatique GitHub

Cette version contient un système de mise à jour automatique.

Fonctionnement :
1. Au démarrage, l'application vérifie si une nouvelle version existe.
2. Elle compare APP_VERSION avec la version en ligne.
3. Si une version plus récente est disponible, elle propose à l'utilisateur de l'installer.
4. Elle télécharge le ZIP.
5. Elle vérifie le SHA256 si renseigné.
6. Elle lance un updater PowerShell séparé.
7. L'application se ferme.
8. L'updater remplace les fichiers et tente de relancer l'application.

À configurer dans app.py avant de publier :
- Option recommandée :
  GITHUB_UPDATE_REPO = "Lukiseven/RL-Overlay-Studio"

Ensuite, publie chaque nouvelle version dans GitHub Releases avec :
- le ZIP de l'application
- un fichier .sha256 contenant le hash SHA256 du ZIP

Option alternative :
- GITHUB_UPDATE_MANIFEST_URL = "URL_DIRECTE_DE_update.json"

Le fichier update.example.json fourni est un modèle si tu préfères utiliser un manifest JSON.


Dépôt GitHub configuré dans cette version :
Lukiseven/RL-Overlay-Studio

À publier dans GitHub Releases :
- Overlay_Studio_API_version_Beta_3.8_GitHub_READY.zip
- Overlay_Studio_API_version_Beta_3.8_GitHub_READY.zip.sha256
