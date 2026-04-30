FROM node:24-slim AS deps
WORKDIR /srv/dashboard
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /srv/dashboard
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /srv/dashboard/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-slim AS runtime
WORKDIR /srv/dashboard
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system switch && adduser --system --ingroup switch switch

COPY --from=builder /srv/dashboard/.next/standalone ./
COPY --from=builder /srv/dashboard/.next/static ./.next/static
COPY --from=builder /srv/dashboard/public ./public

USER switch

EXPOSE 3000

CMD ["node", "server.js"]
