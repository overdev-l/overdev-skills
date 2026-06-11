---
name: deploy-tg-mini-game
description: Use when deploying a Telegram Mini App game from a tg-mini-game-factory style repository to production on Cloudflare Workers. Automates production readiness checks, Telegram and AdsGram SDK verification, Vite build variables, Wrangler secrets, Workers Static Assets deployment, optional custom domain binding, Supabase schema checks, and post-deploy verification.
---

# Deploy TG Mini Game

Deploy a Telegram Mini App game to Cloudflare Workers so the game is publicly reachable and production API calls use the same origin.

## Default Target

Assume the repository has this layout unless inspection proves otherwise:

- `apps/game`: Vite frontend
- `apps/api`: Hono Cloudflare Worker with `wrangler.jsonc`
- `supabase/schema.sql`: score and ad event tables

Use the bundled script first:

```bash
python3 skills/deploy-tg-mini-game/scripts/deploy_tg_mini_game.py \
  --repo /path/to/tg-mini-game-factory \
  --env-file /path/to/.env.production \
  --hostname game.overdev.cn
```

If the skill is installed outside the current repo, run the script from the installed skill path and pass `--repo`.

## Required Production Inputs

Read secrets from environment variables or a local env file. Do not print them.

- `CLOUDFLARE_API_TOKEN`: token with Workers deploy rights
- `CLOUDFLARE_ACCOUNT_ID`: recommended for Wrangler and domain operations
- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`
- `VITE_ADSGRAM_BLOCK_ID`

For automatic schema application, also provide:

- `SUPABASE_DB_URL`: Postgres connection string accepted by `psql`

If `SUPABASE_DB_URL` is absent, verify the Supabase REST tables and fail with clear instructions if the schema is missing.

## Workflow

1. Inspect the repo and confirm it is a tg-mini-game-factory style app.
2. Load production env from `--env-file`, `.env.production`, or the shell.
3. Ensure `apps/game/index.html` loads:
   - `https://telegram.org/js/telegram-web-app.js`
   - `https://sad.adsgram.ai/js/sad.min.js`
4. Set Worker secrets with `wrangler secret put` from env.
5. Force `VITE_API_BASE_URL` to an empty string for production unless the user explicitly provides another production URL.
6. Optionally apply `supabase/schema.sql` through `psql` when `--apply-supabase-schema` and `SUPABASE_DB_URL` are available.
7. Run typecheck and build.
8. Deploy from `apps/api` with Wrangler.
9. If `--hostname` is provided, bind it with Wrangler `--domain <hostname>` by default.
10. Verify `/health` and the public game URL.

Read `references/production-checklist.md` when diagnosing failures or when the user asks what permissions, env vars, or external setup are needed.

## Commands

Dry run without changing Cloudflare:

```bash
python3 skills/deploy-tg-mini-game/scripts/deploy_tg_mini_game.py \
  --repo . \
  --env-file .env.production \
  --hostname game.overdev.cn \
  --dry-run
```

Deploy with schema application:

```bash
python3 skills/deploy-tg-mini-game/scripts/deploy_tg_mini_game.py \
  --repo . \
  --env-file .env.production \
  --hostname game.overdev.cn \
  --apply-supabase-schema
```

Use Worker route mode instead of Custom Domain mode only when Custom Domain fails or the zone requires route-based deployment:

```bash
python3 skills/deploy-tg-mini-game/scripts/deploy_tg_mini_game.py \
  --repo . \
  --hostname game.overdev.cn \
  --domain-mode route
```

## Safety

- Never commit env files, tokens, Supabase keys, Telegram bot tokens, or Wrangler logs containing secrets.
- Keep `ALLOW_DEV_AUTH=false` in production.
- Do not deploy with `VITE_API_BASE_URL` pointing at localhost.
- If the target repo has uncommitted user changes, report them before modifying files.
- Do not delete or rotate existing Cloudflare secrets unless the user explicitly asks.
