# Brasaland Digital frontends (CONTEXT.md: Marketing public site + staff backoffice).
# Official Node image on Alpine. Website and backoffice dependencies install separately.
# Default CMD runs start.sh, which starts both Next.js apps (website:3000, backoffice:3001).
# Build from this folder: docker build -t brasaland-uis .

# Never bake GROQ_API_KEY, JWT_SECRET_KEY, or passwords into this image.
# Pass secrets at runtime from root .env (gitignored) via Compose env_file.

FROM node:22-alpine

WORKDIR /uis

ENV NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0

# uis/website — Camila Ospina / public corporate site (Next.js)
COPY website/package.json website/package-lock.json ./website/
RUN npm ci --prefix /uis/website

# uis/backoffice — Operations/Executive staff console (Next.js, JWT, COP/USD locations)
COPY backoffice/package.json backoffice/package-lock.json ./backoffice/
RUN npm ci --prefix /uis/backoffice

COPY website ./website
COPY backoffice ./backoffice
COPY start.sh /uis/start.sh
RUN chmod +x /uis/start.sh \
    && npm run build --prefix /uis/website \
    && npm run build --prefix /uis/backoffice

ENV NODE_ENV=production

EXPOSE 3000 3001

CMD ["./start.sh"]
