# Guide de Migration de Base de Données

Ce document décrit les changements de schéma de base de données et les procédures de migration pour le backend web Recozik.

## Aperçu

Le backend web Recozik utilise des bases de données SQLite avec l'ORM SQLModel/SQLAlchemy. Les modifications de schéma peuvent nécessiter des étapes de migration manuelles lors de la mise à niveau.

**Fichiers de Base de Données** :

- `auth.db` - Comptes utilisateurs, sessions et jetons API (emplacement par défaut : `data/auth.db`)
- `jobs.db` - Suivi des tâches en arrière-plan pour l'identification de fichiers (emplacement par défaut : `data/jobs.db`)

**Gestion du Schéma** : SQLModel crée automatiquement les tables via `SQLModel.metadata.create_all()` lors de la première initialisation de la base de données. Cependant, les modifications de schéma sur les tables **existantes** nécessitent une migration manuelle.

---

## Changements de Schéma pour la Gestion des Utilisateurs (2025-01-30)

### Résumé

Ajout d'un système complet de gestion des utilisateurs avec :

- Nouvelle table `User` pour les comptes utilisateurs
- Modifications du schéma de la table `SessionToken` (`user_id` changé de string à entier clé étrangère)
- Nouveaux endpoints admin pour les opérations CRUD des utilisateurs
- Hachage des mots de passe avec Argon2id
- Contrôle d'accès basé sur les rôles (admin, operator, readonly)
- Permissions de fonctionnalités et limites de quota par utilisateur

### Changements Incompatibles

**⚠️ CRITIQUE** : Le champ `SessionToken.user_id` est passé de `str` à `int` (clé étrangère vers `User.id`). Il s'agit d'un **changement de schéma incompatible** qui nécessite une migration.

### Étapes de Migration

#### Option 1 : Nouveau Départ (Recommandé pour le Développement)

Si vous n'avez pas besoin de conserver les sessions existantes :

```bash
# Sauvegarder la base de données existante
cp data/auth.db data/auth.db.backup

# Supprimer la base de données (elle sera recréée avec le nouveau schéma)
rm data/auth.db

# Redémarrer le backend - il créera le nouveau schéma
cd packages/recozik-web
uv run uvicorn recozik_web.app:app --host 0.0.0.0 --port 8000
```

Le backend va automatiquement :

1. Créer la nouvelle table `User`
2. Créer la table `SessionToken` mise à jour avec `user_id` comme clé étrangère entière
3. Créer l'utilisateur admin initial à partir des variables d'environnement

**Utilisateur Admin Initial** :
Définissez ces variables d'environnement avant de démarrer :

```bash
export RECOZIK_WEB_ADMIN_USERNAME="admin"
export RECOZIK_WEB_ADMIN_PASSWORD="votre-mot-de-passe-securise"
export RECOZIK_WEB_ADMIN_EMAIL="admin@example.com"
```

#### Option 2 : Migration Manuelle (Préserver les Données)

Si vous devez conserver les sessions existantes, utilisez ce script de migration SQLite :

```bash
# Sauvegardez d'abord !
cp data/auth.db data/auth.db.backup

# Connectez-vous à la base de données
sqlite3 data/auth.db
```

Puis exécutez ces commandes SQL :

