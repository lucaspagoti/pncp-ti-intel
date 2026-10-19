#!/usr/bin/env bash
# Bibliotecas e fontes do Chromium do Playwright sem sudo (homelab; o CI usa `--with-deps`).
# Baixa os .deb com `apt-get download`, extrai em ~/.cache/pncp-ti/playwright-libs e imprime os
# `export` de LD_LIBRARY_PATH e FONTCONFIG_FILE. Idempotente: só baixa o que faltar.
#
#   eval "$(scripts/playwright_libs.sh)"
set -euo pipefail

DESTINO="${XDG_CACHE_HOME:-$HOME/.cache}/pncp-ti/playwright-libs"
PACOTES=(
    libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 libxcomposite1 libxdamage1
    libxfixes3 libxrandr2 libxrender1 libxi6 libxres1 libgbm1 libasound2t64
    fonts-dejavu-core fonts-crosextra-carlito
)

mkdir -p "$DESTINO/debs" "$DESTINO/raiz"
for pacote in "${PACOTES[@]}"; do
    if ! compgen -G "$DESTINO/debs/${pacote}_*.deb" > /dev/null; then
        (cd "$DESTINO/debs" && apt-get download -q "$pacote" > /dev/null 2>&1) \
            || { echo "falha ao baixar $pacote" >&2; exit 1; }
        dpkg-deb -x "$DESTINO"/debs/"${pacote}"_*.deb "$DESTINO/raiz"
    fi
done

libs="$DESTINO/raiz/usr/lib/x86_64-linux-gnu"
cat > "$DESTINO/fonts.conf" <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>$DESTINO/raiz/usr/share/fonts</dir>
  <dir>/usr/share/fonts</dir>
  <cachedir>$DESTINO/fontcache</cachedir>
</fontconfig>
EOF

# Confere que o Chromium headless resolve todas as bibliotecas.
navegador=$(find "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" \
    -name chrome-headless-shell -type f 2> /dev/null | head -1)
if [[ -n $navegador ]]; then
    faltam=$(LD_LIBRARY_PATH="$libs" ldd "$navegador" | grep 'not found' || true)
    [[ -z $faltam ]] || { echo "bibliotecas ainda ausentes:" >&2; echo "$faltam" >&2; exit 1; }
fi

printf 'export LD_LIBRARY_PATH=%q\n' "$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
printf 'export FONTCONFIG_FILE=%q\n' "$DESTINO/fonts.conf"
