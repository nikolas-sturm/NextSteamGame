FROM node:24-bookworm-slim AS dependencies
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY apps/web ./
COPY schemas /schemas
RUN npm run build

FROM node:24-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN useradd --create-home --uid 10001 nextsteam
COPY --from=builder --chown=nextsteam:nextsteam /app/.next/standalone ./
COPY --from=builder --chown=nextsteam:nextsteam /app/.next/static ./.next/static
COPY --from=builder --chown=nextsteam:nextsteam /app/public ./public
USER nextsteam
EXPOSE 3000
CMD ["node", "server.js"]
