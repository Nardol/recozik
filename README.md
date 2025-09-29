# recozik

Application en ligne de commande qui calcule des empreintes Chromaprint à partir de fichiers audio afin d'alimenter une reconnaissance musicale côté serveur ou via des APIs tierces. L'interface texte reste volontairement simple pour un usage fluide avec un lecteur d'écran.

## Prérequis
- Python 3.10, 3.11 ou 3.12 (librosa n'est pas encore compatible Python 3.13).
- [Chromaprint](https://acoustid.org/chromaprint) et son outil `fpcalc` dans le `PATH`.
  - **Linux** : installez le paquet `chromaprint` (ex. `sudo apt install libchromaprint-tools`).
  - **Windows** : téléchargez l'archive binaire depuis la page Chromaprint, extrayez-la et ajoutez le dossier contenant `fpcalc.exe` à votre `PATH`.

## Compatibilité des dépendances principales
- `librosa` publie un wheel universel (`py3-none-any`) depuis la version 0.11.0, facilitant l'installation sans compilation sur Windows, Linux et macOS.
- `soundfile` 0.13.x fournit des wheels précompilés incluant `libsndfile` pour Windows (x64/x86), Linux (glibc et musl) et macOS (x86_64/ARM64).
- `pyacoustid` 1.3.0 est fourni en sdist pur Python. Il expose ses API via le module `acoustid` et requiert l'exécutable `fpcalc` (Chromaprint) présent sur le système.
- `typer` 0.12+ reste un paquet pur Python (`py3-none-any`) et ne pose pas de contrainte supplémentaire.

## Configuration de la clé AcoustID
1. Créez un compte sur <https://acoustid.org> puis rendez-vous sur **Account → Create API Key**.
2. Générez une clé d'API (format alphanumérique) et conservez-la.
3. Enregistrez-la via la CLI :
   ```bash
   uv run recozik config set-key
   ```
   La commande vous demande la clé et l'enregistre dans un fichier utilisateur :
   - **Linux/macOS** : `~/.config/recozik/config.toml`
   - **Windows** : `%APPDATA%\recozik\config.toml`

Vous pouvez vérifier la valeur et le chemin avec `uv run recozik config show`. Pour un besoin avancé (tests ou profils multiples), pointez vers un fichier alternatif avec la variable d'environnement `RECOZIK_CONFIG_FILE` ou l'option cachée `--config-path`.

## Installation avec uv
1. Vérifiez/installez `uv` : `pip install uv` ou suivez la documentation officielle.
2. Initialisez l'environnement et les dépendances :
   ```bash
   uv sync
   ```
   Cela crée un environnement virtuel géré par uv et installe les bibliothèques déclarées dans `pyproject.toml`.

## Utilisation
- Inspecter un fichier audio :
  ```bash
  uv run recozik inspect chemin/vers/fichier.wav
  ```
- Générer l'empreinte Chromaprint (JSON écrit dans `fingerprint.json`) :
  ```bash
  uv run recozik fingerprint chemin/vers/fichier.wav --output fingerprint.json
  ```
  Ajoutez `--show-fingerprint` pour afficher l'empreinte brute dans le terminal (longue lecture).
- Si `fpcalc` n'est pas dans le `PATH`, utilisez `--fpcalc-path` pour lui indiquer l'exécutable.
- Identifier un morceau via AcoustID :
  ```bash
  uv run recozik identify chemin/vers/fichier.wav
  ```
  Utilisez `--limit` pour restreindre le nombre de résultats, `--template` pour ajuster l'affichage (`{artist} - {title}` par défaut), `--json` pour un rendu structuré, `--refresh` pour ignorer le cache et `--api-key` pour une clé ponctuelle (ex. usage CI).
- Identifier l'intégralité d'un dossier et consigner les résultats :
  ```bash
  uv run recozik identify-batch repertoire --recursive --log-file logs/recozik.log
  ```
  Options utiles : `--pattern '*.flac'`, `--ext mp3 --ext wav`, `--best-only`, `--log-format jsonl`, `--template "{artist} - {title} ({score})"`, `--refresh` pour ignorer le cache, `--append` pour ajouter au log existant.
- Gérer la configuration :
  ```bash
  uv run recozik config show
  uv run recozik config set-key --api-key VOTRE_CLE
  ```

## Cache et personnalisation
- Le fichier `config.toml` peut contenir d'autres sections pour ajuster le comportement :
  ```toml
  [acoustid]
  api_key = "votre_cle"

  [cache]
  enabled = true
  ttl_hours = 24

  [output]
  template = "{artist} - {title}"

  [logging]
  format = "text"      # ou "jsonl"
  absolute_paths = false
  ```
- Le cache local est partagé entre les commandes `identify` et `identify-batch`. Utilisez `--refresh` pour forcer ponctuellement une nouvelle requête AcoustID.
- Les modèles (`--template`) acceptent les champs `{artist}`, `{title}`, `{album}`, `{score}`, `{recording_id}`, etc. Le CLI a priorité sur la configuration.
- Les logs peuvent être produits en texte brut (lisible) ou en JSONL (parseable). Utilisez `--log-format` pour surcharger la valeur de configuration.

## Auto-complétion du shell
- Installer le script pour votre shell (détection automatique sinon) :
  ```bash
  uv run recozik completion install --shell bash
  ```
  Le chemin du script généré est indiqué en sortie, avec la commande `source …` à copier/coller dans votre fichier de profil (`~/.bashrc`, `~/.zshrc`, etc.). Ajoutez `--print-command` pour n'afficher que la ligne à copier. Utilisez `--shell auto` (ou omettez `--shell`) pour laisser recozik détecter votre shell.
- Visualiser le script si vous souhaitez l’inspecter ou l’intégrer différemment :
  ```bash
  uv run recozik completion show --shell zsh
  ```
- Supprimer la complétion installée :
  ```bash
  uv run recozik completion uninstall --shell bash
  ```
  Le fichier correspondant est supprimé et la commande affiche le fichier de profil à nettoyer si besoin.
- Générer le script sans écriture disque (pratique en CI) :
  ```bash
  uv run recozik completion install --shell bash --no-write
  ```
  Le script est renvoyé sur la sortie standard.
- Écrire le script dans un fichier personnalisé :
  ```bash
  uv run recozik completion install --shell bash --output dist/recozik-completion.sh
  ```
  Aucune modification n’est apportée au système ; vous pouvez ensuite décider comment l’inclure.

## Bonnes pratiques accessibilité
- Les commandes n'affichent que du texte brut compatible lecteurs d'écran.
- Préférez `--output` pour récupérer l'empreinte : cela évite de longues chaînes à lire vocalement.
- Aucune coloration ou mise en forme riche n'est utilisée par défaut.

## Construire et publier
- uv utilise `uv_build` comme backend :
  ```bash
  uv build
  ```
  Le paquet est assemblé dans `dist/`. Consultez la doc `uv build` pour les options (ex. `uv build --wheel-only`).

Produire le wheel localement permet de vérifier l'intégration continue ; `uv build` exploite le backend `uv_build` spécifié dans `pyproject.toml`.

## Tests
1. Installez les dépendances de test :
   ```bash
   uv sync --extra test
   ```
2. Lancez la suite :
   ```bash
   uv run pytest
   ```

## Étapes suivantes
- Ajouter une option de renommage assisté à partir du log batch.
- Fournir une intégration API AcoustID (soumission/score vers un service distant).
- Mettre en place une CI (GitHub Actions) qui exécute `uv run pytest` et `uv build`.
