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

- Python 3.10 à 3.13 (librosa >= 0.11 prend en charge 3.13 ; Recozik installe automatiquement les paquets de remplacement `standard-*`/`audioop-lts`).
- [Chromaprint](https://acoustid.org/chromaprint) et son binaire `fpcalc` présents dans le `PATH`.
  - Linux : paquet `chromaprint` / `libchromaprint-tools` selon la distribution.
  - Windows : télécharger l'archive Chromaprint, extraire, ajouter le dossier contenant `fpcalc.exe` au `PATH`.
- Outil `msgfmt` optionnel si vous modifiez les traductions.
- FFmpeg (facultatif) + `pip install recozik[ffmpeg-support]` pour que le fallback AudD et `recozik inspect` puissent traiter les formats non pris en charge par libsndfile (par exemple les fichiers WMA volumineux).

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
2. Enregistrez le token avec `uv run recozik config set-audd-token` (supprimez-le ensuite avec `uv run recozik config set-audd-token --clear` si besoin), exportez la variable `AUDD_API_TOKEN` ou passez `--audd-token` lors de l'exécution.
3. Quand AudD identifie un titre, le JSON conserve l'origine via le champ `source` (`acoustid` ou `audd`) et les journaux ajoutent la note `Source: AudD.` — aucune bannière console n'est imposée.
4. Pour les formats qu'libsndfile ne sait pas lire (ex. WMA volumineux), installez `ffmpeg` et l'extra `pip install recozik[ffmpeg-support]`. Recozik réessaiera alors de générer l'extrait via FFmpeg avant d'abandonner le fallback AudD.

Par défaut, la CLI affiche la stratégie choisie sur `stderr` (ex. « Identification strategy: AcoustID first, AudD fallback. »). Activez ou désactivez ce bandeau avec `--announce-source/--silent-source`, ou rendez le réglage persistant via les clés `announce_source`.

Selon les besoins, vous pouvez désactiver ponctuellement le fallback avec `--no-audd`, ou au contraire privilégier AudD avant AcoustID via `--prefer-audd`. Gardez en tête que chaque commande lit sa propre section : `identify` récupère ses réglages (dont `audd_enabled`, `prefer_audd` et `announce_source`) dans `[identify]`, tandis que `identify-batch` ne tient compte que de `[identify_batch]`.

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

Par défaut, la commande parcourt les fichiers avec les extensions `.mp3`, `.flac`, `.wav`, `.ogg`, `.m4a`, `.aac`, `.opus` et `.wma`. Ajoutez des options `--ext` pour remplacer cette sélection.

Options utiles : `--pattern`, `--ext`, `--best-only`, `--refresh`, `--template "{artist} - {title}"`.

Renommage à partir d'un log JSONL :

```bash
uv run recozik rename-from-log logs/recozik.jsonl --root musique/ --apply
```

Ajouter `--interactive` pour choisir la proposition à la volée, `--metadata-fallback` pour se rabattre sur les tags embarqués, `--backup-dir` pour conserver une copie et `--keep-template-duplicates` si vous souhaitez examiner toutes les propositions même lorsque plusieurs produisent le même nom final.
Le flux de renommage respecte également plusieurs clés sous `[rename]` :

- `default_mode` : définit le comportement implicite de `--dry-run/--apply` (`dry-run` par défaut, `apply` pour appliquer directement).
- `interactive` : active la sélection interactive sans ajouter `--interactive` (par défaut `false`).
- `confirm_each` : demande une confirmation avant chaque renommage lorsque réglé à `true` (par défaut `false`).
- `conflict_strategy` : politique de collision par défaut (`append`, `skip` ou `overwrite` ; valeur par défaut `append`).
- `metadata_confirm` : impose (ou non) la confirmation des renommages basés sur les métadonnées (par défaut `true`).
- `deduplicate_template` : fusionne les propositions qui aboutiraient au même nom de fichier final lorsqu'il est réglé à `true` (valeur par défaut). Surchagez-le via `--deduplicate-template/--keep-template-duplicates`.
- `log_cleanup` : politique de nettoyage du journal JSONL après `--apply` (`ask`, `always` ou `never` ; valeur par défaut `ask`). Surchargez-la par commande avec `--log-cleanup`.
- `require_template_fields` : ignore les propositions qui n’ont pas toutes les valeurs exigées par le modèle (par défaut `false`). Modifiez-la à la volée avec `--require-template-fields/--allow-missing-template-fields`.

Deux sections optionnelles permettent aussi d’ajuster les commandes d’identification :

- `[identify]` configure la limite de résultats (`3`), la sortie JSON (`false`), le rafraîchissement du cache (`false`) et les réglages AudD (`audd_enabled = true`, `prefer_audd = false`) uniquement pour `identify`.
- `[identify_batch]` règle la limite par fichier (`3`), `best_only` (`false`), la récursivité (`false`), le journal par défaut (non défini → `recozik-batch.log` dans le répertoire courant) et les réglages AudD (`audd_enabled = true`, `prefer_audd = false`) exclusivement pour `identify-batch`.

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

# Les réglages de [identify] ne concernent que la commande `identify` (fichier unique).
[identify]
limit = 3
json = false
refresh = false
audd_enabled = true
prefer_audd = false
announce_source = true

# La commande batch ne lit que la section [identify_batch]; aucune valeur n’est reprise
# depuis [identify].
[identify_batch]
limit = 3
best_only = false
recursive = false
# log_file = "recozik-batch.log"
audd_enabled = true
prefer_audd = false
announce_source = true

[rename]
# default_mode = "dry-run"
# interactive = false
# confirm_each = false
conflict_strategy = "append"
metadata_confirm = true
log_cleanup = "ask"
require_template_fields = false
deduplicate_template = true

[general]
locale = "fr"
```

## Référence de configuration

Chaque commande ne lit que la section qui porte son nom. Les valeurs définies sous `[identify]` ne servent jamais de repli pour `[identify_batch]`, et inversement. Si vous voulez un comportement identique (par exemple pour `limit`, `audd_enabled`, `prefer_audd` ou `announce_source`), dupliquez les réglages dans les deux blocs.

| Portée                     | Nom                       | Type / Valeurs                    | Valeur par défaut                | Description                                                                | Méthode de configuration                                                                 |
| -------------------------- | ------------------------- | --------------------------------- | -------------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Fichier `[acoustid]`       | `api_key`                 | chaîne                            | non défini                       | Clé cliente AcoustID utilisée pour les requêtes.                           | `uv run recozik config set-key` ou édition de `config.toml`.                             |
| Fichier `[audd]`           | `api_token`               | chaîne                            | non défini                       | Jeton AudD utilisé en fallback.                                            | `uv run recozik config set-audd-token` ou édition de `config.toml`.                      |
| Fichier `[cache]`          | `enabled`                 | booléen                           | `true`                           | Active le cache local des correspondances.                                 | Édition de `config.toml`.                                                                |
| Fichier `[cache]`          | `ttl_hours`               | entier                            | `24`                             | Durée de vie du cache en heures (minimum 1).                               | Édition de `config.toml`.                                                                |
| Fichier `[output]`         | `template`                | chaîne                            | `"{artist} - {title}"`           | Modèle par défaut pour l'affichage/renommage.                              | Édition de `config.toml` ou option `--template`.                                         |
| Fichier `[metadata]`       | `fallback`                | booléen                           | `true`                           | Autorise le repli sur les métadonnées embarquées.                          | Édition de `config.toml` ou `--metadata-fallback/--no-metadata-fallback`.                |
| Fichier `[logging]`        | `format`                  | `text` \| `jsonl`                 | `"text"`                         | Format du journal généré.                                                  | Édition de `config.toml`.                                                                |
| Fichier `[logging]`        | `absolute_paths`          | booléen                           | `false`                          | Force l'utilisation de chemins absolus dans les journaux.                  | Édition de `config.toml`.                                                                |
| Fichier `[general]`        | `locale`                  | chaîne (ex. `fr`, `fr_FR`)        | auto (locale système)            | Locale préférée si l'option CLI et l'env sont absents.                     | Édition de `config.toml`.                                                                |
| Fichier `[identify]`       | `limit`                   | entier >= 1                       | `3`                              | Nombre de résultats retournés par défaut par `identify`.                   | Édition de `config.toml`.                                                                |
| Fichier `[identify]`       | `json`                    | booléen                           | `false`                          | Affiche du JSON par défaut.                                                | Édition de `config.toml`.                                                                |
| Fichier `[identify]`       | `refresh`                 | booléen                           | `false`                          | Ignore le cache sauf désactivation explicite.                              | Édition de `config.toml`.                                                                |
| Fichier `[identify]`       | `audd_enabled`            | booléen                           | `true`                           | Active le fallback AudD lorsqu’un jeton est configuré.                     | `--use-audd/--no-audd` ou édition de `config.toml`.                                      |
| Fichier `[identify]`       | `prefer_audd`             | booléen                           | `false`                          | Lance AudD avant AcoustID si activé.                                       | `--prefer-audd/--prefer-acoustid` ou édition de `config.toml`.                           |
| Fichier `[identify]`       | `announce_source`         | booléen                           | `true`                           | Affiche la stratégie retenue sur `stderr`.                                 | `--announce-source/--silent-source` ou édition de `config.toml`.                         |
| Fichier `[identify_batch]` | `limit`                   | entier >= 1                       | `3`                              | Maximum de propositions conservées par fichier.                            | Édition de `config.toml`.                                                                |
| Fichier `[identify_batch]` | `best_only`               | booléen                           | `false`                          | Conserve uniquement la meilleure proposition.                              | Édition de `config.toml`.                                                                |
| Fichier `[identify_batch]` | `recursive`               | booléen                           | `false`                          | Analyse les sous-dossiers par défaut.                                      | Édition de `config.toml`.                                                                |
| Fichier `[identify_batch]` | `log_file`                | chaîne (chemin)                   | non défini → `recozik-batch.log` | Destination par défaut des journaux batch.                                 | Édition de `config.toml`.                                                                |
| Fichier `[identify_batch]` | `audd_enabled`            | booléen                           | `true`                           | Active AudD pendant l’identification en lot.                               | `--use-audd/--no-audd` ou édition de `config.toml`.                                      |
| Fichier `[identify_batch]` | `prefer_audd`             | booléen                           | `false`                          | Tente AudD avant AcoustID lors des traitements batch.                      | `--prefer-audd/--prefer-acoustid` ou édition de `config.toml`.                           |
| Fichier `[identify_batch]` | `announce_source`         | booléen                           | `true`                           | Affiche la stratégie lot sur `stderr`.                                     | `--announce-source/--silent-source` ou édition de `config.toml`.                         |
| Fichier `[rename]`         | `default_mode`            | `dry-run` \| `apply`              | `"dry-run"`                      | Comportement implicite si ni `--dry-run` ni `--apply` ne sont passés.      | Édition de `config.toml`.                                                                |
| Fichier `[rename]`         | `interactive`             | booléen                           | `false`                          | Active l'interactif sans ajouter l'option `--interactive`.                 | Édition de `config.toml`.                                                                |
| Fichier `[rename]`         | `confirm_each`            | booléen                           | `false`                          | Demande confirmation avant chaque renommage par défaut.                    | Édition de `config.toml`.                                                                |
| Fichier `[rename]`         | `conflict_strategy`       | `append` \| `skip` \| `overwrite` | `"append"`                       | Politique de collision appliquée par défaut.                               | Édition de `config.toml`.                                                                |
| Fichier `[rename]`         | `metadata_confirm`        | booléen                           | `true`                           | Imposer une confirmation pour les métadonnées.                             | Édition de `config.toml`.                                                                |
| Fichier `[rename]`         | `log_cleanup`             | `ask` \| `always` \| `never`      | `"ask"`                          | Politique de nettoyage du log JSONL après `rename-from-log --apply`.       | Édition de `config.toml` ou option `--log-cleanup`.                                      |
| Fichier `[rename]`         | `require_template_fields` | booléen                           | `false`                          | Rejette les correspondances sans toutes les valeurs du modèle.             | Édition de `config.toml` ou `--require-template-fields/--allow-missing-template-fields`. |
| Fichier `[rename]`         | `deduplicate_template`    | booléen                           | `true`                           | Fusionne les propositions menant au même nom final.                        | Édition de `config.toml` ou `--deduplicate-template/--keep-template-duplicates`.         |
| Environnement              | `RECOZIK_CONFIG_FILE`     | chemin                            | non défini                       | Chemin alternatif vers `config.toml`.                                      | Exporter avant d'exécuter la CLI.                                                        |
| Environnement              | `RECOZIK_LOCALE`          | chaîne locale                     | non défini                       | Force la locale active (prioritaire sur le fichier).                       | Exporter avant d'exécuter la CLI.                                                        |
| Environnement              | `AUDD_API_TOKEN`          | chaîne                            | non défini                       | Jeton AudD utilisé quand `--audd-token` est omis.                          | Exporter avant d'exécuter la CLI.                                                        |
| Environnement (auto)       | `_RECOZIK_COMPLETE`       | interne                           | gérée automatiquement            | Variable gérée par les scripts de complétion, ne pas la définir à la main. | Configurée automatiquement lors du chargement de la complétion.                          |

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
