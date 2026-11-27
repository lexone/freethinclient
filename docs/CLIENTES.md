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


### Acompanhamento no painel

Em Máquinas, Verificar agora consulta o cadastro no servidor. O painel mostra
consulta em andamento, hora da última resposta, próxima consulta em cinco segundos
e contagens de máquinas cadastradas, online e pendentes. Se a consulta falhar,
os resultados anteriores são mantidos e identificados como possivelmente desatualizados.
Cada requisição tem limite de 15 segundos; uma nova consulta não duplica a que está em curso.
O último contato de cada agente aparece na lista. Esse botão não faz varredura da rede
nem mede downloads PXE. O progresso percentual do boot ainda não é enviado pelo cliente.


## Desktop limpo e aplicativo do quiosque

O grupo controla os atalhos Navegador, Área remota e Citrix, os ícones do sistema
(Início, Lixeira e volumes) e a barra inferior. Somente navegador desmarca os demais
atalhos e os ícones do sistema; Ocultar todos os atalhos remove os três atalhos
gerenciados. Arquivos do usuário não são apagados. A barra tem um controle separado.
Navegador e portal Citrix podem abrir em tela cheia mantendo o desktop.

Em Quiosque com aplicativo único, selecione Chromium, portal Citrix no navegador
ou RDP. Desktop, barra e atalhos ficam ocultos. RDP pede credenciais e mantém
validação do certificado; Citrix ICA não está incluído. Não há campo de comandos
arbitrários. Quiosque restringe a interface da sessão, não fornece isolamento físico
ou uma política completa de segurança do sistema operacional.

A imagem cliente precisa conter a nova session.py para aplicar essas opções.
Atualizar somente o painel não modifica o sistema SquashFS que o PC carrega.
Depois de atualizar o checkout e o painel, o servidor pode atualizar a imagem PXE
existente com:

```bash
bash scripts/refresh-client-image.sh /srv/freethinclient/boot
```

O comando descompacta o SquashFS em diretório temporário, copia o agente e a sessão,
renderiza os assets SVG em PNG, compacta uma nova imagem e guarda a anterior em
/var/backups/freethinclient/pxe-DATA. A publicação usa troca de arquivo; kernel,
initrd, certificado, URL do painel, boot.ipxe, DHCP e ISO não mudam. Requer espaço
para a árvore descompactada, a nova imagem e o backup. O comando recusa imagens
que contenham identidade de um cliente cadastrado. Reinicie o PC pelo PXE para
carregar a imagem nova e aprove/vincule o cliente no painel conforme necessário.

PNG evita depender de um loader SVG ausente na instalação mínima. O desktop define
o wallpaper mesmo quando as propriedades ainda não existem no xfconf, respeita
o diretório Desktop localizado do XDG e substitui os painéis padrão por uma barra
inferior. A compilação completa também inclui o suporte SVG e os mesmos PNGs.
A aparência e a troca de modos precisam ser conferidas no hardware do piloto.


## Manutenção da imagem pelo portal

Administradores usam Imagens e boot → Linux e aplicativos da imagem PXE:

- Consultar versões lê o banco dpkg da imagem publicada.
- Atualizar componentes do cliente aplica o agente, a sessão, os PNGs e o banner
  da versão instalada no servidor. Essa opção também corrige a confiança dos atalhos
  XFCE com metadata::xfce-exe-checksum, calculado dos bytes do arquivo gerado;
  a proteção para arquivos externos continua ativa.
- Atualizar Linux instala as atualizações e o kernel do Debian 12; não faz mudança
  de versão principal da distribuição e não atualiza o Ubuntu do servidor.
- Chromium vem do repositório Debian. Google Chrome usa o .deb estável oficial,
  com HTTPS e validação de nome/arquitetura do pacote. Quando instalado, Chrome
  é preferido pelo supervisor de sessão.
- Citrix Workspace exige o link HTTPS direto do .deb amd64 nos hosts oficiais
  e seu SHA-256. O pacote deve ser icaclient; dependências incompatíveis causam
  erro antes da publicação. O portal no navegador continua uma opção distinta do
  cliente ICA instalado. A obtenção de um novo link Citrix é feita no site oficial.

