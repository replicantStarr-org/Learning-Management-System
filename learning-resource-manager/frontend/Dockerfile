FROM nginx:1.27-alpine

COPY learning-resource-manager/frontend/src /usr/share/nginx/html
COPY learning-resource-manager/frontend/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets
