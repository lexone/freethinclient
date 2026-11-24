# PXE no piloto 0.2

A receita de build e publicação está em [CLIENTES.md](CLIENTES.md).
O instalador do painel não ativa DHCP, ProxyDHCP, TFTP ou NFS.

`scripts/build-client.sh` gera a ISO e kernel/initrd/SquashFS em um builder
Linux. `scripts/setup-boot.sh` publica os artefatos via HTTP em TCP 8081 e
os inicializadores iPXE via TFTP. O Windows Server mantém as concessões DHCP.

Antes de ativar boot no segmento, identifique:

- IP, VLAN, prefixo, gateway e DNS definitivos da VM.
- Escopo/versão do Windows DHCP, relay/IP helper e existência de WDS/SCCM.
- Arquitetura BIOS/UEFI, Secure Boot e hardware do PC piloto.
- Acesso dos clientes ao painel HTTPS e ao servidor de imagem.
- Persistência da identidade do agente, ou reconhecimento por MAC explicitamente
  habilitado em grupo para uma rede de boot confiável.

Não use um único arquivo de boot para BIOS e UEFI. Clientes que já carregaram
iPXE precisam receber o script HTTP, evitando loop de chainloading.
A receita usa um único sistema Linux; o perfil é aplicado pelo agente depois
da aprovação. A escolha de origem no grupo não reconfigura o firmware nem
instala o sistema no disco.

## Estado de validação

A presença dos arquivos de imagem pode ser consultada no painel. Isso não
comprova que o DHCP, a arquitetura, os drivers ou o Secure Boot estão corretos.
A versão não declara automaticamente `pxe_verified=true`.

Homologue primeiro uma VM cliente e depois um PC real; só então amplie a frota.
Referências: [iPXE](https://ipxe.org/howto/chainloading),
[live-build](https://manpages.debian.org/bookworm/live-build/lb_config.1.en.html).
