FROM nginx:1.27-alpine

COPY stefan/frontend/index.html /usr/share/nginx/html/index.html
COPY stefan/frontend/subject-management.html /usr/share/nginx/html/subject-management.html
COPY stefan/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets
