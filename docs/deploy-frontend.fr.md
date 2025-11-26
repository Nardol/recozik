# Déployer le tableau de bord web Recozik

L'interface React/Next.js située dans `packages/recozik-webui` fournit un tableau de bord accessible pour les opérateurs
et administrateurs. Elle consomme l'API FastAPI via HTTPS.

## Prérequis

- Node.js 20 LTS (ou version plus récente) et npm 10+.
- Backend Recozik joignable en HTTPS (voir `docs/deploy-backend.md` ou `docs/deploy-backend.fr.md`).
- Reverse proxy (Caddy, Nginx, Apache…) pour terminer TLS côté frontend et backend.

## 1. Installer les dépendances

```bash
cd /chemin/vers/recozik/packages/recozik-webui
npm install
```

## 2. Configurer l'environnement

```bash
cp .env.example .env.local
# puis éditez :
NEXT_PUBLIC_RECOZIK_API_BASE=https://recozik.example.com
```

La valeur doit pointer vers l'URL publique du backend (sans slash final). Les jetons restent côté navigateur.

## 3. Build & exécution (bare-metal)

```bash
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Placez un reverse proxy devant ce serveur Next.js, terminez TLS au niveau du proxy et faites suivre `/` vers le
port 3000.

## 4. Exemple de reverse proxy (Caddy)

```caddy
recozik-ui.example.com {
  reverse_proxy 127.0.0.1:3000
  encode zstd gzip
}

recozik-api.example.com {
  reverse_proxy 127.0.0.1:8000
}
```

Utilisez idéalement le même domaine de premier niveau pour l'UI et l'API afin d'éviter les soucis de cookies ou de
stratégies CORS.

## 5. Tests d'accessibilité et smoke tests

- Se connecter avec un jeton admin et vérifier les annonces du lecteur d'écran lorsque l'état change.
- Téléverser un fichier audio, contrôler que la liste des tâches se met à jour (live region) et que le statut vocalise
  l'avancement.
- Naviguer uniquement au clavier (Tab / Shift+Tab) et vérifier la visibilité des focus.
- Lancer `npm run lint` pour exécuter ESLint + les vérifications Next.js.

## 6. Déploiement conteneurisé (Docker Compose)

```bash
cd docker
cp .env.example .env  # personnalisez les jetons et clefs
docker compose up --build
# Avec Podman :
# podman-compose up --build
# Ajoutez --profile reverse-proxy pour lancer Nginx :
# docker compose --profile reverse-proxy up --build
```

- Tableau de bord : <http://localhost:8080>
- API backend : <http://localhost:8080/api>

Dans ce scénario, `NEXT_PUBLIC_RECOZIK_API_BASE` vaut `/api`, ce qui permet aux navigateurs d'utiliser la même origine
via Nginx. Ajustez la variable dans `.env` si vous exposez la stack sous un autre hôte ou chemin.

Autres réglages `.env` utiles avec le Compose :

- `RECOZIK_WEBUI_UPLOAD_LIMIT` (transmis au build frontend ; `100mb` par défaut dans `.env.example`)
- L'auth du tableau de bord passe par une session (username/mot de passe). Les jetons API statiques
  (`RECOZIK_ADMIN_TOKEN`, éventuel `RECOZIK_WEB_READONLY_TOKEN`) visent les clients machines ; il n'existe pas de
  session UI « lecture seule » par défaut.
