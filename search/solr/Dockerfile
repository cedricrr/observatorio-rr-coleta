FROM solr:9

# ICUFoldingFilter (busca acento-insensível) vem do módulo analysis-extras
ENV SOLR_MODULES=analysis-extras
ENV SOLR_HEAP=512m

COPY configset/diarios /opt/solr/server/solr/configsets/diarios
COPY --chmod=755 railway-entrypoint.sh /railway-entrypoint.sh

CMD ["bash", "/railway-entrypoint.sh"]
