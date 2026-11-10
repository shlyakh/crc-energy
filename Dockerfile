# One container serving the static explorer (E8). Build the data first: `just data`.
FROM caddy:2-alpine
COPY site/ /srv/
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