O serviço root separado freethinclient-image.timer verifica pedidos a cada 15s.
A API aceita apenas ações fixas e exige administrador e CSRF. A fila, as etapas,
o log recente e o autor ficam visíveis; a auditoria registra pedido e resultado.
O painel não executa comandos ou escolhe caminhos do host.

As alterações são feitas em cópia extraída sob /var/lib/freethinclient-image,
com montagem privada e serviços do chroot bloqueados. Pacotes apt usam verificação
normal do repositório; não se usam opções para desabilitar assinaturas. Downloads
Google/Citrix não podem redirecionar para hosts externos à lista do fornecedor.
A publicação cria /srv/freethinclient/boot/releases/ID com kernel, initrd e SquashFS
compatíveis e checksums. Somente após todas as etapas troca atomicamente boot.ipxe.
A imagem anterior permanece disponível e Voltar à imagem anterior troca o próximo
boot para ela. Não apague releases enquanto existirem clientes iniciando por elas.
Os clientes já ligados não são reiniciados e precisam de novo boot para atualizar.
A ISO original não é regenerada por essa manutenção.

Instalações novas e upgrade-local.sh instalam o serviço e seus pré-requisitos.
É necessário atualizar uma instalação anterior uma vez para disponibilizar essa
área. As tarefas seguintes são solicitadas no portal. Antes da primeira manutenção,
conclua a publicação inicial da imagem e mantenha espaço para descompactação,
nova compactação e versões anteriores. Falhas de pacote não devem trocar o script
ativo; a validação de boot físico continua sendo parte do piloto.

O initrd do cliente mostra o banner FREETHINCLIENT fornecido para o projeto,
com Copyright © 2026 Everton S Oliveira, no início do Linux. A atualização de
componentes regenera o initrd para incluir esse banner. Boot normal usa quiet e
loglevel=3, preservando mensagens de erro. O banner usa os glifos Unicode fornecidos;
a fonte e a largura do console determinam a apresentação no hardware.


## Atalhos e ações por grupo

A aba Atalhos e ações seleciona um grupo e permite renomear/ocultar os atalhos
principais, escolher ícones para até 12 atalhos web HTTPS, editar/ocultar/remover
entradas adicionais. Primeiro adicione o site à lista e depois
salve o grupo. Alterações de perfil preservam os atalhos existentes quando o formulário
não envia esse campo. O editor mantém alterações pendentes durante as consultas automáticas.

Desligar e Reiniciar são atalhos opcionais no desktop. A confirmação de saída pode
ser habilitada ou desabilitada. O cliente usa somente as duas ações fixas de energia
via systemd-logind, sem sudo e sem comandos personalizados. A regra polkit vale apenas
para o usuário thinclient em sessão local ativa; não concede gestão de serviços nem
permissões para sessões remotas/inativas. Desabilitar um ícone controla sua exibição,
não é uma política geral de bloqueio de energia do sistema operacional.

Em quiosque, nenhum atalho ou ação do desktop é mostrado, e a chamada do lançador
recusa atalhos personalizados e ações de energia. Para usar a nova funcionalidade,
atualize o painel, aplique Atualizar componentes do cliente em Imagens e boot e
reinicie o PC. Os nomes/URLs/visibilidade posteriores são enviados pelo agente sem
nova reconstrução da imagem. A posição visual dos atalhos no desktop continua sujeita à organização de ícones do XFCE.


### Extração sob PrivateDevices

O worker mantém PrivateDevices=yes. A extração ignora apenas o diretório /dev
arquivado no SquashFS e recria o diretório vazio: dispositivos são fornecidos
pelo mount privado no chroot e pelo devtmpfs no boot. Não se ignora o código de
saída do unsquashfs. Isso evita erros EPERM ao tentar recriar /dev/null,
/dev/console etc. Staging de tarefas interrompidas é removido sob o lock do worker.
O teste systemd contém device nodes na imagem e comprova a extração com CAP_MKNOD
indisponível. A falha original não publica uma nova imagem.


## Nome e IP no desktop

O cliente mostra um quadro no canto inferior esquerdo com o nome definido em
Máquinas e o IPv4 da interface com a rota padrão preferida. Antes da aprovação,
ou quando não houver nome recebido do painel, usa o hostname local. A leitura
é atualizada a cada cinco segundos; mudanças do nome chegam no heartbeat do agente.
Se não houver IPv4 disponível, exibe Sem IPv4. Não modifica o hostname do sistema.

