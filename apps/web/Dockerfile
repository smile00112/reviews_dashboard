FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# next.config.ts bakes its rewrites into routes-manifest.json at build time, so
# the /api/* proxy target has to be known here — a runtime env var is ignored.
ARG API_PROXY_URL
ENV API_PROXY_URL=$API_PROXY_URL
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
