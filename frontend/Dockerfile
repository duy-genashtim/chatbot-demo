# ----------------------------------------------------------------
# Stage 1: deps — install node_modules only (cache layer)
# ----------------------------------------------------------------
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# ----------------------------------------------------------------
# Stage 2: builder — full build with Next.js standalone output
# ----------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build args for NEXT_PUBLIC_ vars baked at image build time
ARG NEXT_PUBLIC_API_URL=https://chat.example.com/api
ARG NEXT_PUBLIC_BRAND_NAME=G-HelpDesk
ARG NEXT_PUBLIC_BRAND_COLOR=#253956

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_BRAND_NAME=$NEXT_PUBLIC_BRAND_NAME
ENV NEXT_PUBLIC_BRAND_COLOR=$NEXT_PUBLIC_BRAND_COLOR
ENV NEXT_TELEMETRY_DISABLED=1

# Relies on output: 'standalone' in next.config.ts (set in phase 01)
RUN npm run build

# ----------------------------------------------------------------
# Stage 3: runtime — minimal image, non-root user
# ----------------------------------------------------------------
FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Non-root user (uid 1001 to avoid collision with appuser uid 1000 on backend)
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone build artifacts
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
