# FreeThinClient

Gerenciamento de thin clients Linux com painel web em português, grupos,
perfis de inicialização e desktop Blue Workspace.

**Versão 0.2.0 — piloto.** O painel gerencia grupos e dispositivos, e o agente
recebe configurações após aprovação. Há uma receita de imagem Linux e de
publicação PXE; a ISO deve ser gerada em Linux e o boot validado em uma VM/PC.
Ainda não é uma substituição completa do openthinclient.

## Funcionalidades

- Abas: visão geral, máquinas, grupos, imagens/boot, aparência, atualizações e atividade.
- Grupos com desktop, navegador, quiosque, portal Citrix ou RDP.
- Compatibilidade BIOS/UEFI e origem PXE/mídia local por grupo.
- Cadastro por MAC, aprovação, status online e credenciais individuais.
- Reaplicar perfil, reiniciar e desligar através do agente.
- Desktop azul, atalhos próprios, ícones Papirus e wallpaper da organização.
- Build Debian 12 amd64 com XFCE, Chromium e FreeRDP.
- Atualizações do painel assinadas, backup SQLite e rollback automático.

## Instalação do painel

Ubuntu Server **24.04 LTS amd64**. Referência para o piloto: 4 vCPU, 8 GB RAM,
100 GB de disco. O dimensionamento para 50+ clientes depende de homologação.

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/lexone/freethinclient.git
cd freethinclient
sudo bash install.sh --server-name "$(hostname -I | awk '{print $1}')"
```

Confira o endereço detectado em uma VM com várias interfaces. A senha inicial
aleatória do usuário `admin` aparece uma vez no terminal. Acesse
`https://IP_DA_VM:8443`. O instalador cria um certificado local; confira sua
impressão digital no console e use a CA da empresa em produção. Não altera
DHCP, VLAN, PXE ou firewall. Reexecutar o instalador preserva a instalação.

### Atualizar instalação existente

Aplique um checkout revisado com:

```bash
sudo bash scripts/upgrade-local.sh
```

A atualização local preserva a senha, faz backup e testa a saúde do serviço.
Para distribuição regular, use as releases assinadas descritas na documentação.

## Imagem e primeiro cliente

Leia [o guia dos clientes](docs/CLIENTES.md). Ele cobre geração da ISO,
aprovação do primeiro PC, credenciais persistentes ou reconhecimento opcional
por MAC para clientes sem disco, e publicação HTTP/TFTP integrada ao DHCP Windows.

Citrix Workspace precisa ser instalado de fonte oficial na imagem. O build
básico abre o portal Citrix, mas não inclui o pacote ICA. AD/SSO, VNC,
impressoras gerenciadas, Secure Boot e instalação permanente em disco ainda
precisam de implementação/homologação. Não há máquinas fictícias no painel.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Clientes e imagem](docs/CLIENTES.md) | Build, agente, grupos, boot e limitações do piloto |
| [Arquitetura](docs/ARQUITETURA.md) | Componentes e diretórios |
| [Atualizações](docs/ATUALIZACOES.md) | Chaves, releases, validação e rollback |
| [Operação](docs/OPERACAO.md) | Senha, endereço, backup e recuperação |
| [PXE](docs/PXE.md) | Integração com DHCP existente |
| [Segurança](SECURITY.md) | Credenciais e confiança |

## Validação

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh scripts/build-client.sh scripts/setup-boot.sh scripts/upgrade-local.sh
node --check web/app.js
node --check web/fleet.js
```

O CI valida painel, verificação de releases e instalação em contêiner systemd.
Isso não substitui o teste da ISO e do hardware de boot.
