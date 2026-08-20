# --- build stage ---
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
# npm install rather than npm ci: the lockfile is written by npm 11 and
# npm 10 inside this image rejects its picomatch dedupe layout
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

# --- serve stage: Caddy serves the SPA and proxies /api to the backend ---
FROM caddy:2-alpine
COPY --from=build /src/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
