# Validação

## Automatizada

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
node --check web/app.js
python3 -m compileall -q app scripts
```

Testes cobrem senha e versão, autorização/CSRF, gravação de perfil/wallpaper,
assinatura válida e adulterada, checksum, caminhos inseguros em tar e rollback.
Fixtures de assinatura usam chaves temporárias exclusivas dos testes.

Na criação da versão 0.1.0, a suíte local passou em Windows (13 testes e um de
recuperação exclusivo de Linux ignorado). A suíte de 14 testes passou no runner
Ubuntu 24.04 do GitHub. O smoke test também verifica que nginx pode iniciar mesmo
quando o pacote não o inicia automaticamente durante a instalação.

CI executa testes no Ubuntu 24.04 e instala em contêiner descartável com systemd.
O contêiner também executa um update real de teste, confirma persistência e
permissões do banco e aplica uma versão defeituosa para verificar rollback.
`tests/smoke_update.py` recusa execução fora de contêiner explicitamente marcado
como descartável. Não execute esse teste no servidor da empresa.
O workflow de release testa o commit e exige chave de assinatura configurada.
Resultados do Actions devem ser conferidos no GitHub; a presença do workflow
não comprova que o ambiente de destino passou na homologação.

## Piloto em VMware (pendente)

- Instalação limpa em Ubuntu Server 24.04 amd64 e reinício da VM.
- TLS, login, senha errada, sessão expirada e logout.
- Salvar perfil, reiniciar serviço e confirmar persistência.
- Enviar PNG/JPEG e confirmar que imagem inválida e arquivo grande são recusados.
- Consultar GitHub sem chave correspondente: deve recusar assinatura.
- Configurar chave e publicar 0.1.1; conferir indicação de nova versão.
- Atualizar e confirmar nova versão em `/healthz`, perfil e wallpaper preservados.
- Publicar pacote assinado com serviço defeituoso e confirmar rollback.
- Interromper VM durante troca e validar recuperação da transação pendente.
- Em repo privado, testar token inválido/expirado e ausência de token nos logs.
- Repetir instalador e confirmar preservação de senha e dados.
- Trocar VLAN/IP pelo console e validar o acesso com certificado atualizado.

PXE, clientes físicos e capacidade de 50+ máquinas têm aceite separado em PXE.md.
