# syntax=docker/dockerfile:1.7

FROM stagex/pallet-nodejs AS build-stage

COPY --from=stagex/user-hugo-extended:0.161.1 /usr/bin/hugo /usr/local/bin/hugo

# Timezone database for Hugo's time.* functions. stagex images ship no
# zoneinfo, and this Hugo binary embeds none, so named zones (e.g.
# America/New_York) fail to resolve. Go reads them from the zip referenced by
# ZONEINFO. Build stage only — absent from the final runtime image.
COPY --from=stagex/core-go /usr/lib/go/lib/time/zoneinfo.zip /zoneinfo.zip
ENV ZONEINFO=/zoneinfo.zip

ARG hugobuildargs
ENV HUGO_BUILD_ARGS=$hugobuildargs

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN hugo ${HUGO_BUILD_ARGS}
RUN npm run build:search

FROM stagex/user-caddy

COPY --from=stagex/core-musl / /
COPY --from=build-stage /app/public /srv

COPY <<'EOF' /etc/caddy/Caddyfile
{
	auto_https off
	admin off
}

:80 {
	root * /srv
	encode gzip zstd

	# Legacy Drupal URL redirects (301). `map` + `redir` are ordered by Caddy
	# ahead of `rewrite`/`file_server`, so matched paths redirect before a 404.
	# redirects.caddy is generated into Hugo's static/, so it ships inside public/
	# (the release artifact) and lands here at /srv/redirects.caddy on build.
	# Regenerate with `just redirects`. See docs/REDIRECTS.md.
	import /srv/redirects.caddy

	# Backward compatibility: /img/* serves from /assets/img/*
	rewrite /img/* /assets{uri}

	file_server
}
EOF

ENV XDG_CONFIG_HOME=/tmp/caddy-config \
    XDG_DATA_HOME=/tmp/caddy-data

EXPOSE 80
ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
