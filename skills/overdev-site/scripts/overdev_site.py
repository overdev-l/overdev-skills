#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "https://api.cloudflare.com/client/v4"


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def cf_request(method, path, token, payload=None):
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"Cloudflare API {method} {path} failed: {exc.code} {detail}")
    except urllib.error.URLError as exc:
        fail(f"Cloudflare API {method} {path} failed: {exc}")
    if not data.get("success"):
        fail(f"Cloudflare API {method} {path} failed: {data}")
    return data


def get_zone_id(domain, token):
    zone_id = os.environ.get("CLOUDFLARE_ZONE_ID")
    if zone_id:
        return zone_id
    query = urllib.parse.urlencode({"name": domain})
    data = cf_request("GET", f"/zones?{query}", token)
    zones = data.get("result", [])
    if not zones:
        fail(f"no Cloudflare zone found for {domain}")
    return zones[0]["id"]


def ensure_dns(args, fqdn):
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        fail("CLOUDFLARE_API_TOKEN is required unless --skip-dns is used")

    zone_id = get_zone_id(args.domain, token)
    query = urllib.parse.urlencode({"type": "A", "name": fqdn})
    data = cf_request("GET", f"/zones/{zone_id}/dns_records?{query}", token)
    payload = {
        "type": "A",
        "name": fqdn,
        "content": args.origin_ip,
        "ttl": 1,
        "proxied": args.proxied,
        "comment": "Managed by overdev-site skill",
    }

    records = data.get("result", [])
    if records:
        record_id = records[0]["id"]
        cf_request("PATCH", f"/zones/{zone_id}/dns_records/{record_id}", token, payload)
        print(f"updated Cloudflare DNS: {fqdn} -> {args.origin_ip}")
    else:
        cf_request("POST", f"/zones/{zone_id}/dns_records", token, payload)
        print(f"created Cloudflare DNS: {fqdn} -> {args.origin_ip}")


def normalize_host(name, domain):
    name = name.strip().lower().rstrip(".")
    domain = domain.strip().lower().rstrip(".")
    if name.endswith("." + domain):
        fqdn = name
        subdomain = name[: -(len(domain) + 1)]
    else:
        subdomain = name
        fqdn = f"{subdomain}.{domain}"

    label_re = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
    labels = subdomain.split(".")
    if not labels or any(not label_re.match(label) for label in labels):
        fail("subdomain must contain only DNS labels with lowercase letters, digits, and hyphens")
    return subdomain, fqdn


def site_name_from(subdomain):
    return re.sub(r"[^a-z0-9-]+", "-", subdomain.replace(".", "-")).strip("-")


