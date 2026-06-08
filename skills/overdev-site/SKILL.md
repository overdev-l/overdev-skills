---
name: overdev-site
description: Use when deploying an overdev.cn service that needs automatic Cloudflare DNS plus a 1Panel/OpenResty reverse-proxy site. Handles subdomain creation, Cloudflare proxied A records, local-port reverse proxy binding, Let's Encrypt certificates, and verification for services on the overdev OCI host.
---

# Overdev Site

Create an `overdev.cn` application entrypoint from a local service port.

Use this skill when the user asks to publish a service such as `n8n.overdev.cn`, `dify.overdev.cn`, or another `*.overdev.cn` hostname and bind it to a service running on the overdev OCI host.

## Default Environment

- Domain: `overdev.cn`
- Origin IP: `161.118.250.139`
- SSH target: `ubuntu@161.118.250.139`
- SSH key: `~/.ssh/oci_company`
- 1Panel OpenResty container: `1Panel-openresty-Ev0T`
- 1Panel site config root: `/opt/1panel/www`
- ACME webroot: `/opt/1panel/apps/openresty/openresty/root`

Do not commit or print Cloudflare tokens. Read them from environment variables.

## Required Inputs

- Subdomain, such as `n8n` or full host `n8n.overdev.cn`
- Local port, such as `5678`
- Cloudflare token in `CLOUDFLARE_API_TOKEN`
- Optional zone id in `CLOUDFLARE_ZONE_ID`; if absent, the script looks it up

## Quick Start

Use the bundled script:

```bash
export CLOUDFLARE_API_TOKEN=...
python3 skills/overdev-site/scripts/overdev_site.py n8n 5678
```

This creates or updates:

- Cloudflare DNS record: `n8n.overdev.cn -> 161.118.250.139`, proxied by default
- OpenResty reverse proxy: `https://n8n.overdev.cn -> http://127.0.0.1:5678`
- Let's Encrypt cert copied into `/opt/1panel/www/sites/n8n/ssl/`
- Certbot renewal hook that syncs renewed certs and reloads OpenResty

Run a dry run first when the target port or hostname is uncertain:

```bash
python3 skills/overdev-site/scripts/overdev_site.py n8n 5678 --dry-run
```

## Workflow

1. Confirm the service is already running on the overdev host and which local port it listens on.
2. Run `overdev_site.py <subdomain> <port>`.
3. If certbot fails because DNS was just created, wait for propagation and rerun the same command.
4. Verify public HTTPS with:

```bash
curl -I https://<subdomain>.overdev.cn/
```

5. If the user's local Chrome reports `DNS_PROBE_FINISHED_NXDOMAIN` while public DNS works, treat it as local/company DNS cache and recommend Cloudflare Secure DNS or a temporary `/etc/hosts` entry.

## 1Panel UI Note

The script writes the same OpenResty site files that 1Panel uses under `/opt/1panel/www/sites` and `/opt/1panel/www/conf.d`, then reloads the 1Panel OpenResty container. This reliably publishes the site, but it may not create a first-class website row inside the 1Panel UI database.

If the user explicitly requires the site to appear in the 1Panel UI, inspect the live 1Panel Swagger endpoint for that host and use the official API instead of editing OpenResty files directly.

## Safety

- Never delete existing site directories unless the user explicitly asks.
- Do not overwrite unrelated certs or configs.
- Keep service ports bound to `127.0.0.1` when possible.
- For Cloudflare, use `Full (strict)` SSL/TLS mode on the zone.
- Prefer proxied DNS records unless the user asks to expose the origin directly.
