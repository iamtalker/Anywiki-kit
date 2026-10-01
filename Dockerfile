# 애니위키 Docker 이미지 (위키 엔진은 이미지에 넣지 않고, 처음 켤 때 받아서 볼륨에 저장)
# PHP 는 DokuWiki·MediaWiki 엔진용(openNAMU·Markdown 만 쓰면 없어도 되지만, 엔진을 바꿀 수 있게 넣어 둔다)
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
      php-cli php-mbstring php-xml php-intl php-sqlite3 php-gd php-curl php-zip \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /kit
COPY . /kit
ENV LISTEN=0.0.0.0:4000 COLOR=#3b5bdb ENGINE=opennamu PYTHONUTF8=1
EXPOSE 4000
VOLUME ["/kit/wikis"]
ENTRYPOINT ["bash", "docker/entrypoint.sh"]