def remote_script(args, fqdn, site_name):
    upstream = f"http://127.0.0.1:{args.port}"
    cert_name = fqdn.replace(".", "-")
    email = args.email
    cert_commands = ""
    if not args.skip_cert:
        cert_commands = f"""
sudo certbot certonly --webroot -w /opt/1panel/apps/openresty/openresty/root -d {shlex.quote(fqdn)} --cert-name {shlex.quote(cert_name)} --email {shlex.quote(email)} --agree-tos --non-interactive --keep-until-expiring
sudo install -m 644 /etc/letsencrypt/live/{shlex.quote(cert_name)}/fullchain.pem /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl/fullchain.pem
sudo install -m 600 /etc/letsencrypt/live/{shlex.quote(cert_name)}/privkey.pem /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl/privkey.pem
sudo tee /etc/letsencrypt/renewal-hooks/deploy/1panel-{shlex.quote(site_name)}-sync.sh >/dev/null <<'HOOK'
#!/bin/sh
set -eu
if [ "${{RENEWED_LINEAGE:-}}" = "/etc/letsencrypt/live/{cert_name}" ]; then
  install -m 644 "$RENEWED_LINEAGE/fullchain.pem" /opt/1panel/www/sites/{site_name}/ssl/fullchain.pem
  install -m 600 "$RENEWED_LINEAGE/privkey.pem" /opt/1panel/www/sites/{site_name}/ssl/privkey.pem
  docker exec 1Panel-openresty-Ev0T nginx -t && docker exec 1Panel-openresty-Ev0T nginx -s reload
fi
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/1panel-{shlex.quote(site_name)}-sync.sh
"""

    return f"""set -euo pipefail
sudo install -d -m 755 /opt/1panel/www/sites/{shlex.quote(site_name)}/proxy /opt/1panel/www/sites/{shlex.quote(site_name)}/index /opt/1panel/www/sites/{shlex.quote(site_name)}/log /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl
if [ ! -f /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl/fullchain.pem ]; then
  sudo openssl req -x509 -nodes -newkey rsa:2048 -days 3 -subj /CN={shlex.quote(fqdn)} -keyout /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl/privkey.pem -out /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl/fullchain.pem >/dev/null 2>&1
  sudo chmod 600 /opt/1panel/www/sites/{shlex.quote(site_name)}/ssl/privkey.pem
fi

sudo tee /opt/1panel/www/sites/{shlex.quote(site_name)}/proxy/root.conf >/dev/null <<'EOF'
location ^~ / {{
    proxy_pass {upstream};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header REMOTE-HOST $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_http_version 1.1;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_buffering off;
    client_max_body_size 100M;
    add_header X-Cache $upstream_cache_status;
    proxy_ssl_server_name off;
    proxy_ssl_name $proxy_host;
}}
EOF

sudo tee /opt/1panel/www/conf.d/{shlex.quote(site_name)}.conf >/dev/null <<'EOF'
server {{
    listen 80;
    server_name {fqdn};
    client_max_body_size 100M;
    location ^~ /.well-known/acme-challenge {{
        allow all;
        root /usr/share/nginx/html;
    }}
    if ( $uri ~ "^/\\.well-known/.*\\.(php|jsp|py|js|css|lua|ts|go|zip|tar\\.gz|rar|7z|sql|bak)$" ) {{
        return 403;
    }}
    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen 443 ssl;
    server_name {fqdn};
    index index.php index.html index.htm default.php default.htm default.html;
    access_log /www/sites/{site_name}/log/access.log main;
    error_log /www/sites/{site_name}/log/error.log;
    client_max_body_size 100M;
    location ~ ^/(\\.user.ini|\\.htaccess|\\.git|\\.env|\\.svn|\\.project|LICENSE|README.md) {{
        return 404;
    }}
    location ^~ /.well-known/acme-challenge {{
        allow all;
        root /usr/share/nginx/html;
    }}
    if ( $uri ~ "^/\\.well-known/.*\\.(php|jsp|py|js|css|lua|ts|go|zip|tar\\.gz|rar|7z|sql|bak)$" ) {{
        return 403;
    }}
    root /www/sites/{site_name}/index;
    http2 on;
    ssl_certificate /www/sites/{site_name}/ssl/fullchain.pem;
    ssl_certificate_key /www/sites/{site_name}/ssl/privkey.pem;
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA256:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK:!KRB5:!SRP:!CAMELLIA:!SEED;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    error_page 497 https://$host$request_uri;
    proxy_set_header X-Forwarded-Proto https;
    include /www/sites/{site_name}/proxy/*.conf;
}}
EOF

sudo docker exec 1Panel-openresty-Ev0T nginx -t
sudo docker exec 1Panel-openresty-Ev0T nginx -s reload
{cert_commands}
sudo docker exec 1Panel-openresty-Ev0T nginx -t
sudo docker exec 1Panel-openresty-Ev0T nginx -s reload
curl -k -sS -L -o /dev/null -w 'origin_https=%{{http_code}}\\n' --resolve {shlex.quote(fqdn)}:443:127.0.0.1 https://{shlex.quote(fqdn)}/ || true
"""


def configure_origin(args, fqdn, site_name):
    script = remote_script(args, fqdn, site_name)
    if args.dry_run:
        print(script)
        return
    ssh_cmd = ["ssh", "-i", os.path.expanduser(args.ssh_key), "-o", "BatchMode=yes", args.server, "bash -s"]
    print("+ " + " ".join(shlex.quote(part) for part in ssh_cmd))
    subprocess.run(ssh_cmd, input=script, text=True, check=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create Cloudflare DNS and a 1Panel/OpenResty reverse-proxy site for overdev.cn."
    )
    parser.add_argument("host", help="subdomain or full hostname, e.g. n8n or n8n.overdev.cn")
    parser.add_argument("port", type=int, help="local service port on the origin host")
    parser.add_argument("--domain", default="overdev.cn")
    parser.add_argument("--origin-ip", default="161.118.250.139")
    parser.add_argument("--server", default="ubuntu@161.118.250.139")
    parser.add_argument("--ssh-key", default="~/.ssh/oci_company")
    parser.add_argument("--email", default="admin@overdev.cn")
    parser.add_argument("--site-name")
    parser.add_argument("--skip-dns", action="store_true")
    parser.add_argument("--skip-origin", action="store_true")
    parser.add_argument("--skip-cert", action="store_true")
    parser.add_argument("--unproxied", dest="proxied", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(proxied=True)
    return parser.parse_args()


def main():
    args = parse_args()
    if not (1 <= args.port <= 65535):
        fail("port must be between 1 and 65535")

    subdomain, fqdn = normalize_host(args.host, args.domain)
    site_name = args.site_name or site_name_from(subdomain)
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,62}$", site_name):
        fail("site name must be 1-63 characters of lowercase letters, digits, and hyphens")

    print(f"host={fqdn}")
    print(f"site={site_name}")
    print(f"upstream=http://127.0.0.1:{args.port}")

    if not args.skip_dns:
        if args.dry_run:
            print("dry-run: would create/update Cloudflare DNS")
        else:
            ensure_dns(args, fqdn)
    if not args.skip_origin:
        configure_origin(args, fqdn, site_name)


if __name__ == "__main__":
    main()
