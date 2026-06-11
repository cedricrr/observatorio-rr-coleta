#!/bin/bash
# Volumes do Railway montam como root:root e a imagem do Solr roda como
# uid 8983 — sem isto o Solr não escreve em /var/solr (crash-loop).
# Com RAILWAY_RUN_UID=0 o container inicia como root: ajustamos o dono
# do volume e rebaixamos para o usuário solr (o launcher recusa root).
# Localmente (docker compose, uid 8983) cai direto no exec final.
set -e

if [ "$(id -u)" = "0" ]; then
  chown -R 8983:8983 /var/solr
  exec gosu 8983:8983 solr-precreate diarios /opt/solr/server/solr/configsets/diarios
fi

exec solr-precreate diarios /opt/solr/server/solr/configsets/diarios
