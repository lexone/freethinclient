# FreeThinClient 0.2.6

Corrige o console conectado com a imagem vazia quando o noVNC recebe blocos Tight JPEG/PNG. O noVNC decodifica esses blocos por imagens data:, mas a política de segurança do painel admitia somente imagens da própria origem e blob:. O navegador bloqueava o carregamento e a fila de renderização não desenhava os pixels.

A diretiva img-src agora permite data:. A diretiva script-src permanece restrita à própria origem. Não são habilitados scripts inline, avaliação de código ou imagens de servidores externos.

O teste com Chrome, o controlador e o relay reais recebe um frame Tight JPEG e confere os pixels do canvas. A falha foi reproduzida com a política anterior: sessão VNC conectada, frame recebido e imagem bloqueada pela CSP. A mesma imagem é desenhada após a correção. Os testes com pixels sem compressão e x11vnc real também permanecem no CI.

Instale **0.2.6** em Atualizações, recarregue a página e abra uma nova sessão no console. **Não precisa atualizar ou recompilar a imagem Linux** se o cliente já recebeu os componentes da 0.2.4.
