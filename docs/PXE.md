# Plano de integração PXE (ainda não implementado)

O instalador 0.1.0 não inicia DHCP, ProxyDHCP, TFTP, NFS ou iPXE. O Windows Server
continua responsável por endereços. Não altere opções globais de boot sem
confirmar a arquitetura dos clientes e se há WDS/SCCM no mesmo segmento.

## Informações necessárias

- IP definitivo da VM, prefixo, gateway, DNS e VLAN.
- Windows Server DHCP: versão, escopo e permissões administrativas.
- BIOS/UEFI e Secure Boot do PC piloto; CPU amd64, RAM e adaptador de rede.
- VLANs dos clientes, roteamento, relay/IP helper e serviços PXE existentes.
- URL StoreFront/Gateway Citrix e destino RDP para homologação.
- Recursos necessários: áudio, monitores, USB, impressora, webcam e Teams.

## Implementação prevista

1. Criar imagem Ubuntu mínima com desktop leve e agente de configurações.
2. Integrar Chrome e FreeRDP; instalar Citrix Workspace de fonte oficial com
   dependências compatíveis e respeitando licença/redistribuição.
3. Preparar boot BIOS e UEFI, distribuição da imagem e escrita temporária
   individual em RAM. Homologar Secure Boot separadamente.
4. Integrar Windows DHCP com servidor de boot, escolhendo políticas ou
   ProxyDHCP/relay conforme a topologia, sem disputar concessões IP.
5. Implementar registro/aprovação de dispositivos, identidade por credencial
   própria, grupos e aplicação do perfil/wallpaper ao desktop Linux.
6. Validar reconexão, limpeza de dados ao reiniciar e ausência de credenciais
   compartilhadas nos clientes. Token GitHub nunca entra na imagem.
7. Testar um PC, depois um grupo pequeno e boot simultâneo de mais de 50 PCs.

## Critérios de aceite

Clientes iniciam sem HD; abrem Chrome, Citrix e RDP; recebem wallpaper definido
no painel; respeitam restrições de interface; não alteram DHCP existente;
retornam ao estado limpo após reiniciar. Medir tempo de boot, throughput,
memória, rede, concorrência e falha do servidor de imagem.

Referências: [iPXE chainloading](https://ipxe.org/howto/chainloading),
[Citrix Linux requirements](https://docs.citrix.com/us/en/citrix-workspace-app-for-linux/system-requirements.html),
[Microsoft PXE](https://learn.microsoft.com/en-us/troubleshoot/mem/configmgr/os-deployment/understand-pxe-boot).
