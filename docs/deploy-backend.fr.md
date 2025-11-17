# Déployer le backend web Recozik

Le backend FastAPI contenu dans `packages/recozik-web` expose les fonctionnalités de la CLI via HTTP (authentification par jeton, quotas, gestion des téléversements, WebSockets). Ce guide explique comment l'exécuter sur une machine Linux ou dans les conteneurs fournis.

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

> **Sécurité :** générez toujours un jeton aléatoire pour `RECOZIK_WEB_ADMIN_TOKEN` (`openssl rand -hex 32` par exemple). N'utilisez jamais les valeurs d'exemple en production.

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

Activez CORS ou placez un reverse proxy TLS devant l'application si elle doit être exposée publiquement ou si le tableau de bord Next.js y accède.

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

1. **backend** – image Python basée sur `docker/backend.Dockerfile`, stockage persistant dans le volume `recozik-data` monté sur `/data`.
2. **frontend** – tableau de bord Next.js (voir `docker/frontend.Dockerfile`).
3. **nginx** – proxy facultatif sur le port `8080` (`/` vers l'UI, `/api` vers FastAPI). Activez-le avec le profil `reverse-proxy`.

Mettez à jour `.env` avec vos secrets avant la mise en production. Le Compose est également utile pour reproduire l'environnement sur une machine de développement dépourvue de Nginx.
