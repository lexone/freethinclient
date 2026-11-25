## Próxima revisão do piloto

- Reparação das dependências GIO/XDG na imagem e atualização do desktop/barra sem corrida de encerramento.

- Quadro no desktop com nome do painel e IPv4 atual, configurável por grupo e oculto no quiosque.

- Aba Atalhos e ações por grupo com nomes, URLs HTTPS, ícones e visibilidade.
- Ações opcionais de desligar/reiniciar com confirmação configurável e polkit restrito.
- Atalhos web gerenciados são removidos ao desabilitar/excluir e ficam ocultos no quiosque.

- Manutenção de imagem no portal: versões, Linux, Chromium/Chrome, Citrix Workspace e rollback.
- Serviço root separado com ações fixas, staging, publicação versionada e auditoria.
- Atalhos gerenciados recebem o checksum de confiança específico do XFCE.
- Banner de boot FREETHINCLIENT e Copyright © 2026 Everton S Oliveira no initrd.

- Desktop com atalhos selecionáveis, ícones do sistema e barra configuráveis por grupo.
- Quiosque com navegador, portal Citrix ou RDP e opção de tela cheia no navegador.
- Wallpaper e ícones em PNG; fallback de propriedades XFCE e diretório XDG localizado.
- Atualização da imagem PXE existente com backup sem recompilar o Debian.

- Indicador de consulta de máquinas, verificação manual, última resposta e falhas de comunicação.

- Contas individuais no painel: administrador e operador, edição, senha e desativação.
- Preservação do admin instalado e revogação de sessões ao alterar uma conta.
- Auditoria com usuário, IP e filtro; proteção do último administrador ativo.
- Nome da máquina editável junto à aprovação e orientação sobre cadastro após o boot.

## 0.2.0 — piloto Blue Workspace

- Navegação por abas com teclado, histórico e edição preservada.
- Grupos e perfis desktop, navegador, quiosque, Citrix e RDP.
- Aprovação de máquinas, credenciais individuais, heartbeat e comandos com confirmação.
- Recadastro opcional de clientes sem disco pelo MAC em rede de boot confiável.
- Desktop azul e ícones; receita de ISO Debian 12 e publicação PXE.
- Atualização local com backup/rollback e testes de isolamento entre agentes.
- ISO e boot físico ainda precisam ser compilados/homologados no ambiente Linux.

# Histórico

## 0.1.0

- Instalador Ubuntu Server 24.04 amd64 com nginx HTTPS e systemd.
- Painel autenticado, perfil global, upload de wallpaper e auditoria.
- Atualizador privilegiado separado do painel, releases assinadas e rollback.
- Documentação, testes unitários/integrados e workflows de CI/publicação.
- PXE e integração dos clientes ainda pendentes de desenvolvimento e homologação.
