# Operação

## Instalar e verificar

Siga o README. O instalador precisa de acesso apt/HTTPS e sudo, mas não de
acesso ao VMware ou ao Windows DHCP. Mantém portas existentes do nginx e cria
um virtual host próprio em 8443. Não altera regras de firewall automaticamente.

```bash
systemctl status freethinclint freethinclint-update.timer nginx
journalctl -u freethinclint -u freethinclint-update --since today
curl http://127.0.0.1:8080/healthz
```

Em HTTPS, confira a impressão digital do certificado pelo console antes de
confiar no certificado local do piloto:

```bash
sudo openssl x509 -in /etc/freethinclint/tls.crt -noout -fingerprint -sha256
```

Uma segunda execução completa do instalador sai sem modificar a instalação.
Se a primeira execução foi interrompida, examine arquivos e journal; o script
não apaga automaticamente diretórios de uma instalação parcial.

## Alterar senha administrativa

No checkout do projeto:

```bash
sudo python3 scripts/reset-admin.py
```

A nova senha é solicitada sem eco e o serviço reinicia, encerrando as sessões.

## Mudar VLAN e endereço

Faça a troca do port group no VMware e configure a interface Ubuntu pelo
console para evitar perder acesso. Confirme prefixo, gateway e DNS da rede
definitiva. Os arquivos em `/etc/netplan` dependem da interface criada na VM;
nunca copie um YAML com nome de interface ou endereços de outro ambiente.

O painel escuta em todas as interfaces na porta TLS 8443, sem IP fixo gravado
no código. Se usar DNS, atualize o registro. Se o IP/DNS do certificado mudar,
reinstale certificado válido para o novo endereço e execute:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Não execute o instalador novamente para trocar o IP. Serviços PXE e referências
de boot serão configurados somente depois do endereço definitivo.

## Backup independente

Os backups do update não substituem backup periódico externo. Para cópia fria,
pare painel e timer, confirme que o worker de atualização não está ativo,
copie `/var/lib/freethinclint`, `/etc/freethinclint`, `/opt/freethinclint` e
`/var/backups/freethinclint` preservando permissões e symlinks. Guarde a chave
privada separadamente em cofre. Reinicie o painel e o timer após a cópia.
Proteja os backups, pois contêm hash administrativo e, em `/etc`, token GitHub.

## Recuperação manual

Pelo console do VMware, mantenha uma cópia dos arquivos atuais. Inspecione
`/opt/freethinclint/pending-update.json`, diretórios de releases e backups.
Para acionar a recuperação automática pendente:

```bash
sudo systemctl start freethinclint-update.service
sudo journalctl -u freethinclint-update -n 80 --no-pager
```

Se precisar restaurar manualmente, pare timer e painel, restaure o link `current`
para uma release conhecida e o banco do snapshot correspondente. Remova WAL/SHM
apenas com o serviço parado; mantenha propriedade freethinclint no banco.
Confirme `/healthz` antes de remover o journal pendente e reativar o timer.
Escolher arbitrariamente um banco de outro esquema não é suportado.

Não existe limpeza automática de versões/backups nesta fase. Monitore disco e
remova apenas versões inativas e backups antigos após garantir cópia externa.
