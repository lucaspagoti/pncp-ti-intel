# Cobertura da busca PNCP contra o ARP — 17/10/2026

Cargas ativas: compras_arp de 2026-10-17, pncp_busca de 2026-10-17; lista de termos `dcc22055600e`.
Gerado por `python -m pncp_ti.fontes.pncp_busca_auditoria`.

Referência: atas de TI vigentes do Compras ARP com `numero_controle_pncp`, classificadas
sem o índice de busca do PNCP. Mede a sobreposição SIASG/PNCP; **não é recall nacional**
e não cobre estados e municípios fora do SIASG. A busca entra com o mesmo filtro de
vigência da view.

## Cobertura da lista de termos

| ARP classificou como TI | atas | achadas pela busca | cobertura |
|---|---|---|---|
| pelo objeto (anexo da IN 05) | 6032 | 3547 | 58.8% |
| pelo nome do item (anexo da IN 05) | 1049 | 88 | 8.4% |
| pelos códigos do catálogo (CATMAT/CATSER) | 680 | 27 | 4.0% |
| **total** | 7761 | 3662 | **47.2%** |

Das 4099 perdidas, 755 têm um termo da lista no
objeto da ata (o PNCP indexa o objeto da **compra**, que pode ser outro, ou a ata não
aparece como vigente na busca). As demais não têm nenhum termo: são lacunas da lista.

### Palavras do anexo nas perdidas sem termo (candidatas a termo; o Lucas decide)

| Palavra do anexo da IN 05 | atas perdidas |
|---|---|
| informatica | 933 |
| tic | 373 |
| ti | 171 |
| hospedagem | 39 |
| internet | 38 |
| computador | 23 |
| cabeamento | 18 |
| hardware | 15 |
| infraestrutura de rede | 13 |
| fibra optica | 11 |
| wi-fi | 10 |
| voz | 9 |
| cloud | 9 |
| voip | 6 |
| bpm | 6 |

Antes de virar termo, a palavra precisa passar pelo filtro de frase sem trazer ruído
(ex.: `informatica` sozinha casa com mobiliário de informática).

### Perdidas sorteadas (20)

