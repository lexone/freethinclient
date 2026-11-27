# FreeThinClient 0.2.3

Corrige dois problemas da interface da 0.2.2: o botão **Console remoto** não havia sido incluído na lista de máquinas e a rota **Rede e DNS** não estava registrada, voltando para Visão geral.

Administradores veem o console em máquinas aprovadas e online. Um teste de renderização verifica a presença do botão, seu clique, as restrições e cada rota do menu. A opção **Manter conectado por 30 dias** permanece no formulário de login, agora também coberta por essa verificação.

A interface recarrega quando detecta uma versão diferente no servidor. Para receber esta primeira correção, instale **0.2.3** em Atualizações e recarregue com **Ctrl+F5**. Para marcar a opção de login, clique em **Sair** e entre novamente.

Esta correção altera a interface; quem já atualizou a imagem cliente para 0.2.2 não precisa recompilá-la por causa dela. Para o primeiro uso do console em uma imagem antiga, aplique **Imagens e boot → Atualizar componentes do cliente** e reinicie o PC pelo PXE.
