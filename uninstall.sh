#!/usr/bin/env bash
# Remove o que o install.sh criou. A pasta do repositório e a config (~/.config/clark) ficam.
set -e
ICONS="$HOME/.local/share/icons/hicolor"
rm -f "$HOME/.local/bin/clark" "$HOME/.local/share/applications/clark.desktop"
for SZ in 32 48 64 128 256 512; do
  rm -f "$ICONS/${SZ}x${SZ}/apps/clark.png"
done
gtk-update-icon-cache -q "$ICONS" 2>/dev/null || true
update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "CLARK removido. Para apagar também as configurações: rm -rf ~/.config/clark"
