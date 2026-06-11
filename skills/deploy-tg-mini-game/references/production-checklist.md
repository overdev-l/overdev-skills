# TG Mini Game Production Checklist

## Cloudflare Token

Use a user API token scoped to the deployment account. The Cloudflare "Edit Cloudflare Workers" template is the preferred starting point.

Required or commonly needed permissions:

- Account: `Workers Scripts: Edit`
- Account: `Account Settings: Read`
- User: `User Details: Read`
- User: `Memberships: Read`
- Zone: `Workers Routes: Edit` for route mode or custom domains on a zone

Scope the token to the single Cloudflare account and, if zone access is required, only the target zone.

## Runtime Secrets

Set these with Wrangler secrets, not committed files:

- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`

The deployment script reads them from the shell or `--env-file` and pipes values into `wrangler secret put`.

## Build-Time Variables

These affect the Vite build:

- `VITE_AD_PROVIDER`: defaults to `monetag`
- `VITE_REWARDED_AD_ZONE_ID`: required for real rewarded ads
- `VITE_GAME_APP_ID`: optional, defaults to the shared template app id
- `VITE_API_BASE_URL`: should usually be empty in production so API calls use the same Cloudflare Worker origin

## Telegram and Ad Provider

Production HTML must load the Telegram browser SDK before the Vite entry script:

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
```

Without the Telegram SDK, `Telegram.WebApp.initData` can be absent and authenticated score/ad endpoints fail.

The default ad provider is Monetag. The app should use `monetag-tg-sdk`, which injects the Monetag SDK script from the configured zone id at runtime. If the provider is changed to AdsGram or another network, confirm that the provider adapter either loads its SDK or that the production HTML includes the required provider script.

## Supabase

Run `supabase/schema.sql` before production traffic. If `SUPABASE_DB_URL` is available, the script can apply it with:

```bash
python3 skills/deploy-tg-mini-game/scripts/deploy_tg_mini_game.py --apply-supabase-schema
```

If a database URL is not available, apply the SQL manually in Supabase SQL Editor, then rerun deployment verification.

## Domain Modes

Prefer `--domain-mode custom-domain`, which runs Wrangler with:

```bash
wrangler deploy --domain <hostname>
```

Use `--domain-mode route` only when Custom Domains are not suitable. Route mode runs:

```bash
wrangler deploy --route <hostname>/*
```

Route mode requires the hostname to be on a Cloudflare-managed zone and DNS to resolve through Cloudflare.

## Verification

After deployment:

- `https://<hostname>/health` returns JSON with `ok: true`
- `storage` is `supabase`, not `memory`
- the game loads inside Telegram
- score submit works with real Telegram `initData`
- the selected rewarded ad provider resolves only after a completed rewarded view
