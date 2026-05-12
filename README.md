# RL Overlay Studio

Application overlay Rocket League pour OBS.

## Licence

Ce projet est sous licence propriétaire.  
Voir le fichier `LICENSE.txt`.

La vente, reproduction, modification, redistribution ou réutilisation non autorisée
est strictement interdite.

## Mise à jour automatique

Cette version est configurée pour utiliser GitHub Releases comme source de mise à jour :

```python
GITHUB_UPDATE_REPO = "Lukiseven/RL-Overlay-Studio"
```

L'application vérifie automatiquement la dernière release GitHub au démarrage.

## Publication d'une nouvelle version

Pour publier une nouvelle version :

1. Modifier dans `app.py` :
   ```python
   APP_VERSION = "Beta X.X"
   APP_VERSION_LABEL = "Beta X.X By Luki7 / Eraclesss / Julianout"
   ```

2. Créer un ZIP de la nouvelle version.

3. Générer le SHA256 du ZIP avec :
   `GENERER_SHA256_ZIP.bat`

4. Créer une nouvelle GitHub Release.

5. Ajouter dans la release :
   - le fichier `.zip`
   - le fichier `.zip.sha256`

6. Publier la release.

L'application des utilisateurs détectera automatiquement la nouvelle version au prochain lancement.
