FROM node:alpine
WORKDIR /app
COPY web/package*.json ./web/
RUN cd web && npm install
COPY backoffice/package*.json ./backoffice/
RUN if [ -f backoffice/package.json ]; then cd backoffice && npm install; fi
COPY . .
RUN chmod +x /app/start.sh
EXPOSE 3000
EXPOSE 3001
CMD ["/app/start.sh"]
