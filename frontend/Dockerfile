# Stage 1 builds the static bundle. The API is called on the same origin (/api).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Stage 2 serves it with nginx (unprivileged) and proxies /api to the backend.
# BACKEND_URL is substituted into the nginx config template when the container starts.
FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV BACKEND_URL=http://backend:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
