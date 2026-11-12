# 0042 — Abas "Todas | PRODERJ" e link da contratação no site do PRODERJ

- Status: aceita pelo Lucas (11/11/2026), depois de comparar as opções num HTML interativo
  (filtro: abas sobre a lista; botão: com a nota quando não consta).
- Complementa as ADRs 0016, 0019 e 0039.

## Contexto

O PRODERJ é o órgão com que o Lucas mais tem vínculo (contratos e caronas). As atas dele já entram no
portal pelo SIGA RJ (24 vigentes em 11/11/2026), mas só se acham digitando "PRODERJ" em Órgão, e a ata
não leva à página da contratação em `rj.gov.br/proderj/licitacoes`, onde ficam o edital, a ata assinada
e os demais documentos.

O site do PRODERJ não tem API. As licitações ficam em seis listas HTML (`homologadas`, `andamento`,
`realizadas`, `canceladas`, `desertas`, `fracassadas`), paginadas com `?items_per_page=50&page=N`. Cada
processo é uma página `node/N` e o título traz o número do processo SEI (`SEI-430002/000030/2024`),
em grafias variadas. O CSV do SIGA traz o mesmo número no campo `processo`. Cruzando os dois, os 19
processos das 24 atas vigentes tinham página no site (19 de 19).

## Decisão

1. **Vigência e dados continuam do SIGA.** O site do PRODERJ só dá o endereço da página. Não se
   guarda status do site, nem lista de documentos, nem "ata disponível", nem contratações em
   andamento, canceladas, desertas ou fracassadas: a base segue só de atas vigentes (AGENTS.md).
2. **Fonte nova `proderj`** (`fontes/proderj.py`): lê as seis listas, extrai `(node, título)` do campo
   `views-field-title`, normaliza o processo SEI do órgão `430002` e grava um link por processo em
   `proderj_links`, preso a uma carga (`cargas.fonte = 'proderj'`) com troca atômica. Quando o mesmo
   processo está em duas listas (pregão fracassado e refeito), vale a lista de maior prioridade
   (`homologadas` > `andamento` > `realizadas` > demais) e, nela, o `node` mais novo.
3. **Casamento em SQL.** `proderj_processo(texto)` (migração **0012**) tem a mesma regra do Python
   (`normalizar_processo`); os testes comparam as duas. `v_ata_proderj` liga cada ata do SIGA gerenciada
   pelo PRODERJ à URL da carga ativa, por qualquer processo da ata, e devolve URL nula quando não consta.
   É a única coisa nova que o `web_reader` lê. `v_cargas_web` deixa de listar `proderj`, para o rodapé
   "Dados de" não recuar por causa de link.
4. **Só o título.** Título sem o número SEI (processos antigos, de outros órgãos) fica de fora; não se
   abre cada `node` para procurar o número no corpo (centenas de requisições por dia, sem ata vigente
   que dependa disso). Se uma ata nova aparecer sem link, o botão sai desativado e o caso se vê no teste
   de contrato e na validação (`--validar`).
5. **Piso e contrato.** Falha sem publicar e mantém os links anteriores se: a lista de homologadas vem
   vazia ou nenhum processo SEI é reconhecido (`contrato`: o HTML mudou); a coleta cai abaixo de 50% da
   carga ativa (`queda_volume`); há mais de 10 páginas numa lista; página acima de 8 MiB; ou o site não
   responde após 3 tentativas (`rede`/`http`). Os tipos já têm frase no alerta do WhatsApp (ADR 0032).
6. **Carga diária.** `scripts/carga_diaria.sh` roda `proderj` logo depois do SIGA, com a mesma nova
   tentativa no fim para saída 1. `operacao.FONTES_CARGA` ganha "a lista do PRODERJ". A fonte não entra
   no alerta de dado velho: link não vence.
7. **Web.** Controle segmentado "Todas as atas | PRODERJ" sobre a lista (opção C do comparador), um
   grupo de rádio `escopo=proderj` que aplica sozinho pelo HTMX, entra na exportação CSV e some quando
   não há atas do PRODERJ. As duas contagens seguem os demais filtros. Predicado único:
   `fonte = 'siga_rj' AND unidade_gerenciadora ILIKE 'PRODERJ%'`. Não vira pílula de filtro, porque a
   própria aba mostra o escopo.
8. **Botão no detalhe** (opção B): "Ver no site do PRODERJ", em azul, com rótulo, `target="_blank"` e
   `rel="noopener noreferrer"`; só aceita `https://www.rj.gov.br/proderj/` (filtro `url_proderj`, e
   `CHECK` no banco). Se a contratação não consta: o mesmo botão, desativado (`aria-disabled`, fora da
   ordem de foco, fundo `--sutil`, texto `--ink-2`), "Não consta no site do PRODERJ", e uma nota
   "Não achamos esta contratação em rj.gov.br/proderj/licitacoes. Confira no SIGA." Nenhum token novo.
9. **Rede.** Cliente `httpx` fino, com timeout de 30 s, 3 tentativas, limite de tamanho e nome genérico
   de cliente (`pncp-ti-intel/1.0`); leitura só de páginas públicas, sem credencial.

## Consequências

- O texto do site é dado de terceiros: o título só vira texto escapado no banco e nunca aparece na web
  (a tela usa apenas a URL, validada).
- Se o PRODERJ mudar o HTML das listas, a carga falha com `contrato`, avisa numa frase e os links
  anteriores continuam valendo; o ajuste é no regex `_LINK` e na fixture de `tests/fixtures/proderj/`.
- Ata do PRODERJ que ainda não saiu em nenhuma lista, ou cujo título não traz o processo, fica com o
  botão desativado até o site publicar.
- Outros órgãos podem ganhar a mesma aba depois, mas isso é decisão nova: o predicado e o casamento
  hoje são do PRODERJ.
