# Brasaland Digital frontends (CONTEXT.md: Marketing public site + staff backoffice).
# Official Node image on Alpine. Website and backoffice dependencies install separately.
# Build from this folder: docker build -t brasaland-uis .

FROM node:22-alpine

WORKDIR /uis

# uis/website — Camila Ospina / public corporate site (Vite + React)
COPY website/package.json website/package-lock.json ./website/
RUN npm ci --prefix /uis/website

# uis/backoffice — Operations/Executive staff console (Vite + React, JWT, COP/USD locations)
COPY backoffice/package.json backoffice/package-lock.json ./backoffice/
RUN npm ci --prefix /uis/backoffice

COPY website ./website
COPY backoffice ./backoffice

EXPOSE 5173 5174

WORKDIR /uis/website
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
