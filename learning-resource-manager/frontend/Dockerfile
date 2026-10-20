FROM nginx:1.27-alpine

COPY learning-resource-manager/frontend/src /usr/share/nginx/html
# The pages sit at the frontend root and are served from the web root beside src/.
COPY learning-resource-manager/frontend/index.html \
     learning-resource-manager/frontend/multi-agent.html \
     learning-resource-manager/frontend/multi-agent.js \
     /usr/share/nginx/html/
COPY learning-resource-manager/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets
# Keep seeds outside /content: the cloud EmptyDir mount hides image files there.
COPY learning-resource-manager/content/pdf/ /opt/resource-seed/pdf/
COPY learning-resource-manager/frontend/docker-entrypoint.d/40-seed-content.sh /docker-entrypoint.d/40-seed-content.sh
RUN chmod +x /docker-entrypoint.d/40-seed-content.sh
