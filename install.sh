#!/usr/bin/env bash
# Instala o CLARK no usuário atual (~/.local), sem sudo.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! python3 - 2>/dev/null <<'PY'
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
import cairo
from gi.repository import Gtk, Vte
PY
then
  echo "Faltam dependências do CLARK (PyGObject, GTK 3, VTE ou Cairo). No Ubuntu/Debian:" >&2
  echo "  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-vte-2.91" >&2
  exit 1
fi
if ! command -v claude >/dev/null && [ ! -x "$HOME/.local/bin/claude" ] && [ ! -x "$HOME/.claude/local/claude" ]; then
  echo "Aviso: o Claude Code (comando 'claude') não foi encontrado. O CLARK instala, mas precisa dele para abrir agentes." >&2
  echo "  https://docs.claude.com/en/docs/claude-code" >&2
fi

ICONS="$HOME/.local/share/icons/hicolor"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
chmod +x "$DIR/clark.py"
ln -sf "$DIR/clark.py" "$HOME/.local/bin/clark"
for SZ in 32 48 64 128 256 512; do
  mkdir -p "$ICONS/${SZ}x${SZ}/apps"
  python3 "$DIR/clark.py" --export-icon "$ICONS/${SZ}x${SZ}/apps/clark.png" --icon-size "$SZ"
done
cat > "$HOME/.local/share/applications/clark.desktop" <<DESKTOP
[Desktop Entry]
Name=Clark
Comment=Vários agentes Claude Code numa janela retrô
Exec=$HOME/.local/bin/clark
Icon=clark
Terminal=false
Type=Application
Categories=Development;
StartupWMClass=clark
DESKTOP
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "CLARK instalado! Rode 'clark' no terminal ou procure 'Clark' no menu de aplicativos."
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *)
    echo "Aviso: ~/.local/bin não está no seu PATH, então o comando 'clark' não vai ser encontrado." >&2
    echo "  Adicione ao ~/.zshrc ou ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2
    echo "  Ou rode direto: ~/.local/bin/clark" >&2
    ;;
esac
