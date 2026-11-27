# FreeThinClient 0.2.1

Primeira release estável assinada para testar a atualização remota do painel a partir da versão 0.2.0.

Inclui grupos e aprovação de clientes, contas e auditoria, desktop Blue Workspace, atalhos e ações de energia, modos de abertura e inicialização de aplicativos, RDP direto ou com destino informado ao conectar, permissões de rede/Wi-Fi e DNS gerenciado por grupo. A publicação PXE omite o parâmetro ip=dhcp que produzia um resolvedor inválido no piloto.

## Instalação pelo painel

Em **Atualizações**, clique em **Consultar GitHub**, confira **0.2.1** e a assinatura válida e escolha **Instalar versão verificada**. Aguarde a confirmação e recarregue o painel; pode ser necessário entrar novamente. A verificação usa a chave pública já fixada no servidor; ela deve corresponder ao secret de assinatura do publicador.

O pacote contém o código do servidor e dos clientes, não o filesystem Linux completo. Após atualizar o painel, aplique **Imagens e boot → Atualizar componentes do cliente**, aguarde a conclusão e reinicie os PCs pelo PXE para instalar o código novo na imagem. Mudanças posteriores de perfil chegam pelo agente.

O update remoto preserva usuários, senhas, grupos, dispositivos e perfil. Faz backup do banco, troca a versão, reinicia o painel e verifica a saúde; falhas restauram a versão e o banco anteriores. Pacotes do host Ubuntu, unidades systemd e nginx permanecem sob o procedimento de manutenção documentado. Servidores que não receberam a preparação dos serviços de imagem do piloto devem aplicá-la antes de usar a manutenção de imagem pelo portal.

## Assets e validação

- freethinclient-0.2.1.tar.gz: código da aplicação.
- manifest.json: versão, plataforma, versão mínima, tamanho e SHA-256.
- manifest.sig: assinatura RSA/SHA-256 do manifesto.

O workflow verifica os bytes antes de publicar e valida o download real do GitHub, a assinatura e a instalação por meio da API autenticada do painel em Ubuntu descartável. Exercita também preservação de dados, novo login e rollback diante de falha de saúde. Uma publicação nova que falhar nessa validação é marcada como prerelease e deixa de ser oferecida como release estável pelo atualizador.

Compatibilidade: servidor Ubuntu 24.04 amd64, clientes Debian 12. O portal Citrix usa o navegador; o cliente ICA nativo depende do pacote oficial compatível. O hardware Wi-Fi e os modos de aplicativos ainda devem ser homologados no piloto.
