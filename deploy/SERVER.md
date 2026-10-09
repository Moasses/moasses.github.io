# Running the .eu version on your own server

This puts the Flask site **with the admin panel** online at e.g. `https://moasses.eu`.
Time needed: about an hour the first time. Cost: domain (~€5–10/year) + small VPS (~€4–6/month).

## 1. Get the pieces

1. **Domain** – a `.eu` domain may only be registered by EU residents/citizens (you qualify, living in Berlin).
   Any accredited registrar works (e.g. INWX, Namecheap, Cloudflare, IONOS).
2. **Server** – a small Linux VPS **in the EU** (GDPR), e.g. Hetzner CX22 or Netcup, with **Ubuntu 24.04 LTS**.
   Add your SSH public key while creating it.
3. **DNS** – at your registrar create an `A` record `@ → <server IPv4>` (and `AAAA` for IPv6 if you have one).

## 2. Harden the server (once)

```bash
ssh root@<server-ip>

# updates + automatic security updates
apt update && apt -y full-upgrade && apt -y install unattended-upgrades ufw fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades

# your own user, SSH keys only, no root/password logins
adduser armin && usermod -aG sudo armin
mkdir -p /home/armin/.ssh && cp ~/.ssh/authorized_keys /home/armin/.ssh/ && chown -R armin:armin /home/armin/.ssh
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/; s/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# firewall: only SSH + web
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw enable

# Docker
curl -fsSL https://get.docker.com | sh && usermod -aG docker armin
```

Log out and back in as `armin` (`ssh armin@<server-ip>`).

## 3. Deploy

```bash
git clone https://github.com/<you>/<repo>.git site && cd site/deploy
cp ../.env.example .env
nano .env        # set SECRET_KEY, SITE_URL, DOMAIN, ACME_EMAIL, ADMIN_PATH
docker compose up -d --build
docker compose exec web python manage.py create-admin     # password + 2FA
```

Open `https://<your-domain>` — Caddy fetches the HTTPS certificate automatically on first visit.
The admin panel is at `https://<your-domain><ADMIN_PATH>/`.

## 4. Day-to-day

| Task | Command (in `site/deploy`) |
|---|---|
| Update code | `git pull && docker compose up -d --build` |
| Logs | `docker compose logs -f web` |
| New phone for 2FA | `docker compose exec web python manage.py reset-2fa` |
| Backup content | `docker run --rm -v portfolio_site-data:/d -v $PWD:/b alpine tar czf /b/backup-$(date +%F).tgz -C /d .` |

Content you edit in the admin panel lives in the `site-data` volume (not in git).
To publish the same content on GitHub Pages too: admin → **Download content.json** → replace
`content/content.json` in the repository → commit → the Pages workflow rebuilds.

## 5. Check the result

- <https://securityheaders.com> → should be **A+**
- <https://www.ssllabs.com/ssltest/> → should be **A/A+**
- <https://observatory.mozilla.org> → high score
- <https://hstspreload.org> – only submit once you are sure the domain will always use HTTPS.
