# Frontend image: build the SPA with pnpm, then serve it with Nginx.
#
# A separate build stage keeps Node out of the runtime image: the container that faces the internet
# contains Nginx and static files, nothing else.

FROM node:24-alpine AS build

WORKDIR /app

# Corepack ships with Node and provides the exact pnpm version declared in package.json.
RUN corepack enable

# Copy manifests first so ``pnpm install`` is cached independently of the source.
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

COPY frontend/ ./

# The SPA calls the API on its own origin, so a relative base path is all it needs.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN pnpm build

FROM nginx:1.27-alpine AS runtime

RUN rm /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/app.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1