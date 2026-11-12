# Protótipo da web

Referência visual e de escopo da web (ADR 0033), com a identidade própria da ADR 0039. Telas
estáticas, dados de exemplo, sem backend:

- `index.html` — home: a busca em destaque, a grade de 8 categorias, a faixa de recortes e a data dos dados (ADR 0043);
- `resultados.html` — busca por "notebook" com filtro: cartões de ata, filtros na lateral
  (recolhidos no celular), pílulas, aviso e paginação;
- `ata.html` — detalhe em coluna única;
- `ata-proderj.html` e `ata-proderj-sem-pagina.html` — detalhe de uma ata do PRODERJ com o botão
  "Ver no site do PRODERJ" e, quando a contratação não consta no site, o mesmo botão desativado
  com a nota embaixo (ADR 0042). O controle "Todas as atas | PRODERJ" fica sobre a lista, em
  `resultados.html`.

Abra `index.html` no navegador. Sem estilo inline nem script inline, como exige a CSP da web
(`style-src 'self'`, `script-src 'self'`).

## Arquivos

- `tokens.css` — única fonte dos valores (cor, tipo, espaço, raio, sombra, movimento), com o
  contraste medido de cada cor. A web usa uma cópia idêntica em `src/pncp_ti/web/static/`.
  Valor novo entra aqui, com o contraste quando for cor; nenhum outro CSS tem hex ou `rgba`.
- `prototipo.css` — só `var(--token)`; carrega a Inter de `src/pncp_ti/web/static/fonts/` (ADR 0040).
- `prototipo.js` — fechar o aviso e remover pílulas com animação; vira parte do `app.js` da web na W6.

## Princípios

- **Um acento só.** Azul para links e foco; o botão de busca é grafite, dentro do campo. `warn` e `crit` só para prazo, e só a 90 e 30 dias.
- **Um número em destaque por cartão.** O preço é o único texto em 22 px; o resto é 13 a 17 px.
  Dois pesos: 400 e 600.
- **Separação por espaço e fundo.** Cartão branco sobre `--bg`, sombra de repouso; a elevação
  (`--shadow-lift`) marca o cartão sob o cursor e o cursor sobre a ata. Borda só em controle
  (3:1) e fio de tabela.
- **Seleção que se vê, sem cor.** A opção de filtro marcada é uma pílula branca com sombra leve e peso 500
  (ADR 0040); campo de texto preenchido ganha borda azul.
- **Centro em tela larga.** Lateral e lista ficam juntas no meio da tela (`--casca`, ADR 0044); a
  lista não passa de `--coluna`.
- **Movimento curto.** Só transições CSS, uma curva, duas durações; nada se move com
  `prefers-reduced-motion`.

## Dispensar

| O quê | Como | Volta |
|---|---|---|
| Aviso de dados públicos | botão × | não volta; o mesmo texto fica no rodapé do detalhe |
| Filtro ativo | × da pílula | a pílula sai e a lista troca |

- O aviso fecha com a linha da grade indo de `1fr` a `0fr`: nada é medido em JS.
- Aviso fechado fica no `localStorage` (`pncp-ti:avisos-fechados`); sem armazenamento, nada é
  lembrado e nada quebra.
- O cartão de ata não tem botão de ocultar: ele inteiro é o link para o detalhe.
