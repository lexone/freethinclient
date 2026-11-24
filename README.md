# FreeThinClient

Painel de administração para um ambiente de thin clients Linux iniciado por PXE,
com Chrome, Citrix Workspace e RDP. Servidor em VM VMware, DHCP existente no Windows Server.

**Estado: 0.1.0, piloto do plano de controle.** Esta versão instala o painel,
salva um perfil global e o wallpaper, e implementa atualizações assinadas.
Ela **ainda não gera a imagem Linux dos clientes, ativa PXE nem distribui configurações**.
Não é uma instalação do produto openthinclient e não tem vínculo com ele.

## Instalação no servidor

Ubuntu Server **24.04 LTS amd64** novo; ponto de partida do piloto:
4 vCPU, 8 GB RAM e 100 GB de disco. A capacidade de 50+ clientes depende do
teste de boot simultâneo e do futuro mecanismo de distribuição da imagem.

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/lexone/freethinclient.git
cd freethinclient
sudo bash install.sh --server-name IP_OU_DNS_DA_VM
```

Substitua `IP_OU_DNS_DA_VM` pelo endereço atual. Revise o código antes de executar
com sudo. A senha aleatória do usuário `admin` aparece uma única vez no terminal.
Abra **https://IP_OU_DNS_DA_VM:8443**. O instalador cria certificado local;
valide a impressão digital no console e substitua pela CA da empresa em produção.

O script instala dependências, usuário sem shell, serviços systemd, nginx/TLS,
SQLite e o verificador de updates. Não muda IP, VLAN, DHCP, firewall ou PXE.
Uma segunda execução preserva a instalação existente e não redefine senhas.

## O que funciona nesta versão

- Login administrativo, hash scrypt, sessão com validade de uma hora e CSRF.
- Perfil global: organização, nome do grupo, Chrome, URL Citrix e destino RDP.
- Upload de wallpaper PNG/JPEG de até 5 MB e prévia autenticada.
- Consulta de releases estáveis GitHub; token opcional para repositório privado.
- Update pelo painel com assinatura RSA/SHA-256, hash/tamanho do pacote,
  compatibilidade, backup SQLite, troca de diretório e teste de saúde.
- Rollback automático e recuperação de transação pendente após reinício.
- Registro de alterações administrativas e status persistido do atualizador.

Não há máquinas fictícias cadastradas. Os campos do perfil ficam armazenados
para a futura integração com os clientes; não alteram sessões Windows ou Citrix.

## Próxima etapa: piloto PXE

Precisaremos de IP definitivo, sub-rede/VLAN, versão do Windows DHCP, existência
de WDS/SCCM, um PC de teste e informação BIOS/UEFI/Secure Boot.
A imagem dos clientes deverá incluir desktop leve, Chrome, cliente RDP e o
instalador Citrix obtido conforme a licença do fabricante. Multi-grupos,
enrollment de clientes, aplicação do wallpaper e comandos remotos ainda não
foram implementados. Veja [plano PXE](docs/PXE.md).

## Documentação

| Documento | Conteúdo |
|---|---|
| [Arquitetura](docs/ARQUITETURA.md) | Componentes, permissões e diretórios |
| [Atualizações](docs/ATUALIZACOES.md) | Chaves, releases, validação, rollback |
| [Operação](docs/OPERACAO.md) | Instalação, troca de endereço, backup, recuperação |
| [PXE](docs/PXE.md) | Integração planejada com Windows DHCP |
| [Validação](docs/VALIDACAO.md) | Testes automatizados e homologação na VM |
| [Segurança](SECURITY.md) | Limites, credenciais e modelo de confiança |
| [Changelog](CHANGELOG.md) | Histórico de versões |

## Desenvolvimento

Python 3.11+ para testes; Python 3.12 do Ubuntu 24.04 no servidor. Sem pip ou
dependências Python externas. OpenSSL é necessário para assinatura/verificação.

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
node --check web/app.js
```

O CI inclui teste do instalador em contêiner systemd descartável. O teste em
VMware e em hardware PXE real continua necessário antes de produção.
