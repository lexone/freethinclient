# Segurança

O painel é para rede administrativa confiável. Não exponha diretamente à internet.
Use certificado da empresa e regras de firewall que limitem TCP 8443 à administração.

O processo web não é root e não pode escrever código, chave pública, token GitHub
ou unidades systemd. O serviço root lê apenas ações `check` e `apply`, sem comandos
de shell enviados pelo painel. Release assinada é autorização para executar código
no servidor: proteja a chave privada e quem pode publicar releases.

Senhas ficam em hash scrypt. Cookie HttpOnly, Secure e SameSite=Strict; CSRF em
mutações autenticadas. Limite de dez tentativas de login por IP em 15 minutos,
em memória (reinício limpa o limite). A conta inicial é administrativa única;
MFA, AD/LDAP, RBAC e vários administradores ainda não existem.

Checksum não comprova origem. O manifesto precisa passar na assinatura com a
chave pública fixada em `/etc/freethinclient/release-public.pem`. O GitHub token
fica somente em `/etc/freethinclient/update.json`, root:root 0600. Downloads com
redirecionamento nunca recebem Authorization no host de armazenamento.

O GitHub Actions precisa da chave de assinatura para publicar versões instaláveis.
Use environment `release` com revisores obrigatórios e branches restritos.
Quem pode modificar workflow executado com esse secret pode extrair a chave;
assinatura não substitui proteção de branch nem revisão do código.

PNG/JPEG são identificados pela assinatura de arquivo, sem decodificação profunda.
Envie apenas imagens confiáveis. SVG e HTML não são aceitos como wallpaper.

Backups contêm configurações e hash da senha: diretório root 0700. Nenhum token,
senha, certificado privado ou pacote proprietário deve ser commitado.

Atualizações aceitam apenas esquema de dados 1, Ubuntu 24.04 amd64 e versões
estáveis X.Y.Z crescentes. Mudanças incompatíveis de banco ou de instalação
exigem procedimento de migração separado. O updater não modifica unidades
systemd, nginx ou pacotes apt durante uma atualização de aplicação.

Esta versão não está homologada para produção. Reporte falhas em canal privado
ao mantenedor; nunca publique credenciais em issues.
