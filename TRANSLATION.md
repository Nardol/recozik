# Gestion des traductions

Recozik utilise `gettext` pour traduire les chaînes de la CLI. Les messages sources sont en anglais dans le code ; les catalogues se trouvent dans `src/recozik/locales/`.

## Structure

- `src/recozik/locales/<lang>/LC_MESSAGES/recozik.po` : fichier source (éditable).
- `src/recozik/locales/<lang>/LC_MESSAGES/recozik.mo` : fichier compilé utilisé à l'exécution (généré).
- `scripts/compile_translations.py` : script utilitaire pour recompiler tous les `.po` en `.mo`.

## Mettre à jour une traduction

1. Modifiez `recozik.po` avec votre éditeur en conservant les placeholders (`{artist}`, `{score}`, etc.).
2. Recompilez les catalogues :
   ```bash
   python scripts/compile_translations.py
   ```
   Le script produit/actualise automatiquement les `.mo` correspondants.
3. Lancez les tests en forçant la locale cible pour vérifier les messages :
   ```bash
   RECOZIK_LOCALE=fr_FR uv run pytest
   ```
4. Ajoutez les fichiers `.po` et `.mo` au commit.

## Ajouter une nouvelle langue

1. Copiez `src/recozik/locales/fr/LC_MESSAGES/recozik.po` vers le nouveau répertoire (`src/recozik/locales/<lang>/LC_MESSAGES/`).
2. Traduisez les entrées (`msgstr`). Laissez `msgid` inchangé.
3. Recompilez via `python scripts/compile_translations.py` (le `.mo` est généré automatiquement).
4. Vérifiez la locale via :
   ```bash
   RECOZIK_LOCALE=<lang> uv run recozik identify --help
   ```

## Priorité des locales

| Niveau | Description                                                       |
| ------ | ----------------------------------------------------------------- |
| 1      | Option CLI `--locale` (ex. `uv run recozik identify --locale fr`) |
| 2      | Variable d'environnement `RECOZIK_LOCALE`                         |
| 3      | Configuration utilisateur `[general] locale = "fr_FR"`            |
| 4      | Locale système détectée (fallback anglais si absent)              |

## Bonnes pratiques

- Chaque nouvelle chaîne visible utilisateur doit être entourée de `_()` dans le code.
- Préférez des phrases courtes et précises ; gardez les paramètres `{placeholder}` inchangés.
- Indiquez « fuzzy » (`#, fuzzy`) uniquement pour marquer une traduction approximative ; supprimez l'indicateur après validation.
- Vérifiez les sorties CLI dans les locales concernées (`RECOZIK_LOCALE=fr_FR`, etc.) et adaptez les tests si nécessaire.
