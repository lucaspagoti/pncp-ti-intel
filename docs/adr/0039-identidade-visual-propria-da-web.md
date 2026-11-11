# 0039 — Identidade visual própria da web e redesenho da busca

- Status: aceita pelo Lucas (10/11/2026, ao aprovar o protótipo da W4).
- Substitui, para a web, o design system PGE Ajuda. Altera o escopo do MVP da ADR 0033.

## Contexto

Com a primeira release em produção (W2 e W3), o Lucas avaliou o estilo e a UX e não ficou
satisfeito. Pediu algo limpo, profissional e minimalista, com a Apple como referência de tom, e
cartões arredondados, com animação onde ela ajuda.

O design system PGE Ajuda descreve um relatório mensal impresso de outra instituição: Calibri,
raio de no máximo 10 px, separação por borda, sem movimento. Na web isso resultou em:

- tudo em negrito: título, preço, rótulos e opção marcada competem;
- contorno escuro em todo controle, pílula e selo de vencimento;
- corpo de 13,8 px em Calibri, que só existe no Windows;
- tabela larga onde o conteúdo é um registro por linha; no celular ela vira "Fonte: / Vigência: /
  Preço unitário:";
- home que lista as 20 mil atas sem termo, com 20 selos vermelhos de "vence hoje";
- filtros com duas mecânicas (rádio aplica sozinho; texto e data pedem "Aplicar filtros");
- detalhe com lateral quase vazia e o critério de TI interno ("III-computadores:notebook@objeto")
  com o mesmo peso dos dados.

Em 10/11/2026 o Lucas decidiu que a web pode ignorar o PGE Ajuda.

## Decisão

1. **Identidade própria.** Os valores ficam em `prototipos/web/tokens.css`, escrito à mão, e a web
   carrega uma cópia idêntica. Nenhum outro CSS tem hex, `rgba` ou tamanho de fonte avulso.
   `scripts/gerar_tokens_css.py` sai (dependia do `tokens.json` do PGE, fora do Git).
   - Cor: fundo `#f5f5f7`, superfície branca, tinta `#1d1d1f` e `#636366`, um acento só
     (`#1456d6`, ação e foco); `warn` e `crit` só para prazo. Contrastes anotados no arquivo.
   - Tipo: fonte do sistema (San Francisco no Mac e no iPhone, Segoe no Windows), sem arquivo
     embarcado e sem mudar a CSP; escala 13/15/17/22/28/40 px; pesos 400 e 600.
   - Forma: raio 10 (controle), 16 (cartão) e pílula; separação por espaço e fundo, uma sombra
     de repouso e uma de elevação.
   - Movimento: uma curva e duas durações (180 e 320 ms), só transições CSS; desligado em
     `prefers-reduced-motion`.
2. **Home de busca.** Sem filtro, `/` mostra o campo em destaque, buscas de exemplo, o total e a
   data dos dados. A lista aparece ao buscar ou filtrar; "Ver todas as atas" abre a lista sem
   filtro.
3. **Resultados em cartões.** Cada ata é um cartão: objeto, linha "órgão · esfera e UF · fonte",
   item que casou com o termo e, à direita, o preço (único número em destaque), a nota "no item
   buscado" e o prazo. O prazo é texto: "até DD/MM/AAAA"; com ponto colorido e "vence em N dias"
   só a 90 dias (`warn`) ou 30 (`crit`). O total vira o título ("315 atas vigentes") e a busca
   fica fixa no topo.
4. **Filtros com uma mecânica.** Todo filtro aplica sozinho (texto com espera de 500 ms);
   "Aplicar filtros" sai; um "Limpar" só.
5. **Detalhe em coluna única.** Voltar e ações no topo, título, cartão-resumo (órgão, local,
   vigência, valor total), cartão de itens (a tabela rola dentro do cartão) e "Sobre este registro" com nº de
   controle, motivo de ser TI, primeira vez vista e data dos dados, em texto secundário.
6. **Seleção de filtro evidente.** A opção marcada fica com fundo azul sólido, texto branco e
   marcador de rádio preenchido; as outras mostram o anel vazio. Campo de texto preenchido ganha
   borda azul. O rádio cobre a linha inteira (invisível), então o toque e o E2E acertam a opção.
7. **Dispensar só o que o leitor não precisa ver de novo.** O aviso de dados públicos fecha com
   animação e não volta (lembrado no `localStorage`, nunca no servidor: a web continua só
   leitura), e a pílula de filtro sai com animação ao ser removida. Ocultar atas da lista foi
   testado no protótipo e descartado em 10/11/2026: o cartão inteiro já abre a ata e ocultar não
   ajuda a decidir. Com o armazenamento bloqueado, o aviso só volta a cada visita.

## Consequências

- A regra do `CLAUDE.md` que mandava seguir o PGE Ajuda deixa de valer para esta web.
- Fonte do sistema muda por aparelho. Em Linux sem San Francisco nem Segoe cai em fonte genérica
  (como no homelab e no CI). Se incomodar, embarcar uma fonte exige `font-src 'self'` na CSP.
- Planejada em três fases (`docs/ROADMAP-WEB.md`), entregue num PR só a pedido do Lucas, que
  aprovou o protótipo (W4) e quis o front novo em produção: protótipo, esta ADR e a web (W5 e W6).
  O aceite e o "sim" do merge continuam dele.