```sql
-- Créer la nouvelle table User
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    roles TEXT DEFAULT '[]',  -- Tableau JSON
    allowed_features TEXT DEFAULT '[]',  -- Tableau JSON
    quota_limits TEXT DEFAULT '{}',  -- Objet JSON
    created_at TEXT NOT NULL
);

-- Créer les index
CREATE INDEX IF NOT EXISTS ix_user_username ON user (username);
CREATE INDEX IF NOT EXISTS ix_user_email ON user (email);

-- Créer une table de migration pour les anciennes valeurs user_id
CREATE TABLE sessiontoken_migration (
    old_user_id TEXT,
    new_user_id INTEGER
);

-- Insérer les valeurs user_id uniques depuis SessionToken
INSERT INTO sessiontoken_migration (old_user_id)
SELECT DISTINCT user_id FROM sessiontoken;

-- Créer des enregistrements User pour chaque user_id unique
-- NOTE : Vous devez définir des mots de passe, emails, rôles et fonctionnalités appropriés
-- Cela crée des utilisateurs temporaires - mettez-les à jour ensuite !
INSERT INTO user (username, email, password_hash, roles, allowed_features, created_at)
SELECT
    old_user_id,
    old_user_id || '@example.com',  -- Email temporaire
    '$argon2id$v=19$m=65536,t=3,p=4$placeholder',  -- INVALIDE - doit être réinitialisé !
    '["readonly"]',
    '["identify"]',
    datetime('now')
FROM sessiontoken_migration;

-- Mettre à jour la table de migration avec les nouveaux IDs utilisateur
UPDATE sessiontoken_migration
SET new_user_id = (
    SELECT u.id FROM user u
    WHERE u.username = sessiontoken_migration.old_user_id
);

-- Créer une nouvelle table SessionToken avec le schéma correct
CREATE TABLE sessiontoken_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    refresh_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    refresh_expires_at TEXT NOT NULL,
    remember INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES user (id)
);

CREATE INDEX ix_sessiontoken_new_session_id ON sessiontoken_new (session_id);
CREATE INDEX ix_sessiontoken_new_user_id ON sessiontoken_new (user_id);
CREATE INDEX ix_sessiontoken_new_refresh_token ON sessiontoken_new (refresh_token);

-- Migrer les données vers la nouvelle table
INSERT INTO sessiontoken_new (
    session_id, user_id, refresh_token, created_at,
    expires_at, refresh_expires_at, remember
)
SELECT
    s.session_id,
    m.new_user_id,
    s.refresh_token,
    s.created_at,
    s.expires_at,
    s.refresh_expires_at,
    s.remember
FROM sessiontoken s
JOIN sessiontoken_migration m ON s.user_id = m.old_user_id;

-- Remplacer l'ancienne table par la nouvelle
DROP TABLE sessiontoken;
ALTER TABLE sessiontoken_new RENAME TO sessiontoken;

-- Nettoyer
DROP TABLE sessiontoken_migration;

-- Vérifier la migration
SELECT COUNT(*) FROM user;
SELECT COUNT(*) FROM sessiontoken;

.quit
```

**Étapes Post-Migration** :

1. **Réinitialiser tous les mots de passe utilisateur** (le hash temporaire est invalide) :

   ```bash
   # Utiliser l'API admin ou recréer les utilisateurs avec les bonnes informations
   # Exemple : Utilisateur admin
   export RECOZIK_WEB_ADMIN_USERNAME="admin"
   export RECOZIK_WEB_ADMIN_PASSWORD="MotDePasseSecurise123!"
   export RECOZIK_WEB_ADMIN_EMAIL="admin@example.com"

   # Démarrer le backend et utiliser l'endpoint /admin/users/{id}/reset-password
   ```

2. **Mettre à jour les rôles et fonctionnalités des utilisateurs** via le tableau de bord admin ou l'API

3. **Vérifier que les sessions** fonctionnent toujours en se connectant

### Détails du Schéma

#### Table User

```python
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    display_name: str | None = Field(default=None)
    password_hash: str  # Argon2id
    is_active: bool = Field(default=True)
    roles: list[str] = Field(default_factory=list)  # JSON: ["admin", "operator", "readonly"]
    allowed_features: list[str] = Field(default_factory=list)  # JSON: ["identify", "rename", ...]
    quota_limits: dict[str, int | None] = Field(default_factory=dict)  # JSON: {"acoustid_lookup": 100, ...}
    created_at: datetime
```

#### Table SessionToken (Mise à Jour)

```python
class SessionToken(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    user_id: int = Field(index=True, foreign_key="user.id")  # ← Changé de str
    refresh_token: str = Field(index=True, unique=True)
    created_at: datetime
    expires_at: datetime
    refresh_expires_at: datetime
    remember: bool = Field(default=False)
```

### Nouveaux Endpoints API

**Gestion des Utilisateurs** (admin uniquement) :

- `GET /admin/users` - Lister tous les utilisateurs (pagination)
- `GET /admin/users/{id}` - Obtenir les détails d'un utilisateur
- `PUT /admin/users/{id}` - Mettre à jour un utilisateur
- `DELETE /admin/users/{id}` - Supprimer un utilisateur
- `POST /admin/users/{id}/reset-password` - Réinitialisation admin du mot de passe
- `GET /admin/users/{id}/sessions` - Lister les sessions d'un utilisateur
- `DELETE /admin/users/{id}/sessions` - Révoquer toutes les sessions d'un utilisateur

