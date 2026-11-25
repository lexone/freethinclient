# FreeThinClient Blue — piloto 0.2

O servidor continua Ubuntu 24.04. A imagem cliente é Debian 12 amd64, criada
com live-build, XFCE, Openbox para quiosque, Chromium, FreeRDP e ícones Papirus.
Não reutiliza nem exige um servidor openthinclient. As funcionalidades foram
usadas como referência, sem copiar o código ou a marca do produto.

## O que esta entrega implementa

- Navegação por abas, teclado e histórico do navegador sem recarregar a página.
- CRUD de grupos com modos desktop, navegador, quiosque, portal Citrix e RDP.
- Origem de boot e compatibilidade BIOS/UEFI separadas do tipo de sessão.
- Registro de dispositivos por MAC, aprovação, associação ao grupo e heartbeat.
- Credencial individual de agente: o banco armazena somente SHA-256 do token.
- Perfil versionado por grupo, papel de parede global e ícones do desktop.
- Fila de reaplicar, reiniciar e desligar; confirmação por identidade de agente.
- Receita de ISO híbrida e arquivos kernel/initrd/SquashFS para PXE.
- Publicação HTTP/TFTP separada do DHCP existente.

Os testes do painel não comprovam boot físico. A ISO só existe depois de um
build bem-sucedido em Linux. Não há ISO pré-compilada neste repositório.

## Atualizar uma VM que já tem o painel

Dentro do checkout da versão a aplicar:

```bash
sudo bash scripts/upgrade-local.sh
```

O script mantém senha e certificado, para o painel, faz backup SQLite, aplica
o checkout, testa `/healthz` e restaura a versão anterior em caso de falha.
Recarregue o navegador com Ctrl+F5. Ele não configura DHCP, boot ou firewall.
Para as atualizações assinadas regulares, continue usando o fluxo de releases.

## Gerar imagem em Linux

Use uma VM de build amd64 Ubuntu/Debian com pelo menos 40 GB livres e acesso
aos repositórios Debian. No Ubuntu, o script prepara um ambiente Debian 12
com debootstrap e executa live-build dentro dele, em um namespace de montagem
privado. O live-build antigo do Ubuntu não é usado e os repositórios do
servidor não são substituídos. Não requer Docker. Em Debian 12, o build é nativo.
Exemplo:

```bash
sudo bash scripts/build-client.sh \
  https://10.9.2.175:8443 \
  /etc/freethinclient/tls.crt \
  /var/tmp/ftc-blue-build-01
```

O último caminho deve ser novo. Se uma tentativa falhou, preserve o diretório
para diagnóstico e escolha outro, por exemplo `/var/tmp/ftc-blue-build-02`. O certificado precisa conter o IP/DNS usado
na URL. A imagem incorpora apenas endereço e CA pública; nunca senha do painel
nem token GitHub. O agente valida HTTPS e rejeita redirecionamentos.

Saída em `output/`:

- `freethinclient-blue-amd64.iso`: para anexar ao CD virtual de uma VM cliente
  ou gravar em pendrive com ferramenta apropriada.
- `vmlinuz`, `initrd.img`, `filesystem.squashfs`: boot de rede.
- `SHA256SUMS`: conferência dos arquivos.

## Primeiro teste com ISO

1. Crie um grupo no painel, por exemplo `Laboratório`, modo `Desktop`.
2. Crie uma VM cliente amd64 com 4 GB de RAM e rede com acesso ao painel.
3. Anexe a ISO, selecione boot por CD e mantenha Secure Boot desligado para
   este piloto. O build não gera uma cadeia assinada para Secure Boot.
4. O desktop inicia como usuário `thinclient`, sem senha utilizável ou sudo.
5. Na aba Máquinas, confira nome/MAC e aprove a solicitação no grupo.
6. Em até cerca de 15 segundos o agente recebe o perfil. Valide navegador,
   atalhos, RDP, modo quiosque e comandos administrativos separadamente.

O MAC precisa ser unicast e único. Um cadastro repetido não substitui a
credencial existente. No piloto, use nomes de host diferentes nos PCs se
quiser distingui-los antes da aprovação; o MAC continua sendo a identificação.

### Persistência da identidade — limitação relevante

O agente guarda sua identidade privada em
`/var/lib/freethinclient-client/identity.json`. Em mídia persistente, preserve
esta pasta. Na ISO/PXE com `nopersistence`, ela fica em RAM.

Para clientes sem disco em uma rede de boot confiável, ative no grupo
**Reconhecer PCs sem disco pelo MAC após reiniciar**. Depois da primeira
aprovação, o servidor permite recadastro pelo MAC somente quando a identidade
anterior está há pelo menos 90 segundos sem heartbeat. Uma credencial nova
substitui a antiga, mantendo o grupo; comandos pendentes são descartados.
O PC pode aguardar esse intervalo depois de um reboot rápido.

Esta opção vem desligada: MAC não é prova criptográfica de identidade e pode
ser falsificado por alguém com acesso à rede. Para ambientes que exigem
identidade forte, use persistência individual de credenciais; TPM e mTLS não
estão implementados. Sem persistência e sem a opção, remova o cadastro antigo
no painel e aprove novamente. Nenhum token comum é incluído na imagem.

## Publicar o boot de rede

No servidor de boot do piloto, com os arquivos do build disponíveis:

```bash
sudo bash scripts/setup-boot.sh /var/tmp/ftc-blue-build-01/output 10.9.2.175
```

