# FreeThinClient 0.2.4

Corrige a abertura do x11vnc quando o agente é executado com a UMask=0077 da sua unidade systemd. O diretório temporário permanecia 0700, impedindo o processo thinclient de alcançar o arquivo de senha. Agora a travessia é definida explicitamente em 0711; o diretório continua pertencendo a root e a senha permanece 0600, acessível somente pelo usuário thinclient e root.

O console preserva o motivo de falha apresentado pelo relay. Falta do pacote, problema de arquivos temporários e falha na sessão gráfica recebem orientações específicas, sem exibir senhas ou credenciais.

Instale **0.2.4** pelo portal, recarregue a página, execute **Imagens e boot → Atualizar componentes do cliente** e aguarde a conclusão. Depois reinicie o notebook pelo PXE: a imagem nova só entra em uso no próximo boot.

O teste real de x11vnc agora usa UMask=0077, reproduzindo a restrição da instalação. Ele verifica autenticação, recebimento de pixels, encerramento e limpeza dos arquivos temporários.
