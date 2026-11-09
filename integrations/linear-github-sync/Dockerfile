FROM node:22.16-alpine
WORKDIR /app
COPY package.json ./
COPY src/ ./src/
RUN mkdir -p /app/state && chown -R node:node /app/state
USER node
EXPOSE 3000
CMD ["npm", "start"]
