# Vite/React apps under uis/ (website + backoffice). Build with APP_DIR.

FROM node:22-alpine

WORKDIR /app

ARG APP_DIR=website
ENV APP_DIR=${APP_DIR}

COPY ${APP_DIR}/package.json ${APP_DIR}/package-lock.json ./
RUN npm ci

COPY ${APP_DIR}/ ./

EXPOSE 5173 5174

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