O script publica HTTP em TCP 8081 e arquivos iPXE em
`/srv/tftp/freethinclient`. Não altera opções do Windows DHCP, relay ou firewall.
Confira o diretório raiz de um TFTP já existente antes de usar os arquivos.
Os arquivos de imagem são públicos na rede de boot e não incluem credenciais.
Use uma rede de piloto confiável: a entrega HTTP/TFTP desta receita ainda não
autentica os artefatos no próprio cliente e não deve ser exposta à Internet.

No Windows DHCP, faça políticas por arquitetura: BIOS recebe
`freethinclient/undionly.kpxe`; UEFI x64 recebe `freethinclient/ipxe.efi`.
Quando o cliente já identificar a classe de usuário `iPXE`, entregue
`http://10.9.2.175:8081/boot.ipxe`, evitando carregar iPXE novamente em loop.
Se usar VLANs diferentes, o relay/IP helper e a topologia precisam ser
configurados conforme o ambiente. Não aplique uma opção 67 única para BIOS e UEFI.

## Aplicações e restrições

- Chromium é o navegador incluído. Google Chrome pode ser instalado de fonte
  oficial em uma variação da imagem, sem exigir mudança no perfil.
- Citrix abre o portal definido no grupo. Sessões ICA exigem instalar e testar
  Citrix Workspace oficial e sua cadeia de certificados na imagem; não está
  embutido no build básico. Não há SSO nem integração AD nesta entrega.
- RDP pede usuário/senha em diálogo local. A senha passa para o FreeRDP via
  stdin, não vai para o painel nem para a lista de argumentos. O certificado
  do servidor RDP precisa ser válido/confiável.
- Quiosque inicia navegador em tela cheia, retira painel/ícones e substitui o
  gerenciador de janelas por uma configuração Openbox sem menu/atalhos de
  execução. Isso é um piloto de sessão restrita, não garantia de bloqueio
  completo contra acesso físico ou falhas do navegador.
- `lock_wallpaper` reaplica periodicamente o wallpaper no desktop. Ainda não
  corresponde a bloqueio administrativo por política Xfconf.
- USB controla montagem automática; não é bloqueio de USB no kernel.
- `reapply` e mudanças de perfil podem fechar a aplicação supervisionada.
  Reiniciar/desligar são enviados ao agente como operações fixas, sem shell.
- VNC, impressoras gerenciadas, múltiplos monitores por perfil, SSO/AD,
  distribuição de pacotes por grupo e instalação permanente em disco não
  fazem parte desta versão.

## Validação para ampliar o piloto

Homologue boot BIOS e UEFI, persistência de identidade, armazenamento em RAM,
driver de rede/vídeo, funcionamento Citrix/RDP, isolamento dos grupos,
reaplicação, perda de rede e reinício. Só depois teste concorrência e 50+ PCs.

Referências oficiais:

- https://docs.openthinclient.com/2603/books/openthinclient-management-server-en-us/page/thin-client
- https://docs.openthinclient.com/2603/books/openthinclient-management-server-en-us/page/desktop
- https://manpages.debian.org/bookworm/live-build/lb_config.1.en.html
- https://manpages.debian.org/bookworm/live-boot-doc/live-boot.7.en.html
- https://manpages.debian.org/bookworm/freerdp2-x11/xfreerdp.1.en.html
- iPXE: https://ipxe.org/howto/chainloading


## Contas do painel e atividade

A aba Usuários permite criar contas de administrador e operador, editar nome,
redefinir senha e desativar o acesso. O login é único e não pode ser renomeado.
Administradores gerenciam usuários e atualizações; operadores gerenciam máquinas,
grupos e aparência. O sistema impede desativar/rebaixar o último administrador ativo.
A senha admin existente é preservada na migração. Alterar uma conta invalida suas sessões.

Atividade exibe os últimos 100 eventos com usuário, horário, ação e IP, com filtro.
O IP vem do nginx, que sobrescreve X-Real-IP; mantenha o backend em loopback.
Eventos anteriores mantêm seus autores originais e não recebem atribuição retroativa.
Senhas e tokens não são gravados nos eventos. A auditoria cobre as ações do painel,
não os aplicativos ou sites usados dentro da sessão do thin client.

A máquina aparece pendente depois que o Linux carrega e o agente solicita cadastro.
O servidor TFTP estático não comunica os pedidos de boot ao painel. Um loop baixando
ipxe.efi significa que o DHCP continua entregando o primeiro estágio. Na reserva
Windows, preserve 067 padrão como freethinclient/ipxe.efi e use a classe de usuário
iPXE (ID ASCII iPXE) para entregar 067 http://IP_DO_SERVIDOR:8081/boot.ipxe.
Na lista de máquinas, ajuste o nome e escolha um grupo antes de Aprovar; as
configurações de sessão são definidas em Grupos e perfis.


### Kernel panic antes do live-boot em UEFI

Se kernel e initrd baixam com OK, mas o Linux para imediatamente com
`VFS: Unable to mount root fs on unknown-block(0,0)`, verifique a entrega do initrd
pelo carregador. O script publicado passa explicitamente `initrd=initrd.magic`
para compatibilidade com versões antigas de iPXE/EFI. O arquivo HTTP continua
se chamando initrd.img; initrd.magic é o arquivo virtual criado pelo iPXE.
Não é preciso reconstruir a imagem para alterar essa linha em boot.ipxe.
Essa é uma hipótese de correção para o piloto; confirme reiniciando o cliente.
