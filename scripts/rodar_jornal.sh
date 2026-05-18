#!/bin/bash
# Wrapper para o orquestrador jornal_diario, chamado pelo launchd 2x/dia.
# Faz cd para o project root, roda o python, captura exit code e loga
# com timestamp em /tmp/observatorio-roraima/jornal.log.

set -u

PROJECT_ROOT="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
OUTPUT_DIR="/tmp/observatorio-roraima"
LOG_FILE="$OUTPUT_DIR/jornal.log"

mkdir -p "$OUTPUT_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

cd "$PROJECT_ROOT" || { log "ERRO: cd para $PROJECT_ROOT falhou"; exit 2; }

log "===== Rodada iniciada ====="
log "PROJECT_ROOT=$PROJECT_ROOT"
log "PYTHON_BIN=$PYTHON_BIN"

"$PYTHON_BIN" -m scripts.jornal_diario \
    --data hoje \
    --fonte todas \
    --output "$OUTPUT_DIR" \
    >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "Geração concluída. Iniciando publicação no R2..."
    "$PYTHON_BIN" -m scripts.publicar --data hoje >> "$LOG_FILE" 2>&1
    PUB_EXIT=$?
    if [ $PUB_EXIT -eq 0 ]; then
        log "Publicação concluída (exit=0)"
    else
        log "Publicação falhou (exit=$PUB_EXIT)"
        EXIT_CODE=$PUB_EXIT
    fi
fi

if [ $EXIT_CODE -eq 0 ]; then
    log "Rodada concluída com sucesso (exit=0)"
else
    log "Rodada falhou (exit=$EXIT_CODE)"
fi

exit $EXIT_CODE
