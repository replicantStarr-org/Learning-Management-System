FROM nginx:1.27-alpine

COPY access/frontend/index.html /usr/share/nginx/html/index.html
COPY access/frontend/login.html /usr/share/nginx/html/login.html
COPY access/frontend/register.html /usr/share/nginx/html/register.html
COPY access/frontend/app.js /usr/share/nginx/html/app.js
COPY access/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets

EXPOSE 3000
