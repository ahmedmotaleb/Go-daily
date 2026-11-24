# Environments (U41)

Three environments, each with its own database, attachment storage, secrets and accounts. Nothing is shared between them.

| | Development | Staging | Production |
|---|---|---|---|
| `APP_ENV` | `development` | `staging` | `production` |
| Purpose | Local work, seeded fake data | Final check of each release with production-like setup | Real fleet |
| Database | Local PostgreSQL (`godaily`/`godaily`) | Its own instance, own credentials | Managed PostgreSQL with PITR |
| Attachments | Local folder | Its own bucket (or prefix + key limited to it) | Its own bucket, versioning on |
| Redis (rate limits) | Optional | Its own | Its own |
| Secrets | Development defaults | Its own, in the secret store | Its own, in the secret store, named owners |
| `DATA_ENCRYPTION_KEY` | Fixed development key | Its own key | Its own key (never copied elsewhere) |
| Accounts | Seed accounts | Test accounts only | Real staff and drivers |
| Driver app build | Debug, any URL | `-PgoDailyEnvironment=staging` (separate app id) | Release, production URL |
| `TWOFA_ENFORCE` | false | true | true |
| Monitoring | — | Scraped, alerts to the team | Scraped, alerts paged (`ops/monitoring/alerts.yml`) |

## Rules

- **No production data outside production.** Staging is seeded with test data, never with a copy of the production database, which holds personal data, locations and finances.
  - If a production-shaped dataset is needed, restore into an isolated, access-controlled server, run the drill there, and drop it afterwards (`BACKUP_RESTORE_DRILL.md`).
- **No production secrets anywhere else.**
  - CI uses only its own throwaway values (the PostgreSQL service `godaily`/`godaily`, a generated test key). It has no repository secrets for production, and none must be added.
  - Each environment has its own database user, bucket key, metrics token, encryption key and Android signing setup (staging builds use the same signing key, but a different application id).
- **Startup guard.** With `APP_ENV=staging` or `production`, the API refuses to start:
  - on the development database password;
  - without `DATA_ENCRYPTION_KEY`;
  - with a plain `http://` CORS origin.

  It logs a warning while `BOOTSTRAP_ADMIN_PASSWORD` is still set. Interactive API docs are off in production.
- **Names make the environment obvious.** Hosts like `api.staging.example.com` vs `api.example.com`. The staging app shows «نسخة تجريبية».

## Migration path

Every release moves the same way. A migration only reaches production after it has run on staging:

1. **CI** (`.github/workflows/ci.yml`):
   - lint, types and tests;
   - migrations apply to a clean database and downgrade cleanly;
   - web and Android builds.
2. **Staging:**
   - back up;
   - run `alembic upgrade head` (the `migrate` job);
   - deploy the API and web;
   - install the staging driver app;
   - run the smoke test (DEPLOYMENT.md §12) and the scenarios touched by the release;
   - keep it running for at least one day of normal use if the release changes GPS, money or the driver app.
3. **Production**, the same images and the same migration:
   - back up first;
   - deploy outside working hours where possible;
   - watch alerts for 30 minutes.
4. **Driver app:** staging build first, then production. Raise the version policy (DRIVER_APP_RELEASE.md §4) only after the new build is installed.

Migrations are additive ("expand, then contract", DEPLOYMENT.md §7), so the previous release still runs on the new schema and an application rollback needs no database change.

## Checklist before production (feeds U53)

- [ ] Staging exists with its own database, bucket, Redis, secrets and test accounts.
- [ ] Production secrets created by their owners and stored in the secret store; none in CI, images or the repository.
- [ ] `APP_ENV` set correctly on each server (the startup guard confirms no development defaults).
- [ ] The release under test has gone through staging (migration + smoke test).
- [ ] Staging and production driver app builds point at their own API.
