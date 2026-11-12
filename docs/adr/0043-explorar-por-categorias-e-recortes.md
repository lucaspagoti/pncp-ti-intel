# 0043 — Explorar sem buscar: categorias e recortes na home

- Status: aceita pelo Lucas (12/11/2026), depois de comparar seis opções num HTML interativo
  (botão, categorias, recortes, mapa por UF e a combinação de categorias com recortes).
- Complementa as ADRs 0036, 0039 e 0042.

## Contexto

A home só tinha a busca. Quem chegava sem saber o nome do item não tinha por onde começar, e a lista
completa ficava num link "Ver todas as atas" no rodapé, depois da frase das fontes. Abrir essa lista
leva a 20 mil atas sem ponto de partida.

## Decisão

1. **Home com duas portas além da busca.** Uma grade de 8 categorias de TI, com ícone e número de atas,
   no lugar das pílulas de exemplo; e uma faixa de recortes prontos embaixo: "Vencem em 30 dias",
   "Entraram nesta semana", "PRODERJ", "Rio de Janeiro" e "Todas as atas". O link do rodapé sai; a
   lista completa passa a ser o último recorte. A busca continua no centro e no foco. Sem token novo:
   os cartões e as pílulas usam os valores da ADR 0039, e só "Vencem em 30 dias" leva a cor `--warn`.
2. **Categoria é um filtro, `categoria=<slug>`.** Uma categoria reúne vários termos (Rede e segurança:
   switch, roteador, firewall, access point), e o `q` aceita um termo só. O filtro reaproveita a busca:
   - sem `q`, os termos da categoria são as `alternativas` (ranking, marcação do item e preço do item
     que casa funcionam como numa busca digitada);
   - com `q`, a busca vale dentro da categoria (condição extra: o documento casa com algum termo dela).
   Slug fora da lista vira vazio, como os outros filtros fechados. A categoria aparece como pílula e
   segue num campo oculto do formulário, para não se perder quando outro filtro muda.
3. **As categorias são um insumo que o Lucas revisa**, `insumos/categorias_busca.txt`
   (`slug | Rótulo | termo = termo`), lido como o `sinonimos_busca.txt`. Lista inicial: Impressão,
   Suporte e manutenção, Rede e segurança, Computadores, Licenças de software, Monitores, Servidores e
   armazenamento e Periféricos. Videomonitoramento e Telefonia ficaram de fora a pedido do Lucas.
   "Servidores" usa só frases, porque "servidor" sozinho casa com servidor público.
4. **Dois filtros de data para os recortes**: `vence_ate` (`fim <= data`) e `desde`
   (`primeira_vez_vista >= data`). O `vigente_ate` existente é o contrário e continua como está. Os dois
   ganham pílula ("Vence até", "Novas desde") e campo oculto, sem controle novo na lateral.
5. **Contagens da home numa consulta só** (total, recortes e uma por categoria), calculadas a cada
   visita sobre `v_busca_atas`: cerca de 100 ms na base de 12/11/2026. Sem migração, sem view nova e
   sem cache; se a base crescer, entra um cache por carga.

## Consequências

- Mudar uma categoria é editar o arquivo e reiniciar a web (a leitura é guardada em memória); o número
  da home e o da lista vêm da mesma busca e sempre batem.
- "Entraram nesta semana" depende de `atas_vistas`: ata sem registro de primeira vista não aparece.
- Os filtros novos valem também para a exportação CSV, que usa a mesma consulta da lista.
- Fica fora, por ora: mapa por UF (exigiria cinco tons novos de azul e uma ADR própria) e o botão
  "Explorar" isolado (leva à lista inteira sem ponto de partida).
