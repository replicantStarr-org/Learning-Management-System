FROM nginx:1.27-alpine

COPY subjects/frontend/index.html /usr/share/nginx/html/index.html
COPY subjects/frontend/subject-management.html /usr/share/nginx/html/subject-management.html
COPY subjects/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets
