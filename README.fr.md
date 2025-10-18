# recozik

Application en ligne de commande conçue pour calculer des empreintes [Chromaprint](https://acoustid.org/chromaprint), interroger l'API AcoustID et automatiser l'identification / le renommage de bibliothèques audio. La sortie texte reste adaptée aux lecteurs d'écran et l'interface est désormais localisée.

- [Présentation](#présentation)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration d'AcoustID](#configuration-dacoustid)
- [Exemples d'utilisation](#exemples-dutilisation)
- [Internationalisation](#internationalisation)
- [Workflow de développement](#workflow-de-développement)
- [Tests](#tests)
- [Contribuer](#contribuer)

> 🇬🇧 Need the documentation in English? See [README.md](README.md).

## Présentation

| Commande                  | Rôle                                                                                      |
| ------------------------- | ----------------------------------------------------------------------------------------- |
| `recozik inspect`         | Affiche les métadonnées de base d'un fichier audio.                                       |
| `recozik fingerprint`     | Génère les empreintes Chromaprint via `fpcalc`.                                           |
| `recozik identify`        | Identifie un fichier unique via AcoustID (fallback AudD optionnel).                       |
| `recozik identify-batch`  | Traite un répertoire entier, met en cache les résultats et exporte un log texte ou JSONL. |
| `recozik rename-from-log` | Applique les propositions issues du log pour organiser la bibliothèque.                   |
| `recozik completion …`    | Gère les scripts de complétion shell (Bash, Zsh, Fish, PowerShell).                       |
| `recozik config …`        | Persiste et consulte la configuration locale (clé API, cache, modèles, etc.).             |

## Prérequis

- Python 3.10, 3.11 ou 3.12 (librosa/Chromaprint ne gèrent pas encore Python 3.13).
- [Chromaprint](https://acoustid.org/chromaprint) et son binaire `fpcalc` présents dans le `PATH`.
  - Linux : paquet `chromaprint` / `libchromaprint-tools` selon la distribution.
  - Windows : télécharger l'archive Chromaprint, extraire, ajouter le dossier contenant `fpcalc.exe` au `PATH`.
- Outil `msgfmt` optionnel si vous modifiez les traductions.

## Installation

Recozik utilise [uv](https://docs.astral.sh/uv/) pour gérer l'environnement :

```bash
pip install uv
uv sync --all-groups
```

La commande crée un environnement virtuel local et installe les dépendances (runtime + dev) définies dans `pyproject.toml`.

## Configuration d'AcoustID

1. Créer un compte sur <https://acoustid.org> puis générer une clé API (`Account → Create API Key`).
2. Enregistrer la clé via la CLI :
   ```bash
   uv run recozik config set-key
   ```
   Le fichier `config.toml` est stocké par défaut :
   - Linux/macOS : `~/.config/recozik/config.toml`
   - Windows : `%APPDATA%\recozik\config.toml`
   - Surcharge : définissez `RECOZIK_CONFIG_FILE=/chemin/vers/config.toml` avant d'exécuter la CLI.
3. Vérifier la configuration active :
   ```bash
   uv run recozik config show
   ```

Le fichier peut contenir d'autres options (TTL du cache, modèle d'affichage, mode de log). Un exemple figure dans la section [Workflow de développement](#workflow-de-développement).

## Fallback AudD optionnel

Recozik peut interroger l'API [AudD Music Recognition](https://audd.io) quand AcoustID ne retourne aucun résultat. Cette fonctionnalité reste entièrement facultative :

1. Créez un compte AudD et générez un token API. Chaque utilisateur de Recozik doit fournir son propre token et respecter les conditions d'AudD (l'accord public « API Test License Agreement » limite l'évaluation à 90 jours).
2. Enregistrez le token avec `uv run recozik config set-audd-token`, exportez la variable `AUDD_API_TOKEN` ou passez `--audd-token` lors de l'exécution.
3. Quand AudD identifie un titre, Recozik affiche `Powered by AudD Music (fallback)` dans la console (et, en mode JSON, via `stderr`). Le flux JSON ajoute également un champ `source` (`acoustid` ou `audd`) pour tracer l'origine de la proposition.

Conseil : laissez le fallback désactivé dans les scripts partagés tant que chaque personne n'a pas accepté les conditions AudD et fourni son jeton.

## Exemples d'utilisation

Inspection rapide :

```bash
uv run recozik inspect chemin/vers/fichier.wav
```

Extraction de l'empreinte :

```bash
uv run recozik fingerprint chemin/vers/fichier.wav --output empreinte.json
```

Ajouter `--show-fingerprint` affiche l'empreinte brute dans la console (très longue).

Identification ponctuelle :

```bash
uv run recozik identify chemin/vers/fichier.wav --limit 5 --json
```

Traitement d'un dossier complet :

```bash
uv run recozik identify-batch musique/ --recursive --log-format jsonl --log-file logs/recozik.jsonl
```

Options utiles : `--pattern`, `--ext`, `--best-only`, `--refresh`, `--template "{artist} - {title}"`.

Renommage à partir d'un log JSONL :

```bash
uv run recozik rename-from-log logs/recozik.jsonl --root musique/ --apply
```

Ajouter `--interactive` pour choisir la proposition à la volée, `--metadata-fallback` pour se rabattre sur les tags embarqués, `--backup-dir` pour conserver une copie.
Le flux de renommage respecte également deux clés sous `[rename]` :

- `log_cleanup` : politique de nettoyage du journal JSONL après `--apply` (`ask`, `always` ou `never`). Surchargez-la par commande avec `--log-cleanup`.
- `require_template_fields` : ignore les propositions qui n’ont pas toutes les valeurs exigées par le modèle (`true`/`false`). Modifiez-la à la volée avec `--require-template-fields/--allow-missing-template-fields`.

Completions shell :

```bash
uv run recozik completion install --shell bash
uv run recozik completion install --shell zsh --no-write   # affiche uniquement le script
```

## Internationalisation

Le code source utilise des msgids en anglais. Les traductions vivent dans `src/recozik/locales/<lang>/LC_MESSAGES/`.

Ordre de priorité des locales :

1. Option CLI `--locale`
2. Variable d'environnement `RECOZIK_LOCALE`
3. Clé `[general].locale` dans `config.toml`
4. Locale système (retombe sur l'anglais si aucun catalogue n'est disponible)

Mettre à jour ou ajouter une langue :

1. Modifier le `.po` correspondant.
2. Recompiler avec `python scripts/compile_translations.py` (utilise `msgfmt` si présent, sinon un fallback Python).
3. Lancer les tests en anglais (`uv run pytest`) et, si besoin, dans la locale ciblée (`RECOZIK_LOCALE=fr_FR uv run pytest`).
4. Le document [TRANSLATION.md](TRANSLATION.md) détaille la procédure (extraction, compilation, bonnes pratiques).

## Workflow de développement

Commandes courantes (demander l'autorisation avant toute commande `uv …`) :

```bash
uv sync --all-groups
uv run recozik …
uv run ruff format
uv run ruff check --fix
uv run pytest
uv run recozik completion …
uv build
```

Exemple de `config.toml` :

```toml
[acoustid]
api_key = "votre_cle"

[audd]
# api_token = "votre_token_audd"

[cache]
enabled = true
ttl_hours = 24

[output]
template = "{artist} - {title}"

[metadata]
fallback = true

[logging]
format = "text"
absolute_paths = false

[general]
locale = "fr"
```

## Référence de configuration

| Portée               | Nom                       | Type / Valeurs               | Description                                                                | Méthode de configuration                                                                 |
| -------------------- | ------------------------- | ---------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Fichier `[acoustid]` | `api_key`                 | chaîne                       | Clé cliente AcoustID utilisée pour les requêtes.                           | `uv run recozik config set-key` ou édition de `config.toml`.                             |
| Fichier `[audd]`     | `api_token`               | chaîne                       | Jeton AudD utilisé en fallback.                                            | `uv run recozik config set-audd-token` ou édition de `config.toml`.                      |
| Fichier `[cache]`    | `enabled`                 | booléen                      | Active le cache local des correspondances.                                 | Édition de `config.toml`.                                                                |
| Fichier `[cache]`    | `ttl_hours`               | entier                       | Durée de vie du cache en heures (minimum 1).                               | Édition de `config.toml`.                                                                |
| Fichier `[output]`   | `template`                | chaîne                       | Modèle par défaut pour l'affichage/renommage.                              | Édition de `config.toml` ou option `--template`.                                         |
| Fichier `[metadata]` | `fallback`                | booléen                      | Autorise le repli sur les métadonnées embarquées.                          | Édition de `config.toml` ou `--metadata-fallback/--no-metadata-fallback`.                |
| Fichier `[logging]`  | `format`                  | `text` \| `jsonl`            | Format du journal généré.                                                  | Édition de `config.toml`.                                                                |
| Fichier `[logging]`  | `absolute_paths`          | booléen                      | Force l'utilisation de chemins absolus dans les journaux.                  | Édition de `config.toml`.                                                                |
| Fichier `[general]`  | `locale`                  | chaîne (ex. `fr`, `fr_FR`)   | Locale préférée si l'option CLI et l'env sont absents.                     | Édition de `config.toml`.                                                                |
| Fichier `[rename]`   | `log_cleanup`             | `ask` \| `always` \| `never` | Politique de nettoyage du log après `rename-from-log --apply`.             | Édition de `config.toml` ou option `--log-cleanup`.                                      |
| Fichier `[rename]`   | `require_template_fields` | booléen                      | Rejette les correspondances sans toutes les valeurs du modèle.             | Édition de `config.toml` ou `--require-template-fields/--allow-missing-template-fields`. |
| Environnement        | `RECOZIK_CONFIG_FILE`     | chemin                       | Chemin alternatif vers `config.toml`.                                      | Exporter avant d'exécuter la CLI.                                                        |
| Environnement        | `RECOZIK_LOCALE`          | chaîne locale                | Force la locale active (prioritaire sur le fichier).                       | Exporter avant d'exécuter la CLI.                                                        |
| Environnement        | `AUDD_API_TOKEN`          | chaîne                       | Jeton AudD utilisé quand `--audd-token` est omis.                          | Exporter avant d'exécuter la CLI.                                                        |
| Environnement (auto) | `_RECOZIK_COMPLETE`       | interne                      | Variable gérée par les scripts de complétion, ne pas la définir à la main. | Configurée automatiquement lors du chargement de la complétion.                          |

## Tests

```bash
uv run ruff format
uv run ruff check --fix
uv run pytest
```

Un fixture pytest (`tests/conftest.py`) force la locale anglaise par défaut afin de garder les assertions stables. Surcharger `RECOZIK_LOCALE` dans un test pour vérifier un rendu localisé.

## Contribuer

- Respecter le cycle format (`ruff format`), lint (`ruff check --fix`) et tests (`pytest`) avant toute contribution.
- Utiliser des messages de commit impératifs signés (`git commit -s`).
- Envelopper toute nouvelle chaîne utilisateur avec `_()` fourni par `recozik.i18n` et mettre à jour les catalogues de traductions.
- Les détails du workflow i18n sont décrits dans [TRANSLATION.md](TRANSLATION.md).

Merci d'avance pour vos contributions et vos retours !

> _Transparence :_ cette application a été développée avec l'assistance d'OpenAI Codex.
