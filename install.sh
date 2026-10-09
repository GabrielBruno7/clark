#!/usr/bin/env bash
# Instala o CLARK no usuário atual (~/.local), sem sudo.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
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
