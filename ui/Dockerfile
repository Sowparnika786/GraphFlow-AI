FROM nginx:alpine-slim

COPY nginx.conf /etc/nginx/nginx.conf
COPY src/ /usr/share/nginx/html/

RUN touch /var/run/nginx.pid && \
    chown -R 10001:10001 /var/run/nginx.pid /usr/share/nginx/html /var/cache/nginx /var/log/nginx

USER 10001

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
