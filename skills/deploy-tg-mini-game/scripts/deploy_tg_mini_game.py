#!/usr/bin/env python3
"""Deploy a tg-mini-game-factory style app to Cloudflare Workers."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


RUNTIME_SECRETS = ("TELEGRAM_BOT_TOKEN", "SUPABASE_URL")
SUPABASE_KEY_NAMES = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY")
SDK_SCRIPTS = (
    "https://telegram.org/js/telegram-web-app.js",
    "https://sad.adsgram.ai/js/sad.min.js",
)


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).expanduser().resolve()
    api_dir = repo / "apps" / "api"
    game_dir = repo / "apps" / "game"

    require_file(repo / "package.json", "repo package.json")
    require_file(api_dir / "wrangler.jsonc", "apps/api/wrangler.jsonc")
    require_file(game_dir / "index.html", "apps/game/index.html")

    env = os.environ.copy()
    for env_file in env_files(args, repo):
        load_env_file(env_file, env)

    if args.api_base_url is not None:
        env["VITE_API_BASE_URL"] = args.api_base_url
    else:
        env["VITE_API_BASE_URL"] = ""

    require_env(env, "CLOUDFLARE_API_TOKEN", skip=args.dry_run)
    if not env.get("CLOUDFLARE_ACCOUNT_ID") and not args.dry_run:
        print("warn: CLOUDFLARE_ACCOUNT_ID is not set; Wrangler may still work, but setting it is recommended.")

    require_env(env, "VITE_ADSGRAM_BLOCK_ID", skip=args.skip_ads_check)
    for name in RUNTIME_SECRETS:
        require_env(env, name, skip=args.dry_run)
    if not any(env.get(name) for name in SUPABASE_KEY_NAMES) and not args.dry_run:
        fail("missing SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY")

    warn_if_dirty(repo, args.allow_dirty)
    ensure_sdk_scripts(game_dir / "index.html", fix=not args.no_fix_sdk_scripts, dry_run=args.dry_run)
    ensure_production_wrangler(api_dir / "wrangler.jsonc")

    if args.apply_supabase_schema:
        apply_supabase_schema(repo, env, dry_run=args.dry_run)

    if not args.skip_supabase_verify:
        verify_supabase_tables(env, dry_run=args.dry_run)

    put_worker_secrets(api_dir, env, dry_run=args.dry_run)

    run(["npm", "run", "typecheck"], cwd=repo, env=env, dry_run=args.dry_run)
    run(["npm", "run", "build"], cwd=repo, env=env, dry_run=args.dry_run)

    deploy_cmd = ["npx", "wrangler", "deploy", "--keep-vars"]
    if args.hostname:
        if args.domain_mode == "custom-domain":
            deploy_cmd.extend(["--domain", args.hostname])
        else:
            deploy_cmd.extend(["--route", f"{args.hostname}/*"])

    deploy_output = run(deploy_cmd, cwd=api_dir, env=env, dry_run=args.dry_run, capture=True)
    public_url = infer_public_url(deploy_output, args.hostname)

    if public_url and not args.skip_verify:
        verify_public_url(public_url, dry_run=args.dry_run)

    print()
    print("deploy summary")
    print(f"- repo: {repo}")
    print(f"- worker: {worker_name(api_dir / 'wrangler.jsonc')}")
    print(f"- url: {public_url or '(see Wrangler output)'}")
    if args.dry_run:
        print("- mode: dry run, no remote changes were made")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path to the tg-mini-game-factory repository.")
    parser.add_argument("--env-file", action="append", default=[], help="Production env file. Can be passed more than once.")
    parser.add_argument("--hostname", help="Custom production hostname, e.g. game.overdev.cn.")
    parser.add_argument("--domain-mode", choices=("custom-domain", "route"), default="custom-domain")
    parser.add_argument("--api-base-url", help="Production API base URL. Defaults to empty string for same-origin API calls.")
    parser.add_argument("--apply-supabase-schema", action="store_true", help="Run supabase/schema.sql with psql and SUPABASE_DB_URL.")
    parser.add_argument("--skip-supabase-verify", action="store_true")
    parser.add_argument("--skip-ads-check", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--no-fix-sdk-scripts", action="store_true", help="Fail instead of inserting Telegram/AdsGram scripts.")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow deployment with uncommitted changes.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def env_files(args: argparse.Namespace, repo: pathlib.Path) -> list[pathlib.Path]:
    files = [pathlib.Path(path).expanduser().resolve() for path in args.env_file]
    default_prod = repo / ".env.production"
    if not files and default_prod.exists():
        files.append(default_prod)
    return files


def load_env_file(path: pathlib.Path, env: dict[str, str]) -> None:
    require_file(path, f"env file {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            env[key] = value


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.exists():
        fail(f"missing {label}: {path}")


def require_env(env: dict[str, str], key: str, skip: bool = False) -> None:
    if skip:
        return
    value = env.get(key)
    if value is None or value == "":
        fail(f"missing required env var: {key}")


def warn_if_dirty(repo: pathlib.Path, allow_dirty: bool) -> None:
    result = subprocess.run(["git", "status", "--short"], cwd=repo, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return
    dirty = result.stdout.strip()
    if dirty and not allow_dirty:
        fail("git worktree has uncommitted changes. Commit/stash them or rerun with --allow-dirty.")
    if dirty:
        print("warn: deploying with uncommitted changes:")
        print(dirty)


def ensure_sdk_scripts(index_html: pathlib.Path, fix: bool, dry_run: bool) -> None:
    html = index_html.read_text()
    missing = [src for src in SDK_SCRIPTS if src not in html]
    if not missing:
        return
    if not fix:
        fail("missing browser SDK scripts in apps/game/index.html: " + ", ".join(missing))
    insert = "\n".join(f'    <script src="{src}"></script>' for src in missing)
    if "</head>" not in html:
        fail("apps/game/index.html has no </head>; cannot insert SDK scripts")
    next_html = html.replace("  </head>", f"{insert}\n  </head>", 1)
    if dry_run:
        print("dry-run: would insert SDK scripts into apps/game/index.html")
        return
    index_html.write_text(next_html)
    print("updated apps/game/index.html with Telegram/AdsGram SDK scripts")


def ensure_production_wrangler(config_path: pathlib.Path) -> None:
    text = config_path.read_text()
    if '"ALLOW_DEV_AUTH": "true"' in text:
        fail("wrangler.jsonc sets ALLOW_DEV_AUTH=true; production must keep it false")


def apply_supabase_schema(repo: pathlib.Path, env: dict[str, str], dry_run: bool) -> None:
    schema = repo / "supabase" / "schema.sql"
    require_file(schema, "supabase/schema.sql")
    db_url = env.get("SUPABASE_DB_URL")
    if not db_url:
        fail("SUPABASE_DB_URL is required for --apply-supabase-schema")
    if not shutil.which("psql"):
        fail("psql is required for --apply-supabase-schema")
    run(["psql", db_url, "-v", "ON_ERROR_STOP=1", "-f", str(schema)], cwd=repo, env=env, dry_run=dry_run, redact=[db_url])


def verify_supabase_tables(env: dict[str, str], dry_run: bool) -> None:
    if dry_run:
        print("dry-run: would verify Supabase scores/ad_events tables")
        return
    url = env.get("SUPABASE_URL", "").rstrip("/")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        return
    for table in ("scores", "ad_events"):
        request = urllib.request.Request(
            f"{url}/rest/v1/{table}?select=*&limit=1",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status >= 400:
                    fail(f"Supabase table verification failed for {table}: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            fail(f"Supabase table verification failed for {table}: HTTP {exc.code}. Apply supabase/schema.sql first.")
        except urllib.error.URLError as exc:
            fail(f"Supabase verification failed: {exc.reason}")


def put_worker_secrets(api_dir: pathlib.Path, env: dict[str, str], dry_run: bool) -> None:
    names = ["TELEGRAM_BOT_TOKEN", "SUPABASE_URL"]
    names.append("SUPABASE_SERVICE_ROLE_KEY" if env.get("SUPABASE_SERVICE_ROLE_KEY") else "SUPABASE_SECRET_KEY")
    for name in names:
        value = env.get(name, "")
        if not value:
            continue
        if dry_run:
            print(f"dry-run: would set Wrangler secret {name}")
            continue
        print(f"setting Wrangler secret {name}")
        run(["npx", "wrangler", "secret", "put", name], cwd=api_dir, env=env, input_text=value + "\n", capture=True)


def run(
    cmd: list[str],
    cwd: pathlib.Path,
    env: dict[str, str],
    dry_run: bool = False,
    input_text: str | None = None,
    capture: bool = False,
    redact: list[str] | None = None,
) -> str:
    display = " ".join(cmd)
    for secret in redact or []:
        display = display.replace(secret, "***")
    if input_text is not None:
        display += " < stdin"
    print(f"$ {display}")
    if dry_run:
        return ""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=capture,
        check=False,
    )
    if capture:
        output = (result.stdout or "") + (result.stderr or "")
        print(output, end="" if output.endswith("\n") else "\n")
    if result.returncode != 0:
        fail(f"command failed ({result.returncode}): {display}")
    return (result.stdout or "") + (result.stderr or "")


def infer_public_url(output: str, hostname: str | None) -> str | None:
    if hostname:
        return f"https://{hostname}"
    match = re.search(r"https://[A-Za-z0-9_.-]+\\.workers\\.dev", output)
    return match.group(0) if match else None


def verify_public_url(public_url: str, dry_run: bool) -> None:
    health_url = public_url.rstrip("/") + "/health"
    if dry_run:
        print(f"dry-run: would verify {health_url}")
        return
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(health_url, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                if data.get("ok") is not True:
                    fail(f"{health_url} did not return ok=true: {body}")
                if data.get("storage") != "supabase":
                    fail(f"{health_url} is reachable but storage={data.get('storage')!r}; production should use supabase")
                print(f"verified {health_url}")
                return
        except Exception as exc:  # noqa: BLE001 - print retry context for deployment propagation.
            if attempt == 5:
                fail(f"failed to verify {health_url}: {exc}")
            time.sleep(3)


def worker_name(config_path: pathlib.Path) -> str:
    text = re.sub(r"//.*", "", config_path.read_text())
    try:
        return json.loads(text).get("name", "(unknown)")
    except json.JSONDecodeError:
        match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
        return match.group(1) if match else "(unknown)"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
