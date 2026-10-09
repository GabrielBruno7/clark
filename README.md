# CLARK

Launcher retrô em pixel art para rodar vários agentes [Claude Code](https://claude.com/claude-code) ao mesmo tempo, numa única janela.

## Requisitos

- Linux com GTK 3 (testado no Ubuntu 22.04)
- Python 3 com PyGObject, VTE e Cairo
- [Claude Code](https://docs.claude.com/en/docs/claude-code) instalado e logado (`claude` no PATH)

No Ubuntu/Debian:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-vte-2.91
```

## Instalação

```bash
git clone git@github.com:GabrielBruno7/clark.git ~/clark
cd ~/clark
./install.sh
```

O instalador não usa sudo: cria o comando `clark` em `~/.local/bin`, os ícones e o atalho no menu de aplicativos.
Não apague a pasta clonada depois de instalar: o comando `clark` aponta para ela.

## Uso

```bash
clark                 # abre o launcher
clark --no-splash     # pula a tela de abertura
clark --fresh         # começa sem restaurar a sessão anterior
clark -- <args>       # repassa argumentos para cada `claude`
```

## Atualizar

```bash
cd ~/clark && git pull
```
