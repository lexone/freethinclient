# FreeThinClient 0.2.5

O console deixa de apresentar "Conectado" quando apenas o transporte do agente está aberto. A confirmação de sessão VNC aparece somente após a negociação/autenticação do noVNC.

Erros de processamento do protocolo são capturados e mostrados, encerrando o fluxo com um motivo visível. A interface informa os bytes recebidos/enviados, a etapa da negociação e a resolução da tela. Se a negociação não terminar em 30 segundos, mostra a etapa em que parou.

O teste de navegador agora usa Chrome, o controlador real do console, o relay e x11vnc com UMask=0077. Confere pixels vermelhos efetivamente desenhados no canvas. Há também uma fixture RFB determinística que valida a resposta DES do noVNC.

Esta versão altera o painel e seus testes. **Não requer recompilar a imagem Linux** se o cliente já recebeu os componentes da 0.2.4. Após instalar a 0.2.5, abra uma nova conexão no console. Se a tela continuar vazia, o diagnóstico visível e o Console do navegador (F12) ajudam a distinguir negociação, transporte e captura da imagem; a causa no equipamento real ainda precisa ser confirmada.
