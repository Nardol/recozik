# recozik

Application en ligne de commande conçue pour calculer des empreintes [Chromaprint](https://acoustid.org/chromaprint),
interroger l'API AcoustID et automatiser l'identification / le renommage de bibliothèques audio. La sortie texte reste
adaptée aux lecteurs d'écran et l'interface est désormais localisée.

- [Présentation](#présentation)
- [Backend web et tableau de bord](#backend-web-et-tableau-de-bord)
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

## Backend web et tableau de bord

Recozik fournit désormais un backend FastAPI mutualisé et un tableau de bord Next.js accessible :

- Consultez [docs/deploy-backend.md](docs/deploy-backend.md) (EN) ou
  [docs/deploy-backend.fr.md](docs/deploy-backend.fr.md) (FR) pour exposer l'API HTTP (téléversements, WebSockets,
  gestion des jetons).
- Consultez [docs/deploy-frontend.md](docs/deploy-frontend.md) (EN) ou
  [docs/deploy-frontend.fr.md](docs/deploy-frontend.fr.md) (FR) pour construire et déployer l'interface web.

Les définitions Docker Compose décrites dans la documentation permettent également de lancer le backend, le frontend et
Nginx en une seule commande (utile pour les tests locaux ou une mise en production minimale) :

```bash
cd docker
cp .env.example .env  # éditez les tokens/mots de passe avant de démarrer
docker compose up --build
```

Le fichier `.env.example` recense toutes les variables consommées par le `docker-compose.yml` :

- `RECOZIK_ADMIN_TOKEN` (injecté en `RECOZIK_WEB_ADMIN_TOKEN`), `RECOZIK_AUDD_TOKEN`, `RECOZIK_ACOUSTID_API_KEY`
- `RECOZIK_WEB_ADMIN_USERNAME`, `RECOZIK_WEB_ADMIN_PASSWORD`, éventuel `RECOZIK_WEB_READONLY_TOKEN`
- `RECOZIK_WEB_PRODUCTION_MODE` pour activer les garde-fous (cookies sécurisés, blocage des secrets par défaut)
- `RECOZIK_WEB_BASE_MEDIA_ROOT`, `RECOZIK_WEB_UPLOAD_SUBDIR`, `RECOZIK_WEBUI_UPLOAD_LIMIT`

Les valeurs `dev-*`/`demo-key` ne servent qu'au développement local : remplacez-les par des secrets robustes avant toute
exposition.

### Gestion des utilisateurs

Le tableau de bord web inclut un système complet de gestion des utilisateurs pour les administrateurs :

**Fonctionnalités utilisateur :**

- Comptes utilisateurs avec nom d'utilisateur, e-mail, nom d'affichage et stockage sécurisé des mots de passe (Argon2id)
- Basculement actif/inactif du statut utilisateur
- Contrôle d'accès basé sur les rôles (admin, operator, readonly)
- Permissions de fonctionnalités (identify, rename, traitement par lot, AudD, enrichissement MusicBrainz)
- Limites de quota par utilisateur pour les opérations API

**Tableau de bord administrateur :**

- **Gestion des utilisateurs** : Créer, éditer et supprimer des utilisateurs avec des opérations CRUD complètes
- **Gestion des mots de passe** : Réinitialisation des mots de passe initiée par l'administrateur avec exigences de robustesse (12+ caractères, majuscule, minuscule, chiffre, symbole)
- **Gestion des sessions** : Visualiser et révoquer les sessions actives pour n'importe quel utilisateur (déconnexion forcée)
- **Gestion des tokens API** : Créer des tokens API liés à des utilisateurs spécifiques pour l'accès CLI/automation

**Accéder au panneau administrateur :**

1. Connectez-vous au tableau de bord avec les identifiants admin (`RECOZIK_WEB_ADMIN_USERNAME` / `RECOZIK_WEB_ADMIN_PASSWORD`)
2. Naviguez vers la section "Admin" dans le menu de navigation
3. Gérez les utilisateurs, sessions et tokens API depuis les panneaux dédiés

**Exigences de mot de passe :**
Tous les mots de passe doivent respecter ces critères :

- Minimum 12 caractères
- Au moins une lettre majuscule
- Au moins une lettre minuscule
- Au moins un chiffre
- Au moins un symbole

**Schéma de base de données :**

- Les utilisateurs sont stockés dans `auth.db` (SQLite) avec des mots de passe hachés
- Les sessions suivent les tokens d'accès/rafraîchissement avec TTL configurable (1h accès, 7-30 jours rafraîchissement)
- Les tokens API référencent les utilisateurs via clé étrangère et héritent des permissions utilisateur

## Prérequis

- Python 3.10 à 3.14 (librosa 0.11 + numba 0.63 prennent en charge 3.14 ; Recozik installe automatiquement les paquets
  de remplacement `standard-*`/`audioop-lts`).
- [Chromaprint](https://acoustid.org/chromaprint) et son binaire `fpcalc` présents dans le `PATH`.
  - Linux : paquet `chromaprint` / `libchromaprint-tools` selon la distribution.
  - Windows : télécharger l'archive Chromaprint, extraire, ajouter le dossier contenant `fpcalc.exe` au `PATH`.
- Un backend de trousseau système (`python-keyring`) pour stocker les clés AcoustID/AudD de façon sécurisée. Sur un
  serveur sans trousseau, exportez `ACOUSTID_API_KEY` et `AUDD_API_TOKEN` avant chaque commande.
- Outil `msgfmt` optionnel si vous modifiez les traductions.
- FFmpeg (facultatif) + `pip install recozik[ffmpeg-support]` pour que le fallback AudD et `recozik inspect` puissent
  traiter les formats non pris en charge par libsndfile (par exemple les fichiers WMA volumineux).

## Installation

Recozik utilise [uv](https://docs.astral.sh/uv/) pour gérer l'environnement :

```bash
pip install uv
uv sync --all-groups
```

La commande crée un environnement virtuel local et installe les dépendances (runtime + dev) définies dans
`pyproject.toml`.

## Configuration d'AcoustID

1. Créer un compte sur <https://acoustid.org> puis générer une clé API (`Account → Create API Key`).
2. Enregistrer la clé via la CLI (elle est stockée dans le trousseau système via `python-keyring`) :

   ```bash
   uv run recozik config set-key
   ```

   Si aucun trousseau n'est disponible (serveur/headless), exportez `ACOUSTID_API_KEY` avant d'exécuter la commande.
   Pour supprimer la clé enregistrée, utilisez `uv run recozik config set-key --clear` (ou
   `uv run recozik config clear-secrets` pour effacer toutes les informations). Le fichier `config.toml` est stocké par
   défaut :
   - Linux/macOS : `~/.config/recozik/config.toml`
   - Windows : `%APPDATA%\recozik\config.toml`
   - Surcharge : définissez `RECOZIK_CONFIG_FILE=/chemin/vers/config.toml` avant d'exécuter la CLI.

3. Vérifier la configuration active :

   ```bash
   uv run recozik config show
   ```

Le fichier peut contenir d'autres options (TTL du cache, modèle d'affichage, mode de log). Un exemple figure dans la
section [Workflow de développement](#workflow-de-développement). Si votre `config.toml` contenait déjà ces valeurs en
clair, elles seront automatiquement migrées vers le trousseau lors de la prochaine exécution d'une commande `recozik`
(le fichier est réécrit avec un simple commentaire).

## Fallback AudD optionnel

Recozik peut interroger l'API [AudD Music Recognition](https://audd.io) quand AcoustID ne retourne aucun résultat. Cette
fonctionnalité reste entièrement facultative :

1. Créez un compte AudD et générez un token API. Chaque utilisateur de Recozik doit fournir son propre token et
   respecter les conditions d'AudD (l'accord public « API Test License Agreement » limite l'évaluation à 90 jours).
2. Enregistrez le token avec `uv run recozik config set-audd-token` (supprimez-le ensuite avec
   `uv run recozik config set-audd-token --clear` si besoin). Le token est sauvegardé dans le trousseau système ; si
   votre environnement n'a pas de backend, exportez `AUDD_API_TOKEN` ou passez `--audd-token` à chaque commande.
3. L'équipe AudD confirme que l'endpoint principal `https://api.audd.io/` n'analyse que les **12 premières secondes**
   d'un fichier et peut refuser les uploads volumineux. Basculez vers l'endpoint entreprise
   `https://enterprise.audd.io/` si vous souhaitez traiter l'intégralité d'un morceau.
4. Quand AudD identifie un titre, le JSON conserve l'origine via le champ `source` (`acoustid` ou `audd`) et les
   journaux ajoutent la note `Source: AudD.` — aucune bannière console n'est imposée.
5. Pour les formats qu'libsndfile ne sait pas lire (ex. WMA volumineux), installez `ffmpeg` et l'extra
   `pip install recozik[ffmpeg-support]`. Recozik réessaiera alors de générer l'extrait via FFmpeg avant d'abandonner le
   fallback AudD.

Par défaut, la CLI affiche la stratégie choisie sur `stderr` (ex. « Identification strategy: AcoustID first, AudD
fallback. »). Activez ou désactivez ce bandeau avec `--announce-source/--silent-source`, ou rendez le réglage persistant
via les clés `announce_source`.

Options avancées :

- `--audd-mode standard|enterprise|auto` choisit l'endpoint AudD à utiliser (le mode `auto` reste sur l'endpoint
  standard sauf si des paramètres enterprise sont activés).
- `--force-enterprise/--no-force-enterprise` impose l'endpoint entreprise, tandis que
  `--audd-enterprise-fallback/--no-audd-enterprise-fallback` relance automatiquement la requête via l'endpoint
  entreprise en cas d'absence de résultat.
- `--audd-endpoint-standard` et `--audd-endpoint-enterprise` permettent de surcharger les URLs par défaut fournies par
  AudD.
- `--audd-snippet-offset` décale l'extrait de 12 s envoyé au plan standard ; `--audd-snippet-min-rms` avertit lorsque
  l'extrait est quasi silencieux.
- Les options `--audd-skip`, `--audd-every`, `--audd-limit`, `--audd-skip-first`, `--audd-accurate-offsets` et
  `--audd-use-timecode` reproduisent les paramètres de l'API AudD Enterprise (fenêtres de 12 s, pas d'échantillonnage,
  offsets précis, timecodes, etc.).

Chaque option dispose d'un équivalent dans le fichier de configuration (`[audd]`) et via les variables d'environnement
`AUDD_ENDPOINT_STANDARD`, `AUDD_ENDPOINT_ENTERPRISE`, `AUDD_MODE`, `AUDD_FORCE_ENTERPRISE`, `AUDD_ENTERPRISE_FALLBACK`,
`AUDD_SKIP`, `AUDD_EVERY`, `AUDD_LIMIT`, `AUDD_SKIP_FIRST_SECONDS`, `AUDD_ACCURATE_OFFSETS`, `AUDD_USE_TIMECODE`,
`AUDD_SNIPPET_OFFSET` et `AUDD_SNIPPET_MIN_RMS`.

Selon les besoins, vous pouvez toujours désactiver ponctuellement le fallback avec `--no-audd`, ou au contraire
privilégier AudD avant AcoustID via `--prefer-audd`. Gardez en tête que chaque commande lit sa propre section :
`identify` récupère ses réglages (dont `audd_enabled`, `prefer_audd` et `announce_source`) dans `[identify]`, tandis que
`identify-batch` ne tient compte que de `[identify_batch]`.

Conseil : laissez le fallback désactivé dans les scripts partagés tant que chaque personne n'a pas accepté les
conditions AudD et fourni son jeton.

## Enrichissement MusicBrainz optionnel

Lorsque AcoustID ou AudD retournent un identifiant sans métadonnées complètes, Recozik peut interroger l'API JSON de
[MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API) pour renseigner l'artiste, le titre et les identifiants de
release :

1. Renseignez un User-Agent poli (par défaut `recozik/0.10.0`) et, si possible, une adresse de contact dans la section
   `[musicbrainz]` du `config.toml`. Aucun token n'est requis pour les requêtes en lecture seule.
2. Activez/désactivez l'enrichissement à la volée via `--with-musicbrainz/--without-musicbrainz`. Contrôlez si la
   requête doit se limiter aux correspondances incomplètes avec `--musicbrainz-missing-only/--musicbrainz-always`.
3. Respectez la limite de une requête par seconde : ajustez `rate_limit_per_second` et `timeout_seconds` si votre usage
   exige un rythme différent.

L'opération se fait localement : aucun appel n'est envoyé aux mainteneurs de Recozik, et les réponses déjà mises en
cache sont automatiquement enrichies si de nouvelles métadonnées sont découvertes.

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

Par défaut, la commande parcourt les fichiers avec les extensions `.mp3`, `.flac`, `.wav`, `.ogg`, `.m4a`, `.aac`,
`.opus` et `.wma`. Ajoutez des options `--ext` pour remplacer cette sélection.

Options utiles : `--pattern`, `--ext`, `--best-only`, `--refresh`, `--template "{artist} - {title}"`.

Renommage à partir d'un log JSONL :

```bash
uv run recozik rename-from-log logs/recozik.jsonl --root musique/ --apply
```

Ajouter `--interactive` pour choisir la proposition à la volée, `--metadata-fallback` pour se rabattre sur les tags
embarqués, `--backup-dir` pour conserver une copie et `--keep-template-duplicates` si vous souhaitez examiner toutes les
propositions même lorsque plusieurs produisent le même nom final. Le flux de renommage respecte également plusieurs clés
sous `[rename]` :

- `default_mode` : définit le comportement implicite de `--dry-run/--apply` (`dry-run` par défaut, `apply` pour
  appliquer directement).
- `interactive` : active la sélection interactive sans ajouter `--interactive` (par défaut `false`).
- `confirm_each` : demande une confirmation avant chaque renommage lorsque réglé à `true` (par défaut `false`).
- `conflict_strategy` : politique de collision par défaut (`append`, `skip` ou `overwrite` ; valeur par défaut
  `append`).
- `metadata_confirm` : impose (ou non) la confirmation des renommages basés sur les métadonnées (par défaut `true`).
- `deduplicate_template` : fusionne les propositions qui aboutiraient au même nom de fichier final lorsqu'il est réglé à
  `true` (valeur par défaut). Surchagez-le via `--deduplicate-template/--keep-template-duplicates`.
- `log_cleanup` : politique de nettoyage du journal JSONL après `--apply` (`ask`, `always` ou `never` ; valeur par
  défaut `ask`). Surchargez-la par commande avec `--log-cleanup`.
- `require_template_fields` : ignore les propositions qui n'ont pas toutes les valeurs exigées par le modèle (par défaut
  `false`). Modifiez-la à la volée avec `--require-template-fields/--allow-missing-template-fields`.

Deux sections optionnelles permettent aussi d'ajuster les commandes d'identification :

- `[musicbrainz]` paramètre l'enrichissement des correspondances (activation, User-Agent, contact, limite de requêtes,
  timeout, mode « missing only », token).
