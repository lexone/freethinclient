# FreeThinClient 0.2.2

- Atualizações: acompanhamento por etapas e histórico textual de consulta, download, validação, backup, ativação e saúde. O progresso representa etapas, não uma estimativa do tempo restante.
- Login: opção **Manter conectado por 30 dias**, com cookie HttpOnly/Secure e credencial revogável armazenada somente como hash. A senha não é guardada pelo aplicativo. Sair e alterar a senha/conta revogam o acesso. Sessões comuns continuam expirando após uma hora/reinício.
- Máquinas: **Console remoto** para administradores em clientes aprovados e online. Usa noVNC 1.7.0 (MPL-2.0) e x11vnc. Começa em somente visualizar; controle de teclado e mouse precisa ser selecionado antes de conectar. Inclui tela inteira, encerramento e auditoria.

O console dura até 10 minutos, aceita até quatro sessões simultâneas e uma por PC. O agente inicia x11vnc como o usuário thinclient, com senha temporária e escuta exclusiva em loopback. Os dados trafegam pelo HTTPS existente, com certificado fixado no agente. Não há VNC escutando na LAN, download de código via CDN ou alteração de nginx. O relay usa blocos HTTPS com sequência, limite de buffer e repetição idempotente. Perder o navegador por 40 segundos, revogar a máquina ou sair do painel encerra o relay. A qualidade/latência deve ser homologada no ambiente real.

Após instalar esta versão pelo portal, use **Imagens e boot → Atualizar componentes do cliente** e reinicie o PC pelo PXE. Essa etapa instala x11vnc, o módulo do relay e a unidade do agente atualizada, com leitura do Xauthority e acesso ao socket X11 da sessão. Clientes antigos mostram instruções para atualizar a imagem. O console acompanha a sessão X11 existente em :0; não cria outra área de trabalho.

A release anterior permanece intacta. Este pacote não contém uma imagem Linux completa; a imagem é atualizada separadamente pelo portal.
