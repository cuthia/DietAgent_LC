FROM node:20-alpine

WORKDIR /app

COPY frontend/package.json ./
COPY frontend/server.js ./
COPY frontend/index.html ./
COPY frontend/app.js ./

EXPOSE 8501

CMD ["node", "server.js"]
