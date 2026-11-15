# Frontend image: build the SPA with pnpm, then serve it with Nginx.
#
# A separate build stage keeps Node out of the runtime image: the container that faces the internet
# contains Nginx and static files, nothing else.

FROM node:24-alpine AS build

WORKDIR /app

# Install the exact pnpm the lockfile was produced with. `npm install -g` is used instead of
# `corepack enable` on purpose: corepack's bundled signature verification has needed occasional
# intervention in CI images, while an explicit version is deterministic and fails loudly.
RUN npm install --global pnpm@12.15.0

# Copy manifests first so the dependency layer is cached independently of the source.
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

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