FROM nginx:1.27-alpine

COPY assignments/frontend/index.html /usr/share/nginx/html/index.html
COPY assignments/frontend/navbar.html /usr/share/nginx/html/navbar.html
COPY assignments/frontend/assignment.html /usr/share/nginx/html/assignment.html
COPY assignments/frontend/create.html /usr/share/nginx/html/create.html
COPY assignments/frontend/edit.html /usr/share/nginx/html/edit.html
COPY assignments/frontend/upcoming.html /usr/share/nginx/html/upcoming.html
COPY assignments/frontend/app.js /usr/share/nginx/html/app.js
COPY assignments/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets

EXPOSE 3003