| Ata | Objeto (ARP) | Motivo no ARP | Link |
|---|---|---|---|
| `48031918000124-1-003541/2024-000010` | aquisição de bens (de consumo e permanente), utilizados em sistemas de seguranç… | VII-videomonitoramento:videomonitoramento@objeto | https://pncp.gov.br/app/atas/48031918000124/2024/3541/10 |
| `00394452000103-1-009089/2026-000003` | Aquisição de Materiais de Expediente | III-computadores:impressora@item | https://pncp.gov.br/app/atas/00394452000103/2026/9089/3 |
| `24098477000110-1-000100/2025-000012` | Registro de preços para a eventual Aquisição de equipamentos de TIC, especifica… | geral:tic@objeto | https://pncp.gov.br/app/atas/24098477000110/2025/100/12 |
| `10635424000186-1-000257/2025-000008` | aquisição de materiais e equipamentos destinados ao refeitório, alojamentos e l… | geral:informatica@objeto | https://pncp.gov.br/app/atas/10635424000186/2025/257/8 |
| `10779511000107-1-000216/2025-000008` | Contratação de materiais de consumo de TIC a fim de atender às demandas consoli… | geral:tic@objeto | https://pncp.gov.br/app/atas/10779511000107/2025/216/8 |
| `00394452000103-1-001573/2026-000019` | Aquisição de material de informatica. | geral:informatica@objeto | https://pncp.gov.br/app/atas/00394452000103/2026/1573/19 |
| `00394429000100-1-002818/2025-000008` | AQUISIÇÃO DE MATERIAL DE HIDRÁULICA PARA ATENDER AS NECESSIDADES DO GAP-MN E UN… | catmat70:pdm238@item:central | https://pncp.gov.br/app/atas/00394429000100/2025/2818/8 |
| `15126437000305-1-001959/2026-000015` | Registro de preços para a eventual aquisição de INSUMOS PARA INFORMÁTICA, a fim… | geral:informatica@objeto | https://pncp.gov.br/app/atas/15126437000305/2026/1959/15 |
| `00394452000103-1-005747/2026-000032` | eventual aquisição de Material permanente e suprimento de informática | geral:informatica@objeto |  |
| `13127340000120-1-000055/2025-000003` | registro de preços para aquisição de insumos destinados à fabricação de MOCHILA… | III-computadores:tablets@objeto | https://pncp.gov.br/app/atas/13127340000120/2025/55/3 |
| `15126437000305-1-004528/2025-000001` | Aquisição de Materiais/Insumos de Informática - Lote 01 | geral:informatica@objeto | https://pncp.gov.br/app/atas/15126437000305/2025/4528/1 |
| `17733643000147-1-000218/2025-000008` | A presente Ata tem por objeto o registro de preço para futura e eventual aquisi… | III-computadores:computador@item | https://pncp.gov.br/app/atas/17733643000147/2025/218/8 |
| `12207536000161-1-000046/2025-000015` | Registro de preços para a eventual Aquisição de Equipamentos de Informática des… | III-computadores:equipamentos de informatica@obje… | https://pncp.gov.br/app/atas/12207536000161/2025/46/15 |
| `00394452000103-1-020223/2025-000057` | eventual aquisição de Material permanente e suprimento de informática. | geral:informatica@objeto | https://pncp.gov.br/app/atas/00394452000103/2025/20223/57 |
| `00394452000103-1-025192/2025-000024` | Aquisição de suprimentos de informática não enquadrados como TIC | geral:tic@objeto | https://pncp.gov.br/app/atas/00394452000103/2025/25192/24 |
| `00394429000100-1-004049/2025-000011` | AQUISIÇÃO DE MATERIAIS ODONTOLÓGICOS PARA ESPECIALIDADE DE PRÓTESE DENTÁRIA (PR… | catmat70:pdm7590@item:prop1de1 | https://pncp.gov.br/app/atas/00394429000100/2025/4049/11 |
| `29112760000172-1-000101/2025-000011` | REGISTRO DE PREÇO VISANDO FUTURA E EVENTUAL AQUISIÇÃO DE EQUIPAMENTOS/BENS PERM… | III-computadores:microcomputador@item | https://pncp.gov.br/app/atas/29112760000172/2025/101/11 |
| `00394494000136-1-000909/2025-000030` | A presente Ata tem por objeto o registro de preços para a eventual aquisição de… | III-computadores:microcomputador@item | https://pncp.gov.br/app/atas/00394494000136/2025/909/30 |
| `00394452000103-1-010818/2026-000001` | A presente Ata tem por objeto o registro de preços para a eventual aquisição de… | III-computadores:materiais de informatica@objeto | https://pncp.gov.br/app/atas/00394452000103/2026/10818/1 |
| `30871497000184-1-000040/2024-000002` | Aquisição o de Licenças de softwares (Canva, Elements Envato e Microsoft Visio) | VI-software:softwares@objeto | https://pncp.gov.br/app/atas/30871497000184/2024/40/2 |

## Concordância por termo (proxy de precisão)

Das 16991 atas vigentes da busca, 3872 também estão no ARP; o ARP classifica 3664 delas como TI (94.6%).
Não é precisão: o anexo da IN 05 e a lista de termos compartilham palavras (notebook,
software, tecnologia da informação), então as duas fontes podem concordar no mesmo falso
positivo. Serve para achar o termo a revisar primeiro: concordância baixa com muitas
atas. Uma ata com vários termos conta em cada um na tabela e uma vez no total acima.

| Termo | atas | no ARP | ARP diz TI | concordância |
|---|---|---|---|---|
| gestao de documentos | 4 | 1 | 0 | 0% |
| estacao de trabalho | 37 | 25 | 10 | 40% |
| digitalizacao | 194 | 59 | 35 | 59% |
| tablet | 138 | 21 | 13 | 62% |
| scanner | 124 | 25 | 19 | 76% |
| videoconferencia | 111 | 63 | 48 | 76% |
| toner | 536 | 94 | 72 | 77% |
| microsoft | 116 | 64 | 55 | 86% |
| telefonia | 589 | 175 | 154 | 88% |
| cabeamento estruturado | 106 | 38 | 34 | 89% |
| antivirus | 22 | 11 | 10 | 91% |
| rede de dados | 102 | 24 | 22 | 92% |
| impressora | 2329 | 387 | 356 | 92% |
| solucao de seguranca | 24 | 14 | 13 | 93% |
| outsourcing de impressao | 98 | 53 | 50 | 94% |
| software | 824 | 206 | 195 | 95% |
| sistema operacional | 33 | 20 | 19 | 95% |
| switch | 193 | 85 | 81 | 95% |
| workstation | 46 | 22 | 21 | 95% |
| microinformatica | 56 | 45 | 43 | 96% |
| material de informatica | 637 | 151 | 145 | 96% |
| nuvem | 144 | 45 | 44 | 98% |
| backup | 94 | 47 | 46 | 98% |
| microcomputador | 233 | 101 | 99 | 98% |
| equipamentos de informatica | 4378 | 314 | 309 | 98% |
| computadores | 1312 | 262 | 258 | 98% |
| tecnologia da informacao | 2024 | 1063 | 1052 | 99% |
| materiais de informatica | 2452 | 433 | 430 | 99% |
| access point | 9 | 2 | 2 | 100% |
| acesso a internet | 136 | 23 | 23 | 100% |
| banco de dados | 12 | 1 | 1 | 100% |
| cartucho de impressora | 13 | 2 | 2 | 100% |
| central telefonica | 10 | 2 | 2 | 100% |
| certificado digital | 42 | 7 | 7 | 100% |
| cftv | 223 | 116 | 116 | 100% |
| computacao em nuvem | 18 | 7 | 7 | 100% |
| computador desktop | 16 | 1 | 1 | 100% |
| data center | 45 | 26 | 26 | 100% |
| fabrica de software | 7 | 3 | 3 | 100% |
| firewall | 39 | 22 | 22 | 100% |
| licenca de software | 14 | 1 | 1 | 100% |
| licenciamento de software | 23 | 6 | 6 | 100% |
| link de internet | 39 | 7 | 7 | 100% |
| locacao de impressoras | 93 | 8 | 8 | 100% |
| monitor de video | 11 | 3 | 3 | 100% |
| notebook | 130 | 36 | 36 | 100% |
| perifericos de informatica | 526 | 52 | 52 | 100% |
| roteador | 74 | 10 | 10 | 100% |
| servicos de tic | 11 | 11 | 11 | 100% |
| servidor de dados | 3 | 1 | 1 | 100% |
| servidor de rede | 17 | 8 | 8 | 100% |
| solucao de tic | 18 | 18 | 18 | 100% |
| storage | 59 | 35 | 35 | 100% |
| suprimentos de informatica | 1522 | 216 | 216 | 100% |
| videomonitoramento | 320 | 49 | 49 | 100% |
| assinatura eletronica | 5 | 0 | 0 | - |

## Amostra para rotular (30 atas só da busca, fora do ARP)

Preencha a coluna Rótulo com TI ou NÃO; a precisão rotulada sai desta amostra.

| Ata | Esfera/UF | Objeto | Termos | Link | Rótulo |
|---|---|---|---|---|---|
| `03156999000150-1-000053/2025-000018` | Municipal/MS | REGISTRO DE PREÇOS FUTURA E EVENTUAL AQUISIÇÃO DE COMPONENTES/ITENS DE INFORMÁTICA E COMP… | computadores | https://pncp.gov.br/app/atas/03156999000150/2025/53/18 || TI |
| `46429379000150-1-000099/2026-000023` | Municipal/SP | REGISTRO DE PREÇO PARA AQUISIÇÃO DE SUPRIMENTOS DE INFORMÁTICA, PERIFÉRICOS, EQUIPAMENTOS… | cabeamento estruturado, suprimentos de … | https://pncp.gov.br/app/atas/46429379000150/2026/99/23 || TI |
| `29115441000110-1-000007/2025-000001` | Municipal/RJ | Aquisição de computadores do tipo deesktop e notebook, impressora, drone, rádio comunicad… | computadores, impressora, notebook, sup… | https://pncp.gov.br/app/atas/29115441000110/2025/7/1 || TI |
| `18803072000132-1-000010/2026-000001` | Municipal/MG | \[Portal de Compras Públicas\] - REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL AQUISIÇÃO DE ELE… | equipamentos de informatica | https://pncp.gov.br/app/atas/18803072000132/2026/10/1 || TI (misto) |
| `13825500000104-1-000113/2026-000006` | Municipal/BA | \[Portal de Compras Públicas\] - Registro de preços para futura e eventual Contratação de e… | materiais de informatica | https://pncp.gov.br/app/atas/13825500000104/2026/113/6 || TI |
| `48664304000180-1-000144/2025-000016` | Municipal/SP | FORNECIMENTO PARCELADO DE PECAS E EQUIPAMENTOS PARA MANUTENCAO DO PARQUE TECNOLOGICO E IN… | tecnologia da informacao | https://pncp.gov.br/app/atas/48664304000180/2025/144/16 || TI |
| `31055800000133-1-000022/2025-000003` | Municipal/PE | Registro de preço visando a aquisição de equipamentos e materiais de informática, destina… | materiais de informatica | https://pncp.gov.br/app/atas/31055800000133/2025/22/3 || TI |
| `24772162000106-1-000286/2025-000011` | Municipal/MT | REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL AQUISIÇÃO DE MATERIAIS DE INFORMÁTICA (HARDWARE… | materiais de informatica | https://pncp.gov.br/app/atas/24772162000106/2025/286/11 || TI |
| `14998789000126-1-000007/2026-000001` | Municipal/RJ | Aquisicao de notebooks e computadores completos destinados a garantir o atendimento das d… | computadores | https://pncp.gov.br/app/atas/14998789000126/2026/7/1 || TI |
| `18557546000103-1-000028/2026-000008` | Municipal/MG | Registro de preços para aquisição de materiais de informática, equipamentos eletrônicos e… | materiais de informatica | https://pncp.gov.br/app/atas/18557546000103/2026/28/8 || TI |
| `18128231000140-1-000042/2026-000001` | Municipal/MG | Registro de Preços para futura e eventual aquisição de equipamentos de informática (bens … | equipamentos de informatica | https://pncp.gov.br/app/atas/18128231000140/2026/42/1 || TI |
| `85361863000147-1-000037/2026-000015` | Municipal/SC | REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL AQUISIÇÃO DE EQUIPAMENTOS E SUPRIMENTOS DE INFO… | suprimentos de informatica | https://pncp.gov.br/app/atas/85361863000147/2026/37/15 || TI |
| `18363960000181-1-000050/2026-000003` | Municipal/MG | REGISTRO DE PREÇO de futura e eventual aquisição de equipamentos de informática, periféri… | equipamentos de informatica, tecnologia… | https://pncp.gov.br/app/atas/18363960000181/2026/50/3 || TI (misto) |
| `95725024000114-1-000132/2025-000012` | Municipal/PR | REGISTRO DE PRECO PARA FUTURA E EVENTUAL AQUISICAO DE ELETRO ELETRONICOS E MATERIAL DE IN… | material de informatica | https://pncp.gov.br/app/atas/95725024000114/2025/132/12 || TI |
| `01362680000156-1-000081/2026-000004` | Municipal/MT | REGISTRO DE PREÇOS, PARA FUTURA E EVENTUAL AQUISIÇÃO DE MATERIAIS DE INFORMÁTICA E MATERI… | materiais de informatica | https://pncp.gov.br/app/atas/01362680000156/2026/81/4 || TI |
| `76021450000122-1-000084/2025-000015` | Municipal/PR | Fornecimento de material de informática. | material de informatica | https://pncp.gov.br/app/atas/76021450000122/2025/84/15 || TI |
| `01613052000104-1-000008/2026-000007` | Municipal/PR | REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL AQUISIÇÃO DE EQUIPAMENTOS DE INFORMÁTICA, PERIF… | equipamentos de informatica | https://pncp.gov.br/app/atas/01613052000104/2026/8/7 || TI |
| `15126437000305-1-001370/2025-000001` | Não se aplica/PB | Aquisição de câmeras de sistema de circuito fechado de TV (CFTV) por IP, licenciamento de… | cftv, software | https://pncp.gov.br/app/atas/15126437000305/2025/1370/1 || TI |
| `03277610000125-1-000380/2025-000001` | Federal/DF | Contratação do serviço de link de internet via satélite, utilizando-se terminais transpor… | link de internet | https://pncp.gov.br/app/atas/03277610000125/2025/380/1 || TI |
| `75743377000130-1-000142/2025-000028` | Municipal/PR | Aquisição de computadores, impressoras, multifuncionais e periféricos diversos de informá… | computadores, impressora, telefonia | https://pncp.gov.br/app/atas/75743377000130/2025/142/28 || TI |
| `88811948000178-1-000104/2026-000008` | Municipal/RS | \[Portal de Compras Públicas\] - Futura e eventual aquisição de equipamentos de informática… | computadores, equipamentos de informati… | https://pncp.gov.br/app/atas/88811948000178/2026/104/8 || TI |
| `18303222000149-1-000093/2025-000004` | Municipal/MG | AQUISIÇÃO DE EQUIPAMENTOS DE INFORMÁTICA, ACESSÓRIOS, PERIFÉRICOS E MATERIAIS PERMANENTES… | equipamentos de informatica | https://pncp.gov.br/app/atas/18303222000149/2025/93/4 || TI |
| `92902055000105-1-000042/2025-000001` | Municipal/RS | VALOR REF. CONTRATAÇÃO DE EMPRESA PARA FUTURA E EVENTUAL AQUISIÇÃO DE MATERIAIS E EQUIPAM… | equipamentos de informatica | https://pncp.gov.br/app/atas/92902055000105/2025/42/1 || TI |
| `02231696000192-1-000059/2026-000011` | Não se aplica/RS | \[Portal de Compras Públicas\] - REGISTRO DE PREÇOS PARA AQUISIÇÃO DE EQUIPAMENTOS DE INFOR… | equipamentos de informatica | https://pncp.gov.br/app/atas/02231696000192/2026/59/11 || TI |
| `07954605000160-1-000133/2026-000006` | Municipal/CE | AQUISIÇÕES DE MICROCOMPUTADORES, NOTEBOOKS, CÂMERAS E OUTROS | microcomputador | https://pncp.gov.br/app/atas/07954605000160/2026/133/6 || TI |
| `07684756000146-1-000046/2026-000002` | Municipal/CE | REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL Contratação de uma solução de software completa… | software | https://pncp.gov.br/app/atas/07684756000146/2026/46/2 || TI |
| `18404889000138-1-000022/2026-000007` | Municipal/MG | REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL AQUISIÇÃO DE EQUIPAMENTOS, MATERIAIS E COMPONEN… | videomonitoramento | https://pncp.gov.br/app/atas/18404889000138/2026/22/7 || TI |
| `75972760000160-1-000265/2026-000004` | Municipal/PR | AQUISIÇÃO DE MOVEIS, ELETRODOMÉSTICOS, FERRAMENTAS E EQUIPAMENTOS DE INFORMATICA COM ADOÇ… | equipamentos de informatica | https://pncp.gov.br/app/atas/75972760000160/2026/265/4 || TI (misto) |
| `98661366000106-1-000557/2026-000026` | Municipal/RS | Aquisição de materiais e equipamentos de informática, para todas as Secretarias Municipai… | equipamentos de informatica | https://pncp.gov.br/app/atas/98661366000106/2026/557/26 || TI |
| `75743377000130-1-000142/2025-000005` | Municipal/PR | Aquisição de computadores, impressoras, multifuncionais e periféricos diversos de informá… | computadores, impressora, telefonia | https://pncp.gov.br/app/atas/75743377000130/2025/142/5 || TI |

## Leitura (17/10/2026, R3)

**Antes e depois dos 7 termos novos** (mesma referência ARP; a de antes ainda não tinha as
atas da varredura R2.1):

| | lista de 51 termos (carga das 03:00) | lista de 58 termos (carga `fdc2152e`) |
|---|---|---|
| atas da busca | 7.857 | 17.076 |
| cobertura contra o ARP | 38,3% (de 6.221) | **47,2%** (de 7.761) |
| concordância com o ARP | — | 94,6% (3.664 de 3.872) |

As frases de informática concordam com o ARP em 96% a 100%. Termos testados e **deixados de
fora** por ruído no filtro de frase: `tic`, `materiais de tic` e `equipamentos de tic` (o sufixo
aceita "ticket"/"ticketagem") e `infraestrutura de rede` (redes de água e esgoto).

**O que a cobertura ainda não alcança e por quê:**
- atas que o ARP classifica pelo item ou pelo catálogo (8,4% e 4,0% de cobertura): o objeto é
  genérico ("material de expediente"), então nenhum termo de objeto as encontra. Para essas
  atas, o ARP é a fonte, e a busca não precisa achá-las;
- `informatica` sozinha (933 perdidas) e `tic`/`ti` (544): exigem uma regra melhor que o
  sufixo livre (fronteira de palavra para siglas) ou curadoria (ADR 0026). Decisão do Lucas;
- 755 perdidas têm termo no objeto da ata, mas o PNCP indexa o objeto da compra, ou a ata não
  aparece como vigente na busca. É limite da fonte.

**Precisão:** a concordância é um proxy com correlação lexical (ver acima). A precisão rotulada
depende de o Lucas preencher a amostra de 30 atas acima. Ruído já visto no digest de 17/10:
`impressora` traz pulseira hospitalar com impressora em comodato e filme de raio X; `toner` tem
a menor concordância entre os termos grandes (77%).

## Fechamento (19/10/2026, R3)

**Precisão rotulada:** 30 de 30 atas da amostra só-busca são TI (100%). Rótulo aplicado pelo
Claude sobre o objeto completo e conferido pelo Lucas, seguindo o anexo da IN 05 (como no SIGA,
ADR 0019). Três atas são mistas (TI junto com eletrodomésticos, móveis ou artigos diversos) e,
por decisão do Lucas, contam como TI. A amostra é pequena (30) e só cobre atas fora do ARP;
não mede o ruído dos termos dentro da sobreposição, que aparece na concordância acima.

**Ruído conferido nas atas que o ARP não classifica como TI:**
- `tablet` casava "tablete" (sabão, pastilhas de cloro): o filtro de frase passou a aceitar só
  plural na última palavra (s/es/ns). Na carga ativa, saem 17 "tablete" e 8 grafias erradas
  ("informaticaa", "impressorae").
- `gestao de documentos`: gestão documental pública, não TI. Saiu da lista.
- `impressora` (offset, etiqueta, ribbon) e `toner` (cestas de consumo): ruído aceito pelo Lucas,
  porque o volume de TI real é grande.
- `estacao de trabalho` (mobiliário), `scanner` (body scanner, scanner de parede ou
  odontológico) e `digitalizacao` (gestão documental, reprografia) ficam, com ruído conhecido.
- `videoconferencia`: o desacordo é do ARP; as atas conferidas são de TI.

**Critério 1:** `notebook` no portal aceita 132 atas, e a carga ativa de 17/10 tem 130, todas em
comum (as 2 a mais são novas). A view `v_atas_ti_vigentes` tem 21.038 linhas com
`numero_controle_pncp` e 21.038 valores distintos: nenhuma duplicata entre ARP e busca.
