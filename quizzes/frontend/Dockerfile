FROM nginx:1.27-alpine

COPY quizzes/frontend/index.html /usr/share/nginx/html/index.html
COPY quizzes/frontend/navbar.html /usr/share/nginx/html/navbar.html
COPY quizzes/frontend/quiz.html /usr/share/nginx/html/quiz.html
COPY quizzes/frontend/create.html /usr/share/nginx/html/create.html
COPY quizzes/frontend/generate.html /usr/share/nginx/html/generate.html
COPY quizzes/frontend/edit.html /usr/share/nginx/html/edit.html
COPY quizzes/frontend/app.js /usr/share/nginx/html/app.js
COPY quizzes/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets

EXPOSE 3004
