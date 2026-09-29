# 애니위키 Docker 이미지 (위키 엔진은 이미지에 넣지 않고, 처음 켤 때 받아서 볼륨에 저장)
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /kit
COPY . /kit
ENV LISTEN=0.0.0.0:3000 COLOR=#3b5bdb PYTHONUTF8=1
EXPOSE 3000
VOLUME ["/kit/wiki"]
ENTRYPOINT ["bash", "docker/entrypoint.sh"]
