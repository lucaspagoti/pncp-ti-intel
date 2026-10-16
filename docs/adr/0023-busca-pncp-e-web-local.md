# 0023 — Busca PNCP por termos (R3) e web local (R4)

- Status: aceita (16/10/2026). Implementa as ADRs 0016 e 0018.

## Decisões

**R3, busca PNCP**
- Uma consulta por termo de `insumos/termos_ti.txt` (`tipos_documento=ata`, `status=vigente`,
  500 por página), 2 requisições/s, retry com backoff (o portal derruba conexões e devolve corpo
  vazio de forma intermitente). Termo que esgota as tentativas é contado e registrado; mais de 20%
  de termos falhos derruba a carga. Mudança de contrato (`items`/`total`/campos) falha alto.
- **Filtro de precisão local:** o portal casa por palavra solta (`equipamentos de informatica`
  devolveu 32 mil atas, quase todas mobiliário e obras; a primeira carga real publicou 20 mil atas
  falsas de TI). Só entra a ata cujo objeto contém o **termo inteiro como frase** (sem acento nem
  caixa, última palavra com sufixo). Termos genéricos saíram da lista. Termo que falha ganha uma
  segunda passada no fim da carga.
- A busca não traz itens nem preço. Toda ata achada entra com `is_ti = true` e
  `motivo_ti = termo_pncp:<termos>`. É recall por termo: **a precisão depende da lista de termos**,
  que o Lucas revisa. Nenhum recall nacional é alegado (ADR 0016, D6).
- Dedupe com o ARP na view (migração 0007): a ata da busca some quando o ARP ativo tem a mesma
  `numero_controle_pncp` como ata de TI vigente. Se o ARP a viu mas não a classificou como TI, a
  busca a mantém (é justamente o furo de recall do ARP, 59%). SIGA não é deduplicado (não tem o
  número de controle).
- `atas` ganha `esfera`, `uf` e `municipio`. A busca preenche; o SIGA é `Estadual`/`RJ` derivado na
  view; **o ARP fica nulo** (a API de atas não os traz). Os filtros de esfera e UF da web, portanto,
  não alcançam as atas do ARP, a menos que a mesma ata apareça na busca.

**R4, web**
- FastAPI + Jinja2 + HTMX (htmx 2.0.4 vendorizado em `static/`, sem CDN, CSP `script-src 'self'`).
- Papel `web_reader` (migração 0008, senha `PNCP_TI_WEB_PASSWORD`): SELECT só em
  `v_atas_ti_vigentes`, `v_ata_itens_ti`, `v_ata_consumo_item` e `v_busca_atas`. Conexões
  somente leitura, `statement_timeout` de 8 s.
- Busca: `to_tsvector('portuguese')` sobre `unaccent(lower(objeto + órgão + itens))` com
  `websearch_to_tsquery`. Consultas fixas e parametrizadas; ordenação e filtros vêm de listas
  fechadas. O `LIKE` do órgão escapa `%`, `_` e `\`.
- Desvio da ADR 0018: **sem `pg_trgm` na consulta** e sem índice. Com ~6 mil atas a busca leva
  ~1,5 s, aceitável para uso pessoal. A extensão `pg_trgm` foi instalada e o índice GIN
  (materializando `texto_busca`) é o próximo passo se a base crescer.
- CSV com fórmulas neutralizadas (mesmo critério de `classificar/amostra.py`), limitado a 5.000
  linhas. Autoescape ligado; link de origem só vira `href` se for `http(s)`.
- Cabeçalhos: CSP restritiva, `nosniff`, `no-referrer`, `X-Frame-Options: DENY`, `no-store`;
  `TrustedHost` (`WEB_ALLOWED_HOSTS`); `/docs` e OpenAPI desligados.

## Consequências

- A web só mostra o que as views mostram; o preço unitário existe só onde há itens (SIGA e ARP).
- Quem edita `termos_ti.txt` muda o conteúdo da base na próxima carga. A queda de volume > 50%
  entre cargas não publica (como nas outras fontes).
