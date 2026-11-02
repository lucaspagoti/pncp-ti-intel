# 0034 — Esfera, UF e município do ARP pelo cadastro de unidades do PNCP

- Status: aceita pelo Lucas (02/11/2026, plano do MVP funcional).
- Complementa a ADR 0016 (fontes) e a migração 0007, que deixava esses campos nulos no ARP
  "até haver fonte confiável".

## Contexto

As 6.965 atas vigentes do Compras ARP chegavam sem esfera, UF e município, porque a API
`modulo-arp` não traz esses campos. No MVP (ADR 0033), o filtro de esfera e o de UF fazem parte
da tela; sem esses campos, o ARP sumiria de qualquer busca filtrada.

## Decisão

- O id da ata do ARP (`numeroControlePncpAta`) começa pelo CNPJ do órgão, e
  `codigoUnidadeGerenciadora` é o código da unidade no PNCP. A sondagem de 02/11/2026 achou
  15 de 15 unidades e depois 248 de 248, todas com esfera e UF.
- `GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/unidades/{codigo}` dá a esfera
  (`orgao.esferaId`), a UF e o município. Se a resposta for 404, `GET /v1/orgaos/{cnpj}` dá só
  a esfera. Tradução: F Federal, E Estadual, M Municipal, D Distrital, N "Não se aplica"
  (a mesma da busca PNCP).
- Um cliente fino (`fontes/unidades.py`) faz as consultas, com timeout, três tentativas, 4
  requisições/s e teto de 1 MB por resposta. O `compras-mcp` não cobre esse endpoint.
- Cache em `unidades_gerenciadoras (cnpj, codigo)` por 30 dias, com até 1.500 consultas por
  carga; o restante fica para a próxima. A primeira carga consulta cerca de 1.000 unidades, uns
  4 minutos.
- É enriquecimento, então nunca derruba a carga: falha de rede ou de contrato deixa os campos
  nulos, ou usa o cache vencido. As contagens `unidades_*` ficam em `cargas.contagens`.

## Consequências

- O filtro de esfera e UF passa a valer para o ARP a partir da primeira carga depois do deploy.
- A web mostra "Não informada" quando a esfera é nula (unidade sem cadastro ou falha de consulta).
- Se o contrato mudar, aparece `unidades_consulta_falhou` no log e cresce `unidades_falhas`; o
  teste de contrato (`tests/test_unidades.py`) usa respostas reais recortadas.
