# syntax=docker/dockerfile:1.7
#
# Go Daily admin web image. Build from the repository root (pnpm workspace):
#   docker build -f apps/admin-web/Dockerfile .
#
# Behind a TLS-intercepting proxy, add: --secret id=extra_ca,src=/path/to/ca.pem

ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS base
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH" NEXT_TELEMETRY_DISABLED=1
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm install -g pnpm@10.28.0
WORKDIR /repo

FROM base AS deps
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/admin-web/package.json apps/admin-web/
COPY packages/config/package.json packages/config/
COPY packages/shared/package.json packages/shared/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    pnpm install --frozen-lockfile --filter "admin-web..."

FROM deps AS build
COPY packages packages
COPY apps/admin-web apps/admin-web
RUN pnpm --filter admin-web build

FROM node:${NODE_VERSION}-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S -g 10001 godaily && adduser -S -u 10001 -G godaily godaily
COPY --from=build --chown=godaily:godaily /repo/apps/admin-web/.next/standalone ./
COPY --from=build --chown=godaily:godaily /repo/apps/admin-web/.next/static ./apps/admin-web/.next/static
COPY --from=build --chown=godaily:godaily /repo/apps/admin-web/public ./apps/admin-web/public
USER godaily
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:3000/healthz || exit 1
CMD ["node", "apps/admin-web/server.js"]
