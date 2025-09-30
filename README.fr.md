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

| Commande | Rôle |
| --- | --- |
| `recozik inspect` | Affiche les métadonnées de base d'un fichier audio. |
| `recozik fingerprint` | Génère les empreintes Chromaprint via `fpcalc`. |
| `recozik identify` | Identifie un fichier unique auprès du service AcoustID. |
| `recozik identify-batch` | Traite un répertoire entier, met en cache les résultats et exporte un log texte ou JSONL. |
| `recozik rename-from-log` | Applique les propositions issues du log pour organiser la bibliothèque. |
| `recozik completion …` | Gère les scripts de complétion shell (Bash, Zsh, Fish, PowerShell). |
| `recozik config …` | Persiste et consulte la configuration locale (clé API, cache, modèles, etc.). |

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
3. Vérifier la configuration active :
   ```bash
   uv run recozik config show
   ```

Le fichier peut contenir d'autres options (TTL du cache, modèle d'affichage, mode de log). Un exemple figure dans la section [Workflow de développement](#workflow-de-développement).

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