Em Atalhos e ações → grupo, Mostrar nome e IP no desktop permite ocultar o quadro.
Ele fica abaixo das janelas de aplicativos, fora da barra de tarefas, não recebe
foco e fica oculto no quiosque. É um processo GTK do usuário thinclient, sem sudo.
Atualize os componentes da imagem e reinicie o cliente para instalar o autostart.


### Reparação de ícones e barra no cliente

A atualização de componentes verifica e instala libglib2.0-bin (gio), xdg-user-dirs,
gvfs-daemons e polkitd quando seus executáveis estão ausentes. Copiar somente os
scripts não supre essas dependências. O gio é necessário para registrar a confiança
dos atalhos no XFCE; o diretório Desktop deve ser o mesmo usado pelo gerenciador.

A aplicação do perfil encerra e aguarda xfdesktop e xfce4-panel antes de modificar
os ícones e a configuração, e os inicia após terminar. Isso evita criar/remover
ícones durante o scan inicial e consultar o PID de um painel ainda encerrando.
O perfil aprovado já disponível é aplicado diretamente, sem uma passagem anterior
pelo perfil vazio. A revisão só é marcada como aplicada após concluir a configuração.
Uma falha para encerrar os componentes deixa a revisão pendente para nova tentativa.
O CI inicia os processos XFCE reais em HOME/X11/DBus isolados e verifica os atalhos,
seu checksum GIO, a barra e a reaplicação enquanto os componentes estão abertos.


## Inicialização de aplicativos e conexão RDP

Em **Grupos e perfis**, cada aplicativo tem seu modo de abertura: padrão do grupo,
janela, tela inteira ou quiosque. No modo Desktop, os marcadores de inicialização
abrem navegador, portal Citrix, RDP e os sites adicionais selecionados. Em outros
modos do grupo, apenas o aplicativo principal é iniciado. O quiosque do grupo
remove desktop e barra; o modo quiosque de um atalho abre aquele navegador em
quiosque mantendo o restante da sessão desktop. Tela inteira RDP usa /f; janela
omite esse parâmetro. O portal Citrix usa Chrome/Chromium; essas opções não
substituem a configuração dos aplicativos ICA nativos do Citrix Workspace.

Para RDP direto ao iniciar, selecione **Conectar diretamente por RDP ao iniciar**
e informe servidor e domínio. A conta e senha são solicitadas no cliente; a senha
segue pelo stdin do FreeRDP e não integra parâmetros ou perfil. Para um atalho que
permita escolher o servidor, marque **Perguntar o servidor ao abrir o RDP** e
**Atalho Área remota (RDP)**. Esse atalho funciona mesmo sem um destino fixo.

Atalhos web em **Atalhos e ações** também têm modo de abertura, parâmetros e
**Abrir este site junto com o desktop**. Cada lançador usa seu próprio diretório
de perfil do navegador, impedindo que uma instância existente ignore outro modo.
Após salvar, o agente reaplica o perfil e pode reiniciar aplicativos automáticos.

Parâmetros são separados com shlex e executados como lista de argumentos, sem
shell. O servidor e o cliente validam a mesma lista de opções. Não são aceitos
executáveis, senhas, troca de destino por parâmetro, desativação de certificados,
depuração remota, extensões locais ou --no-sandbox. Use os campos próprios para
URL, destino RDP e modo de janela. Exemplos e opções aceitas:

- Navegador/Citrix web: --incognito, --disable-gpu, --disable-dev-shm-usage,
  --disable-pinch, --start-maximized, --kiosk-printing, --window-size=1280,800,
  --window-position=0,0, --lang=pt-BR, --force-device-scale-factor=1.25 (0.5 a 3),
  --overscroll-history-navigation=0, --proxy-server=http://proxy.example:8080
  (HTTP/HTTPS/SOCKS4/SOCKS5, com porta, sem credenciais),
  --proxy-bypass-list="*.local;<local>".
- RDP: /multimon, /span, +clipboard, -clipboard, /clipboard,
  /dynamic-resolution, +dynamic-resolution, -dynamic-resolution, /smart-sizing,
  /sound, /microphone, +fonts, -fonts, +compression, -compression,
  +wallpaper, -wallpaper, /auto-reconnect, /size:1440x900, /bpp:16|24|32,
  /network:modem|broadband|broadband-low|broadband-high|wan|lan|auto,
  /scale:100|140|180 e /timeout:30 (1 a 999).

