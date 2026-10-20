FROM nginx:1.28-alpine
COPY cloud/edge/default.conf.template /etc/nginx/templates/default.conf.template
COPY cloud/edge/15-auth.sh /docker-entrypoint.d/15-auth.sh
RUN chmod 755 /docker-entrypoint.d/15-auth.sh
ENV FRONTEND_PORT=3001
EXPOSE 8080
