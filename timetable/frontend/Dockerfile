FROM nginx:1.27-alpine

COPY timetable/frontend/index.html /usr/share/nginx/html/index.html
COPY timetable/frontend/navbar.html /usr/share/nginx/html/navbar.html
COPY timetable/frontend/create.html /usr/share/nginx/html/create.html
COPY timetable/frontend/edit.html /usr/share/nginx/html/edit.html
COPY timetable/frontend/app.js /usr/share/nginx/html/app.js
COPY timetable/frontend/calendar.css /usr/share/nginx/html/calendar.css
COPY timetable/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared/assets /usr/share/nginx/html/assets

EXPOSE 3005
