FROM node:20-slim AS base

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .

# NEXT_PUBLIC_* variables are inlined into the client bundle at build time,
# not read at container runtime — they must be passed as build args, not
# just `environment:` in docker-compose. See docker-compose.yml.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