- `[identify]` configure la limite de résultats (`3`), la sortie JSON (`false`), le rafraîchissement du cache (`false`)
  et les réglages AudD (`audd_enabled = true`, `prefer_audd = false`) uniquement pour `identify`.
- `[identify_batch]` règle la limite par fichier (`3`), `best_only` (`false`), la récursivité (`false`), le journal par
  défaut (non défini → `recozik-batch.log` dans le répertoire courant) et les réglages AudD (`audd_enabled = true`,
  `prefer_audd = false`) exclusivement pour `identify-batch`.

Completions shell :

```bash
uv run recozik completion install --shell bash
uv run recozik completion install --shell zsh --no-write   # affiche uniquement le script
```

## Internationalisation

Le code source utilise des msgids en anglais. Les traductions vivent dans
`packages/recozik-core/src/recozik_core/locales/<lang>/LC_MESSAGES/`.

Ordre de priorité des locales :

1. Option CLI `--locale`
2. Variable d'environnement `RECOZIK_LOCALE`
3. Clé `[general].locale` dans `config.toml`
4. Locale système (retombe sur l'anglais si aucun catalogue n'est disponible)

Mettre à jour ou ajouter une langue :

1. Modifier le `.po` correspondant.
2. Recompiler avec `python scripts/compile_translations.py` (utilise `msgfmt` si présent, sinon un fallback Python).
3. Lancer les tests en anglais (`uv run pytest`) et, si besoin, dans la locale ciblée
   (`RECOZIK_LOCALE=fr_FR uv run pytest`).
