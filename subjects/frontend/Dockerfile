FROM nginx:1.27-alpine

COPY subjects/frontend/index.html /usr/share/nginx/html/index.html
COPY subjects/frontend/navbar.html /usr/share/nginx/html/navbar.html
COPY subjects/frontend/subject.html /usr/share/nginx/html/subject.html
COPY subjects/frontend/create.html /usr/share/nginx/html/create.html
COPY subjects/frontend/edit.html /usr/share/nginx/html/edit.html
COPY subjects/frontend/mcp.html /usr/share/nginx/html/mcp.html
COPY subjects/frontend/app.js /usr/share/nginx/html/app.js
COPY subjects/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets

EXPOSE 3001
