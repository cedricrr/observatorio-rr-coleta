FROM solr:9

# ICUFoldingFilter (busca acento-insensível) vem do módulo analysis-extras
ENV SOLR_MODULES=analysis-extras
ENV SOLR_HEAP=512m

COPY configset/diarios /opt/solr/server/solr/configsets/diarios

CMD ["solr-precreate", "diarios", "/opt/solr/server/solr/configsets/diarios"]