## Permissão de rede e teste de Wi-Fi

**Permitir que o usuário altere IP, DNS e conexões de rede/Wi-Fi** vem desmarcado.
A opção também está em **Atalhos e ações**. Quando habilitada para uma máquina
aprovada, cria **Rede e Wi-Fi** e inclui a bandeja de rede na barra inferior.
O atalho oferece **Conectar rede / Wi-Fi** (nmtui-connect), **Editar IP e DNS**
(nm-connection-editor) e diagnóstico de interfaces, rotas, DNS, bloqueios de rádio,
resolução do site inicial e acesso TCP 443. Um socket TCP bem-sucedido não confirma
TLS, proxy ou autenticação. O diagnóstico não modifica a rede nem mostra senhas
Wi-Fi; a resposta DNS depende do timeout do resolvedor do sistema.

O bloqueio é aplicado no polkit do NetworkManager, além de ocultar os controles.
Somente o usuário thinclient em uma sessão local ativa, com perfil aprovado e
permissão explicitamente verdadeira, pode controlar a rede e editar conexões.
O perfil é escrito pelo agente root; o usuário do desktop não pode alterá-lo.
Revogar a opção remove o atalho e bloqueia novas alterações; não desfaz uma
configuração de rede já aplicada. A janela fecha ao detectar a revogação.
Outros usuários e serviços do sistema mantêm suas políticas existentes.

A atualização de componentes instala NetworkManager, seu editor gráfico,
wpasupplicant, wireless-regdb e rfkill quando faltam. A imagem completa inclui
firmware Intel e Realtek; outras placas podem precisar de firmware específico.
A permissão não grava senhas ou perfis de rede no servidor. Em PXE sem
persistência, configurações locais podem desaparecer no reinício. Conectar Wi-Fi
ou alterar a interface em uso pode interromper o agente até recuperar acesso
ao servidor. Ethernet e Wi-Fi ligados ao mesmo tempo podem usar a rota Ethernet;
confira o diagnóstico antes de concluir qual conexão está sendo testada.

Após instalar esta versão no servidor, aplique **Imagens e boot → Atualizar
componentes do cliente**, aguarde a conclusão e reinicie o PC pelo PXE uma vez.
As mudanças seguintes de perfil chegam por heartbeat, sem recompilar novamente.


## DNS configurado pela gerência

A aba **Rede e DNS** seleciona um grupo e oferece DNS automático da conexão/DHCP,
DNS manual IPv4/IPv6 e domínios de pesquisa opcionais. A tela também mostra o
último resultado informado por cada agente: configurado, sem imposição do grupo
ou falha. É o estado da aplicação, não uma comprovação de acesso à internet.
Agentes antigos aparecem como aguardando suporte; atualize a imagem primeiro.

O agente root valida novamente os endereços e grava somente seu arquivo
/etc/NetworkManager/conf.d/90-freethinclient-dns.conf. O arquivo usa as seções
global-dns e global-dns-domain-* do NetworkManager. Configurações globais
substituem os DNS e domínios das conexões ativas enquanto a opção estiver ligada;
preencha o domínio de pesquisa se precisar resolver nomes internos curtos.
O agente recarrega configuração e resolvedor com nmcli general reload conf e, em seguida, nmcli general reload dns-rc,
sem derrubar interfaces ou mudar IP/gateway. Desmarcar a opção ou revogar a
aprovação remove somente esse arquivo e recarrega a configuração das conexões.
Falhas são registradas e tentadas novamente; o cliente precisa alcançar o servidor
para receber escolhas novas. O agente recebe escrita apenas no diretório de
snippets NM, além do seu diretório de estado, e nunca aceita caminhos ou shell
vindos do perfil. As definições do grupo são reaplicadas após boot por PXE.

O boot agora omite ip=dhcp: no Debian Live, DHCP já é o padrão. A sintaxe ip= do
live-boot descreve uma configuração estática e pode gerar o DNS inválido
“nameserver dhcp”. A correção está nos dois geradores de boot.ipxe (publicação
inicial e novas imagens/rollback). A origem deste defeito foi confirmada no piloto
pela combinação de IP/rota válidos e esse valor literal em /etc/resolv.conf.
