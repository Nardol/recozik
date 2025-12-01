# Déployer le backend web Recozik

Le backend FastAPI contenu dans `packages/recozik-web` expose les fonctionnalités de la CLI via HTTP (authentification
par jeton, quotas, gestion des téléversements, WebSockets). Ce guide explique comment l'exécuter sur une machine Linux
ou dans les conteneurs fournis.

## Prérequis

- Hôte Linux avec Python 3.11 ou version plus récente.
- [uv](https://github.com/astral-sh/uv) pour la gestion des dépendances.
- Facultatif : systemd (ou un autre superviseur) pour maintenir le service actif.

## 1. Installer les dépendances

```bash
cd /chemin/vers/recozik
uv sync --all-groups
```

La commande crée `.venv/` et installe les dépendances runtime + dev.

## 2. Configurer les variables d'environnement

Toutes les options commencent par `RECOZIK_WEB_`. Les plus importantes :

| Variable                        | Description                                                                           |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| `RECOZIK_WEB_BASE_MEDIA_ROOT`   | Dossier qui stocke les téléversements, les bases SQLite et les caches.                |
| `RECOZIK_WEB_UPLOAD_SUBDIR`     | Sous-dossier relatif utilisé pour les fichiers temporaires (`uploads` par défaut).    |
| `RECOZIK_WEB_ADMIN_TOKEN`       | Jeton avec rôle `admin` (utilisé par la CLI et l'API).                                |
| `RECOZIK_WEB_ACOUSTID_API_KEY`  | Clé AcoustID utilisée pendant l'identification.                                       |
| `RECOZIK_WEB_AUDD_TOKEN`        | Jeton AudD optionnel. Laisser vide pour désactiver l'intégration.                     |
| `RECOZIK_WEB_JOBS_DATABASE_URL` | URL SQLModel pour la base des tâches (SQLite par défaut, stockée près du media root). |
| `RECOZIK_WEB_AUTH_DATABASE_URL` | URL SQLModel pour la base des jetons/quotas (SQLite par défaut).                      |

> **Sécurité :** générez toujours un jeton aléatoire pour `RECOZIK_WEB_ADMIN_TOKEN` (`openssl rand -hex 32` par
> exemple). N'utilisez jamais les valeurs d'exemple en production.

Exemple de `.env` :

```bash
RECOZIK_WEB_BASE_MEDIA_ROOT=/var/lib/recozik
RECOZIK_WEB_ADMIN_TOKEN=jeton-super-securise
RECOZIK_WEB_ACOUSTID_API_KEY=xxx
RECOZIK_WEB_AUDD_TOKEN=
RECOZIK_WEB_UPLOAD_SUBDIR=uploads
```

Créez le dossier média + le sous-dossier des uploads avec les bons droits avant de démarrer le service.

## 3. Lancer l'application FastAPI

```bash
uv run uvicorn recozik_web.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info
```

Activez CORS ou placez un reverse proxy TLS devant l'application si elle doit être exposée publiquement ou si le tableau
de bord Next.js y accède.

### Déploiements multi-worker

Le backend crée les utilisateurs/tokens admin et readonly au démarrage de l'application (via le gestionnaire de cycle de
vie FastAPI). Lors d'une exécution avec plusieurs workers (ex. `gunicorn -w 4` ou `uvicorn --workers 4`), chaque processus
worker exécute le seeding de démarrage indépendamment, ce qui peut causer une brève contention de verrous SQLite lorsque
les workers tentent simultanément d'upserter les mêmes tokens.

**Impact :** Ceci est sûr—les contraintes `UNIQUE` de SQLite et la logique `upsert` empêchent la corruption de données—mais
vous pouvez observer des avertissements transitoires `SQLITE_BUSY` dans les logs au démarrage. Les verrous se résolvent
automatiquement en quelques millisecondes.

**Schémas de déploiement recommandés :**

1. **Orchestration de conteneurs (Kubernetes, Docker Swarm) :** Exécutez **un worker par conteneur** et scalez
   horizontalement en ajoutant plus de conteneurs. C'est l'approche préférée en production :

   ```bash
   # Chaque conteneur exécute un seul processus uvicorn
   uvicorn recozik_web.app:app --host 0.0.0.0 --port 8000
   ```

   Avec Kubernetes, scalez les replicas au lieu des workers :

   ```yaml
   spec:
     replicas: 4 # Quatre pods, chacun avec un worker
   ```

2. **Multi-worker bare-metal :** Si vous avez besoin de plusieurs workers dans un seul processus (ex. `gunicorn -w 4` sur
   une VM), les verrous au démarrage sont inoffensifs. Assurez-vous que les fichiers SQLite sont sur un système de
   fichiers local (pas NFS) avec les permissions appropriées.

3. **Pre-seed au moment du build (optionnel) :** Pour des images de conteneur déterministes, vous pouvez créer les
   utilisateurs/tokens durant l'étape de build Docker pour éliminer complètement le seeding au runtime :

   ```dockerfile
   # Dans le Dockerfile, après l'installation des dépendances
   RUN python -c "from recozik_web.auth import seed_users_and_tokens_on_startup; \
                  from recozik_web.config import get_settings; \
                  seed_users_and_tokens_on_startup(get_settings())"
   ```

   Note : Cette approche nécessite que `RECOZIK_WEB_ADMIN_TOKEN` et les secrets associés soient disponibles au moment du
   build, ce qui peut ne pas être souhaitable pour des raisons de sécurité.

**Dépannage :** Si vous observez des erreurs de verrous persistantes (durant > 1 seconde) au démarrage, vérifiez que :

- Les fichiers de base de données (`auth.db`, `jobs.db`) sont sur un système de fichiers **local**, pas un montage réseau
- Le répertoire `RECOZIK_WEB_BASE_MEDIA_ROOT` a les permissions/propriétaire corrects
- Aucun autre processus ne détient de verrous sur les fichiers SQLite

Pour les configurations haute-disponibilité avec plusieurs instances backend, utilisez un worker par conteneur et un load
balancer (ex. Nginx, Traefik) pour distribuer les requêtes.

## 4. Service systemd (optionnel)

```ini
[Unit]
Description=Recozik Web API
After=network.target

[Service]
Type=simple
WorkingDirectory=/chemin/vers/recozik
EnvironmentFile=/etc/recozik-web.env
ExecStart=/chemin/vers/recozik/.venv/bin/uvicorn recozik_web.app:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=recozik
Group=recozik
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/recozik
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
```

Puis :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now recozik-web.service
```

## 5. Points de contrôle

- `GET /health` retourne `{ "status": "ok" }`.
- `GET /whoami` vérifie la validité d'un jeton.
- `GET /jobs/{id}` et `WS /ws/jobs/{id}` confirment la persistance des tâches et le streaming.

## 6. Déploiement conteneurisé (Docker / Podman)

Des définitions prêtes à l'emploi sont disponibles dans `docker/` :

```bash
cd docker
cp .env.example .env  # ajustez les jetons/clefs
docker compose up --build
# ou avec Podman :
# podman-compose up --build
# lancer le reverse proxy uniquement si nécessaire :
# docker compose --profile reverse-proxy up --build
```

La stack démarre trois services :

1. **backend** – image Python basée sur `docker/backend.Dockerfile`, stockage persistant dans le volume `recozik-data`
   monté sur `/data`.
2. **frontend** – tableau de bord Next.js (voir `docker/frontend.Dockerfile`).
3. **nginx** – proxy facultatif sur le port `8080` (`/` vers l'UI, `/api` vers FastAPI). Activez-le avec le profil
   `reverse-proxy`.

Mettez à jour `.env` avec vos secrets avant la mise en production. Le Compose est également utile pour reproduire
l'environnement sur une machine de développement dépourvue de Nginx.

Variables `.env` spécifiques au Compose (toutes optionnelles mais à renseigner explicitement) :

| Variable                      | Rôle / mapping backend                               | Valeur par défaut dans l'exemple |
| ----------------------------- | ---------------------------------------------------- | -------------------------------- |
| `RECOZIK_ADMIN_TOKEN`         | Jeton admin (passe en `RECOZIK_WEB_ADMIN_TOKEN`)     | `dev-admin`                      |
| `RECOZIK_WEB_ADMIN_USERNAME`  | Nom d'utilisateur admin seedé                        | `admin`                          |
| `RECOZIK_WEB_ADMIN_PASSWORD`  | Mot de passe admin seedé                             | `dev-password`                   |
| `RECOZIK_WEB_READONLY_TOKEN`  | Jeton API lecture seule (facultatif)                 | vide                             |
| `RECOZIK_ACOUSTID_API_KEY`    | Clé AcoustID                                         | `demo-key`                       |
| `RECOZIK_AUDD_TOKEN`          | Jeton AudD (laisser vide pour désactiver)            | vide                             |
| `RECOZIK_WEB_PRODUCTION_MODE` | Active cookies sécurisés / bloque les secrets défaut | `false`                          |
| `RECOZIK_WEB_BASE_MEDIA_ROOT` | Dossier media + BDD monté dans le conteneur          | `/data`                          |
| `RECOZIK_WEB_UPLOAD_SUBDIR`   | Sous-dossier d'upload relatif                        | `uploads`                        |
| `RECOZIK_WEBUI_UPLOAD_LIMIT`  | Limite de taille d'upload pour le build frontend     | `100mb`                          |

Remplacez les placeholders de développement avant toute exposition publique.