4. Le document [TRANSLATION.md](TRANSLATION.md) détaille la procédure (extraction, compilation, bonnes pratiques).

## Workflow de développement

Commandes courantes (demander l'autorisation avant toute commande `uv …`) :

```bash
uv sync --all-groups
uv run recozik …
uv run ruff format
uv run ruff check --fix
uv run mypy                     # analyse statique sur l'ensemble de la CLI + recozik-core
uv run pytest
uv run recozik completion …
uv build
```

> Typage : tout `src/recozik` (ainsi que `recozik_core`) est contrôlé par mypy. Exécutez `uv run mypy` avant chaque PR
> et veillez à ce que les nouveaux modules restent dans ces répertoires.

Le test `tests/test_cli_import_time.py` vérifie que `recozik.cli` s'importe en moins de 0,5 s. Pour mesurer localement :

```bash
uv run python scripts/measure_import_time.py
```

Exemple de `config.toml` :

```toml
[acoustid]
api_key = "votre_cle"

[audd]
# api_token = "votre_token_audd"
# endpoint_standard = "https://api.audd.io/"
# endpoint_enterprise = "https://enterprise.audd.io/"
# mode = "standard"  # ou "enterprise", "auto"
# force_enterprise = false
# enterprise_fallback = false
# skip = [12, 24]
# every = 6.0
# limit = 8
# skip_first_seconds = 30.0
# accurate_offsets = false
# use_timecode = false

[musicbrainz]
# enabled = true
# app = "recozik"
# app_version = "0.10.0"
# contact = "vous@example.com"
# rate_limit_per_second = 1.0
# timeout_seconds = 5.0
# enrich_missing_only = true
# api_token = "stocké dans le trousseau"

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

# La commande batch ne lit que la section [identify_batch]; aucune valeur n'est reprise
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

<!-- markdownlint-disable MD013 -->

Chaque commande ne lit que la section qui porte son nom. Les valeurs définies sous `[identify]` ne servent jamais de
repli pour `[identify_batch]`, et inversement. Si vous voulez un comportement identique (par exemple pour `limit`,
`audd_enabled`, `prefer_audd` ou `announce_source`), dupliquez les réglages dans les deux blocs.

| Portée | Nom | Type / Valeurs | Valeur par défaut | Description | Méthode de configuration |
| ----------------------- | ----------------------- | -------------------------- | ------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------- |
| Fichier `[acoustid]` | `api_key` | chaîne | non défini | Commentaire : la clé est stockée dans le trousseau système. | `uv run recozik config set-key` (recommandé) ou variable `ACOUSTID_API_KEY`. |
| Fichier `[audd]` | `api_token` | chaîne | non défini | Commentaire : le jeton est stocké dans le trousseau système. | `uv run recozik config set-audd-token` (recommandé) ou variable `AUDD_API_TOKEN`. |
| Fichier `[audd]` | `endpoint_standard` | chaîne | `"https://api.audd.io/"` | URL de base de l'endpoint standard AudD (analyse les 12 premières secondes). | Édition de `config.toml` ou option `--audd-endpoint-standard`. |
| Fichier `[audd]` | `endpoint_enterprise` | chaîne | `"https://enterprise.audd.io/"` | URL de base de l'endpoint entreprise (analyse l'intégralité du fichier). | Édition de `config.toml` ou option `--audd-endpoint-enterprise`. |
| Fichier `[audd]` | `mode` | `standard` \\ | `enterprise` \\ | `auto` | `"standard"` | Mode AudD par défaut (`auto` bascule vers l'entreprise selon les besoins). | Édition de `config.toml` ou option `--audd-mode`. |
| Fichier `[audd]` | `force_enterprise` | booléen | `false` | Force l'utilisation systématique de l'endpoint entreprise. | Édition de `config.toml` ou option `--force-enterprise/--no-force-enterprise`. |
| Fichier `[audd]` | `enterprise_fallback` | booléen | `false` | Relance sur l'endpoint entreprise si la requête standard échoue/sans match. | Édition de `config.toml` ou option `--audd-enterprise-fallback/--no-audd-enterprise-fallback`. |
| Fichier `[audd]` | `skip` | liste d'entiers | `[]` | Enterprise : blocs de 12 s à ignorer (ex. `[12, 24]`). | Édition de `config.toml` ou option `--audd-skip`. |
| Fichier `[audd]` | `every` | flottant / secondes | non défini | Enterprise : intervalle entre les fenêtres analysées. | Édition de `config.toml` ou option `--audd-every`. |
| Fichier `[audd]` | `limit` | entier | non défini | Enterprise : nombre maximum de correspondances retournées. | Édition de `config.toml` ou option `--audd-limit`. |
| Fichier `[audd]` | `skip_first_seconds` | flottant / secondes | non défini | Enterprise : délai appliqué avant de commencer l'analyse. | Édition de `config.toml` ou option `--audd-skip-first`. |
| Fichier `[audd]` | `accurate_offsets` | booléen | `false` | Enterprise : calcule des offsets à la seconde près. | Édition de `config.toml` ou option `--audd-accurate-offsets/--no-audd-accurate-offsets`. |
| Fichier `[audd]` | `use_timecode` | booléen | `false` | Enterprise : demande des timecodes formatés dans la réponse. | Édition de `config.toml` ou option `--audd-use-timecode/--no-audd-use-timecode`. |
| Fichier `[audd]` | `snippet_offset` | flottant / secondes | `0.0` | Standard : décale l'extrait de 12 s avant l'envoi. | Édition de `config.toml` ou option `--audd-snippet-offset`. |
| Fichier `[audd]` | `snippet_min_rms` | flottant | non défini | Avertit si l'extrait AudD présente un RMS inférieur au seuil indiqué. | Édition de `config.toml` ou option `--audd-snippet-min-rms`. |
| Fichier `[musicbrainz]` | `enabled` | booléen | `true` | Active ou désactive l'enrichissement MusicBrainz. | Édition de `config.toml` ou option `--with-musicbrainz/--without-musicbrainz`. |
| Fichier `[musicbrainz]` | `app` / `app_version` | chaîne | `"recozik"` / `"0.10.0"` | User-Agent déclaré auprès de MusicBrainz. | Édition de `config.toml`. |
| Fichier `[musicbrainz]` | `contact` | chaîne | non défini | Coordonnée facultative ajoutée au User-Agent (email, URL). | Édition de `config.toml`. |
| Fichier `[musicbrainz]` | `rate_limit_per_second` | flottant | `1.0` | Limite de requêtes par seconde. | Édition de `config.toml`. |
| Fichier `[musicbrainz]` | `timeout_seconds` | flottant | `5.0` | Timeout appliqué à chaque requête. | Édition de `config.toml`. |
| Fichier `[musicbrainz]` | `enrich_missing_only` | booléen | `true` | Ne requête MusicBrainz que si artiste/titre sont manquants. | Édition de `config.toml` ou option `--musicbrainz-missing-only/--musicbrainz-always`. |
| Fichier `[cache]` | `enabled` | booléen | `true` | Active le cache local des correspondances. | Édition de `config.toml`. |
| Fichier `[cache]` | `ttl_hours` | entier | `24` | Durée de vie du cache en heures (minimum 1). | Édition de `config.toml`. |
| Fichier `[output]` | `template` | chaîne | `"{artist} - {title}"` | Modèle par défaut pour l'affichage/renommage. | Édition de `config.toml` ou option `--template`. |
| Fichier `[metadata]` | `fallback` | booléen | `true` | Autorise le repli sur les métadonnées embarquées. | Édition de `config.toml` ou `--metadata-fallback/--no-metadata-fallback`. |
| Fichier `[logging]` | `format` | `text` \| `jsonl` | `"text"` | Format du journal généré. | Édition de `config.toml`. |
| Fichier `[logging]` | `absolute_paths` | booléen | `false` | Force l'utilisation de chemins absolus dans les journaux. | Édition de `config.toml`. |
| Fichier `[general]` | `locale` | chaîne (ex. `fr`, `fr_FR`) | auto (locale système) | Locale préférée si l'option CLI et l'env sont absents. | Édition de `config.toml`. |
| Fichier `[identify]` | `limit` | entier >= 1 | `3` | Nombre de résultats retournés par défaut par `identify`. | Édition de `config.toml`. |

| Fichier `[identify]` | `json` | booléen | `false` | Affiche du JSON par défaut. | Édition de `config.toml`. |
| Fichier `[identify]` | `refresh` | booléen | `false` | Ignore le cache sauf désactivation explicite. | Édition de `config.toml`. |
| Fichier `[identify]` | `audd_enabled` | booléen | `true` | Active le fallback AudD lorsqu'un jeton est configuré. | `--use-audd/--no-audd` ou édition de `config.toml`. |
| Fichier `[identify]` | `prefer_audd` | booléen | `false` | Lance AudD avant AcoustID si activé. | `--prefer-audd/--prefer-acoustid` ou édition de `config.toml`. |
| Fichier `[identify]` | `announce_source` | booléen | `true` | Affiche la stratégie retenue sur `stderr`. | `--announce-source/--silent-source` ou édition de `config.toml`. |
| Fichier `[identify_batch]` | `limit` | entier >= 1 | `3` | Maximum de propositions conservées par fichier. | Édition de `config.toml`. |
| Fichier `[identify_batch]` | `best_only` | booléen | `false` | Conserve uniquement la meilleure proposition. | Édition de `config.toml`. |
| Fichier `[identify_batch]` | `recursive` | booléen | `false` | Analyse les sous-dossiers par défaut. | Édition de `config.toml`. |
| Fichier `[identify_batch]` | `log_file` | chaîne (chemin) | non défini → `recozik-batch.log` | Destination par défaut des journaux batch. | Édition de `config.toml`. |
| Fichier `[identify_batch]` | `audd_enabled` | booléen | `true` | Active AudD pendant l'identification en lot. | `--use-audd/--no-audd` ou édition de `config.toml`. |
| Fichier `[identify_batch]` | `prefer_audd` | booléen | `false` | Tente AudD avant AcoustID lors des traitements batch. | `--prefer-audd/--prefer-acoustid` ou édition de `config.toml`. |
| Fichier `[identify_batch]` | `announce_source` | booléen | `true` | Affiche la stratégie lot sur `stderr`. | `--announce-source/--silent-source` ou édition de `config.toml`. |
| Fichier `[rename]` | `default_mode` | `dry-run` \| `apply` | `"dry-run"` | Comportement implicite si ni `--dry-run` ni `--apply` ne sont passés. | Édition de `config.toml`. |
| Fichier `[rename]` | `interactive` | booléen | `false` | Active l'interactif sans ajouter l'option `--interactive`. | Édition de `config.toml`. |
| Fichier `[rename]` | `confirm_each` | booléen | `false` | Demande confirmation avant chaque renommage par défaut. | Édition de `config.toml`. |
| Fichier `[rename]` | `conflict_strategy` | `append` \| `skip` \| `overwrite` | `"append"` | Politique de collision appliquée par défaut. | Édition de `config.toml`. |
| Fichier `[rename]` | `metadata_confirm` | booléen | `true` | Imposer une confirmation pour les métadonnées. | Édition de `config.toml`. |
| Fichier `[rename]` | `log_cleanup` | `ask` \| `always` \| `never` | `"ask"` | Politique de nettoyage du log JSONL après `rename-from-log --apply`. | Édition de `config.toml` ou option `--log-cleanup`. |
| Fichier `[rename]` | `require_template_fields` | booléen | `false` | Rejette les correspondances sans toutes les valeurs du modèle. | Édition de `config.toml` ou `--require-template-fields/--allow-missing-template-fields`. |
| Fichier `[rename]` | `deduplicate_template` | booléen | `true` | Fusionne les propositions menant au même nom final. | Édition de `config.toml` ou `--deduplicate-template/--keep-template-duplicates`. |
| Environnement | `RECOZIK_CONFIG_FILE` | chemin | non défini | Chemin alternatif vers `config.toml`. | Exporter avant d'exécuter la CLI. |
| Environnement | `RECOZIK_LOCALE` | chaîne locale | non défini | Force la locale active (prioritaire sur le fichier). | Exporter avant d'exécuter la CLI. |
| Environnement | `ACOUSTID_API_KEY` | chaîne | non défini | Repli quand aucun trousseau système n'est disponible. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_API_TOKEN` | chaîne | non défini | Jeton AudD utilisé quand `--audd-token` est omis. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_ENDPOINT_STANDARD` | chaîne | non défini | Remplace l'URL de l'endpoint standard AudD. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_ENDPOINT_ENTERPRISE` | chaîne | non défini | Remplace l'URL de l'endpoint AudD entreprise. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_MODE` | `standard`/`enterprise`/`auto` | non défini | Force le mode AudD quand l'option CLI et la config sont absentes. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_FORCE_ENTERPRISE` | booléen | non défini | Force l'utilisation de l'endpoint entreprise (`true`/`false`). | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_ENTERPRISE_FALLBACK` | booléen | non défini | Relance sur l'endpoint entreprise si la requête standard échoue. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_SKIP` | liste d'entiers séparés par des virgules | non défini | Enterprise : blocs de 12 s à ignorer (ex. `12,24`). | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_EVERY` | flottant / secondes | non défini | Enterprise : espacement entre fenêtres analysées. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_LIMIT` | entier | non défini | Enterprise : limite le nombre de résultats. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_SKIP_FIRST_SECONDS` | flottant / secondes | non défini | Enterprise : décale le début de l'analyse. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_ACCURATE_OFFSETS` | booléen | non défini | Enterprise : active le calcul d'offsets précis. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_USE_TIMECODE` | booléen | non défini | Enterprise : demande des timecodes formatés dans la réponse. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_SNIPPET_OFFSET` | flottant / secondes | `0` | Standard : décale l'extrait de 12 s avant l'envoi. | Exporter avant d'exécuter la CLI. |
| Environnement | `AUDD_SNIPPET_MIN_RMS` | flottant | non défini | Avertit lorsque l'extrait AudD est quasi silencieux (RMS sous le seuil). | Exporter avant d'exécuter la CLI. |
| Environnement (auto) | `_RECOZIK_COMPLETE` | interne | gérée automatiquement | Variable gérée par les scripts de complétion, ne pas la définir à la main. | Configurée automatiquement lors du chargement de la complétion. |

<!-- markdownlint-enable MD013 -->

## Gestion sécurisée des secrets

Les commandes `recozik config set-key` et `set-audd-token` stockent désormais les identifiants AcoustID/AudD dans le
trousseau système (via `python-keyring`) au lieu de les écrire en clair dans `config.toml`.

- Lorsqu'un trousseau est disponible, le fichier de configuration ne contient plus que des commentaires d'aide. Les
  valeurs réelles sont récupérées depuis le trousseau à l'exécution.
- Sur un serveur sans backend keyring, vous pouvez exporter `ACOUSTID_API_KEY` / `AUDD_API_TOKEN` ou passer `--api-key`
  / `--audd-token` selon vos besoins.
- Si votre `config.toml` contenait déjà ces secrets en clair, ils sont migrés automatiquement lors du prochain appel à
  la CLI : Recozik les enregistre dans le trousseau puis réécrit le fichier sans les valeurs sensibles.
- Avant toute réécriture, Recozik sauvegarde `config.toml` sous la forme `config.toml.bak-YYYYmmddHHMMSS` dans le même
  dossier afin de permettre un retour arrière facile.
- Utilisez `uv run recozik config clear-secrets` (ou les options `--clear` des commandes individuelles décrites
  ci-dessous) pour supprimer les informations du trousseau lorsque vous changez de machine ou renouvelez vos clés.

## Tests

```bash
uv run ruff format
uv run ruff check --fix
uv run pytest
```

Un fixture pytest (`tests/conftest.py`) force la locale anglaise par défaut afin de garder les assertions stables.
Surcharger `RECOZIK_LOCALE` dans un test pour vérifier un rendu localisé.

## Contribuer

- Respecter le cycle format (`ruff format`), lint (`ruff check --fix`) et tests (`pytest`) avant toute contribution.
- Utiliser des messages de commit impératifs signés (`git commit -s`).
- Envelopper toute nouvelle chaîne utilisateur avec `_()` fourni par `recozik_core.i18n` et mettre à jour les catalogues
  de traductions.
- Les détails du workflow i18n sont décrits dans [TRANSLATION.md](TRANSLATION.md).

Merci d'avance pour vos contributions et vos retours !

> _Transparence :_ cette application a été développée avec l'assistance d'OpenAI Codex.
