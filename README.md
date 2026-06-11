# overdev-skills

Claude Code skills published by [@overdev-l](https://github.com/overdev-l).

## Skills

### `deploy-tg-mini-game` — Telegram Mini Game → Cloudflare Workers production

Deploys a `tg-mini-game-factory` style Telegram Mini App game to Cloudflare Workers with Static Assets, Wrangler secrets, production Vite variables, optional Supabase schema application, and optional custom domain binding.

**Install:**

```bash
npx skills add overdev-l/overdev-skills --skill deploy-tg-mini-game
```

Use it when you want a game repository to become publicly reachable in production after providing Cloudflare, Telegram, Supabase, ad provider, and optional hostname configuration.

### `overdev-site` — Cloudflare DNS → 1Panel/OpenResty site

Creates or updates an `overdev.cn` service entrypoint by adding a Cloudflare DNS record, binding the hostname to a local service port through 1Panel OpenResty, issuing a Let's Encrypt certificate, and installing a renewal hook.

**Install:**

```bash
npx skills add overdev-l/overdev-skills --skill overdev-site
```

Use it when publishing services such as `n8n.overdev.cn`, `dify.overdev.cn`, or any other app running on the overdev OCI host.

### `ovbr` — Standalone brainstorming → spec

Turns a vague idea into a written spec document, then stops. No auto-chaining to implementation planning, no surprise next steps. You get the spec; you decide what to do with it.

**Install:**

```bash
npx skills add overdev-l/overdev-skills --skill ovbr
```

This drops the skill into `~/.claude/skills/ovbr/`. To uninstall:

```bash
rm -rf ~/.claude/skills/ovbr
```

**What it does:**

- Asks one question at a time to clarify your idea
- Proposes 2–3 approaches with tradeoffs and a recommendation
- Presents the design in sections for your approval
- Writes the final spec to `.plan/YYYY-MM-DD-<topic>-design.md` and commits it
- **Stops there.** Hands the spec path back and ends the turn

**Directory layout:**

- `.plan/` — active specs (in progress or pending implementation)
- `.plan/archive/` — completed specs. Move a spec here once the work it describes has shipped, so `.plan/` only reflects open work.

**When to use:**

When you want to explore an idea before writing any code, and want a written spec out the other end without the assistant immediately running off to implement it.

## Credits

The `ovbr` skill is extracted from [obra/superpowers](https://github.com/obra/superpowers) (MIT licensed) and modified to:

- Stop after delivering the spec — no auto-chaining to `writing-plans` or any other skill
- Remove cross-skill dependencies that don't exist outside the full Superpowers plugin
- Rename to `ovbr` to avoid confusion with the original `brainstorming` skill

Original author: Jesse Vincent ([@obra](https://github.com/obra)). The Superpowers methodology this skill comes from is documented in his [original release announcement](https://blog.fsck.com/2025/10/09/superpowers/).

## License

MIT — see [LICENSE](./LICENSE).
