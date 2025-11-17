FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY packages/recozik-webui/package*.json ./
RUN npm ci
COPY packages/recozik-webui/src ./src
COPY packages/recozik-webui/public ./public
COPY packages/recozik-webui/next.config.mjs ./
COPY packages/recozik-webui/tsconfig.json ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    chown -R nextjs:nodejs /app
COPY packages/recozik-webui/package*.json ./
RUN npm ci --omit=dev
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/next.config.mjs ./next.config.mjs
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/', (res) => process.exit(res.statusCode === 200 ? 0 : 1))"
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
