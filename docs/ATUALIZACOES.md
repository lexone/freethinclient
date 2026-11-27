# Atualizações assinadas

## Preparar a primeira publicação

O instalador gera uma chave RSA de 3072 bits no servidor. Somente a pública fica
disponível para verificação; a privada permanece em
`/root/freethinclient-signing/release-private.pem` (0600).

1. Faça backup criptografado da privada em um cofre.
2. No GitHub, crie o environment **release** e configure revisores obrigatórios.
3. Configure o secret **RELEASE_PRIVATE_KEY** nesse environment com o PEM
   completo da chave privada do servidor. Nunca cole a chave no chat ou no git.
4. A chave pública fixada no servidor deve corresponder à privada usada no workflow.

Com GitHub CLI autenticado no servidor, é possível enviar sem exibir a chave:

```bash
sudo sh -c 'gh secret set RELEASE_PRIVATE_KEY --repo lexone/freethinclient --env release < /root/freethinclient-signing/release-private.pem'
```

O CLI precisa estar autenticado no contexto usado pelo sudo; essa configuração
é manual e não é feita pelo instalador. Como alternativa, use o formulário de
secrets com um método seguro de transferência. Se houver vários servidores,
distribua a mesma chave **pública** aos verificadores por canal autenticado;
não gere uma chave de publicação diferente para cada release.

## Publicar uma nova versão

1. Atualize `VERSION`, por exemplo de `0.1.0` para `0.1.1`.
2. Atualize `CHANGELOG.md`, revise e passe no CI.
3. Execute **Actions → Signed release → Run workflow** no commit revisado e
   informe exatamente a versão do arquivo VERSION.
4. O workflow roda testes, produz pacote, manifesto, assinatura e cria a
   release estável `v0.1.1` no mesmo commit.

Sem o secret, o workflow falha antes de publicar. Não há release instalável
assinada até que essa configuração seja feita. A instalação inicial é pelo
checkout revisado; a confiança inicial no código/chave depende do administrador.

É possível assinar fora do Actions no servidor ou em máquina segura:

```bash
sudo python3 scripts/build-release.py --key /root/freethinclient-signing/release-private.pem
# Publique os três arquivos dist/* como assets da mesma release vX.Y.Z.
```

O pacote da aplicação não contém o Chrome nem o Citrix, nem uma imagem PXE.

## Validar e instalar pelo painel

Clique em **Consultar GitHub**. O worker consulta `/releases/latest`, rejeita
draft/prerelease, baixa manifesto e assinatura e verifica:

- assinatura RSA/SHA-256 com chave pública local;
- repositório esperado, tag `vX.Y.Z` e versão estável numérica;
- versão mínima, plataforma `ubuntu-24.04-amd64` e esquema de estado 1;
- nomes de assets sem duplicação e limites de tamanho.

Se houver versão superior assinada, libera **Instalar versão verificada**.
Ao instalar, verifica tudo novamente, exige a versão escolhida pelo admin,
bloqueia downgrade/reinstalação, valida tamanho e SHA-256 do pacote e extrai em
staging. Links, dispositivos, caminhos absolutos, `..` e expansão excessiva
são rejeitados. O código Python é compilado antes de parar o serviço.

Depois faz snapshot consistente do SQLite, guarda configuração/wallpaper,
grava journal, troca o link ativo e inicia o serviço. O `/healthz` deve retornar
status ok, versão esperada e schema 1. O painel pede recarregamento após update.
Sessões expiram no reinício do processo.

## Falha e rollback

Se a nova versão falhar, o worker volta o link e o banco anteriores e testa o
serviço antigo. O status mostra `rolled_back`. Se houver queda de energia com
transação pendente, o timer executa a mesma recuperação no próximo início.
Se o rollback também falhar, o status registra erro e mantém o journal para
intervenção manual. Não apague o journal sem analisar o backup.

As unidades systemd, nginx e pacotes do SO não são atualizados por esse fluxo.
Mudanças nesses arquivos precisam de um procedimento explícito de manutenção.
O esquema 1 não faz migrações destrutivas; outros esquemas são recusados.

## Repositório privado

```bash
sudo python3 scripts/configure-github.py
```

Informe token fine-grained com acesso apenas a este repositório e **Contents:
read**. Token não aparece no comando, painel, clientes ou logs. Rotacione antes
de expirar. Para repo público pode deixar vazio; valem os limites da API anônima.

## Rotação da chave

A chave pública nunca é trocada automaticamente pelo pacote. Gere a nova chave
fora do git, distribua a nova pública por acesso administrativo autenticado,
configure a nova privada no environment e só então publique a próxima release.
Uma perda da chave privada exige esse procedimento, não desativação da assinatura.


## Publicação e teste da release 0.2.1

O workflow também inicia em um push para release/vX.Y.Z. O nome da branch deve
corresponder exatamente ao VERSION. A chave continua no environment release e
as proteções/revisores configurados nesse environment continuam sendo exigidos.
Os três assets são verificados localmente com a chave pública derivada, enviados
primeiro a um draft e então publicados como release estável. O workflow não
substitui uma release estável já existente nem permite reutilizar uma versão em
outro commit.

Após publicar, um Ubuntu 24.04 descartável é instalado com o baseline 0.2.0. O teste
usa o token temporário do job e a chave pública do publicador para consultar e
instalar a release real do GitHub por meio da API do painel. Valida autenticação,
CSRF, permissões, assinatura, SHA-256, backup, saúde, persistência e novo login.
Depois executa o teste de falha de saúde e rollback com pacotes de teste somente
no contêiner; pacotes defeituosos não são publicados. Se uma publicação nova
falhar, a release é marcada como prerelease e deixa de ser oferecida pelo updater.
Esse teste não modifica nem valida a VM física do usuário.

No servidor instalado, uma verificação adicional sem instalar ou reiniciar pode
ser executada após receber os scripts desta versão:

```bash
sudo python3 /opt/freethinclient/current/scripts/verify-remote-release.py --expected-version 0.2.1
```

A saída contém apenas versão, resultado da verificação e fingerprint da chave
pública; não inclui token ou chave privada. Para o teste real na VM, use a aba
Atualizações, confira a assinatura, aplique 0.2.1 e recarregue/entre novamente.
A imagem Linux continua tendo seu próprio fluxo em Imagens e boot.
