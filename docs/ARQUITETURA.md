# Arquitetura

O servidor hospeda o painel de controle; os futuros clientes executarão seu
próprio Linux localmente. RDP/Citrix acessam servidores de sessões existentes.
Não é VDI hospedado nesta VM e não cria licenças RDS/Citrix.

| Componente | Execução e função |
|---|---|
| nginx | TLS na porta 8443, proxy para loopback |
| Painel Python | Usuário freethinclint; perfil, wallpaper e pedidos de update |
| SQLite | Estado persistente e histórico administrativo |
| Atualizador Python | root, timer a cada 15 s; um processo por vez via flock |
| GitHub | Fonte das releases e código; público ou privado com token |
| Windows DHCP | Continua fornecendo endereços; não é modificado nesta versão |

| Caminho | Proprietário / finalidade |
|---|---|
| `/opt/freethinclint/releases` | root; código de cada versão |
| `/opt/freethinclint/current` | root; link para versão ativa |
| `/opt/freethinclint/pending-update.json` | root; journal de recuperação |
| `/etc/freethinclint/panel.json` | root:freethinclint 0640; hash administrativo |
| `/etc/freethinclint/update.json` | root:root 0600; repositório e token |
| `/etc/freethinclint/release-public.pem` | Chave pública fixada localmente |
| `/root/freethinclint-signing` | root 0700; chave privada de publicação |
| `/var/lib/freethinclint` | Usuário web; SQLite, wallpaper e fila de pedidos |
| `/var/lib/freethinclint-update` | root; resultado de updates, legível pelo painel |
| `/var/backups/freethinclint` | root 0700; snapshots antes dos updates |

A página não executa apt, git pull ou comandos arbitrários. O botão de update
cria um pedido JSON completo com hard link atômico, e o worker root verifica
novamente a release no momento da aplicação. Não confia no resultado da consulta
anterior ou em um checksum recebido pelo navegador.

O perfil global contém nome de organização/grupo, URLs, destino e domínio RDP e
preferência de bloqueio do wallpaper. A imagem fica fora do código, e a troca
de release preserva esses dados. Ainda não existe API de agentes ou inventário.

O número de 50+ PCs é objetivo de implantação. O painel não tem uma trava por
quantidade, mas nenhuma capacidade de frota ou tempestade de boot foi medida.