**Authentification** :

- `POST /auth/register` - Créer un nouvel utilisateur (admin uniquement)
- Les endpoints existants `/auth/login`, `/auth/logout`, `/auth/refresh`, `/whoami` fonctionnent avec le nouveau modèle User

### Exigences de Mot de Passe

Tous les mots de passe doivent respecter ces critères :

- Minimum 12 caractères
- Au moins une lettre majuscule
- Au moins une lettre minuscule
- Au moins un chiffre
- Au moins un symbole

### Variables d'Environnement

Nouvelles variables pour la configuration admin initiale :

```bash
# Requis pour le premier démarrage
RECOZIK_WEB_ADMIN_USERNAME="admin"
RECOZIK_WEB_ADMIN_PASSWORD="VotreMotDePasseSecurise123!"
RECOZIK_WEB_ADMIN_EMAIL="admin@example.com"

# Optionnel - personnaliser l'utilisateur admin
RECOZIK_WEB_ADMIN_DISPLAY_NAME="Administrateur Système"
```

Paramètres de base de données d'authentification existants :

```bash
RECOZIK_WEB_AUTH_DATABASE_URL="sqlite:///data/auth.db"
```

### Test de la Migration

1. **Vérifier le schéma de la base de données** :

   ```bash
   sqlite3 data/auth.db ".schema user"
   sqlite3 data/auth.db ".schema sessiontoken"
   ```

2. **Vérifier le nombre d'utilisateurs** :

   ```bash
   sqlite3 data/auth.db "SELECT COUNT(*) FROM user;"
   ```

3. **Tester la connexion** :

   ```bash
   curl -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"VotreMotDePasseSecurise123!"}'
   ```

4. **Accéder aux endpoints admin** :
   ```bash
   # Obtenir les cookies de session depuis la réponse de connexion
   curl -X GET http://localhost:8000/admin/users \
     -H "Cookie: recozik_session=..." \
     -H "X-CSRF-Token: ..."
   ```

### Procédure de Retour en Arrière

En cas d'échec de la migration :

```bash
# Arrêter le backend
# Restaurer la sauvegarde
cp data/auth.db.backup data/auth.db

# Revenir à la version précédente
git checkout <commit-precedent>

# Redémarrer le backend
```

---

## Migrations Futures

Pour les futurs changements de schéma :

1. **Toujours sauvegarder** `data/auth.db` et `data/jobs.db` avant la mise à niveau
2. **Vérifier CHANGELOG.md** pour les changements incompatibles
3. **Consulter les notes de migration** dans ce fichier
4. **Tester d'abord** dans un environnement de développement
5. **Utiliser le dump SQLite** pour les migrations complexes :
   ```bash
   sqlite3 data/auth.db .dump > backup.sql
   ```

### Bonnes Pratiques de Migration

- Utiliser des transactions pour les migrations multi-étapes
- Créer des tables temporaires pour la transformation des données
- Vérifier l'intégrité des clés étrangères après les changements de schéma
- Tester avec des volumes de données similaires à la production
- Conserver les anciennes sauvegardes pendant au moins un cycle de version

---

## Dépannage

### "FOREIGN KEY constraint failed"

Le `SessionToken.user_id` doit référencer un `User.id` existant. Assurez-vous que tous les utilisateurs sont créés avant de migrer les sessions.

### "no such column: sessiontoken.user_id"

L'ancien schéma est toujours utilisé. Exécutez le script de migration ou supprimez et recréez la base de données.

### "Invalid password hash"

Les hashs temporaires de la migration sont invalides. Réinitialisez les mots de passe via :

```bash
curl -X POST http://localhost:8000/admin/users/1/reset-password \
  -H "Content-Type: application/json" \
  -H "Cookie: recozik_session=..." \
  -H "X-CSRF-Token: ..." \
  -d '{"new_password":"NouveauSecurise123!"}'
```

### Sessions expirées après la migration

C'est normal si vous avez supprimé la base de données. Les utilisateurs doivent se reconnecter pour créer de nouvelles sessions.

---

## Support

Pour les problèmes de migration :

1. Consultez les [GitHub Issues](https://github.com/anthropics/claude-code/issues)
2. Examinez les logs du backend pour les erreurs SQLAlchemy
3. Vérifiez l'intégrité de la base de données SQLite : `sqlite3 data/auth.db "PRAGMA integrity_check;"`
