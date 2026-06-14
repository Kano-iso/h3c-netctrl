# 阶段1: Node.js 构建
FROM node:20-alpine AS build

WORKDIR /app

# 替换为淘宝镜像源加速
RUN npm config set registry https://registry.npmmirror.com/

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# 阶段2: Nginx 运行
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
