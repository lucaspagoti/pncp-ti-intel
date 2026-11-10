# Protótipo da web

Referência visual e de escopo da web (ADR 0033), com a identidade própria da ADR 0039. Telas
estáticas, dados de exemplo, sem backend:

- `index.html` — home: a busca em destaque, exemplos e a data dos dados;
- `resultados.html` — busca por "notebook" com filtro: cartões de ata, filtros na lateral
  (recolhidos no celular), pílulas, aviso e paginação;
- `ata.html` — detalhe em coluna única.

Abra `index.html` no navegador. Sem estilo inline nem script inline, como exige a CSP da web
(`style-src 'self'`, `script-src 'self'`).

## Arquivos

- `tokens.css` — única fonte dos valores (cor, tipo, espaço, raio, sombra, movimento), com o
  contraste medido de cada cor. A web usa uma cópia idêntica em `src/pncp_ti/web/static/`.
  Valor novo entra aqui, com o contraste quando for cor; nenhum outro CSS tem hex ou `rgba`.
- `prototipo.css` — só `var(--token)`.
- `prototipo.js` — dispensar com animação interrompível; vira parte do `app.js` da web na W6.

## Princípios

- **Um acento só.** Azul para ação e foco. `warn` e `crit` só para prazo, e só a 90 e 30 dias.
- **Um número em destaque por cartão.** O preço é o único texto em 22 px; o resto é 13 a 17 px.
  Dois pesos: 400 e 600.
- **Separação por espaço e fundo.** Cartão branco sobre `--bg`, sombra de repouso; a elevação
  (`--shadow-lift`) marca o cartão sob o cursor e o aviso de Desfazer. Borda só em controle
  (3:1) e fio de tabela.
- **Movimento que se pode interromper.** Só transições CSS, que voltam do ponto em que estão
  quando a classe sai. Uma curva, duas durações; nada se move com `prefers-reduced-motion`.

## Dispensar

| O quê | Como | Volta |
|---|---|---|
| Ata do resultado | botão × (ou arrastar para o lado no toque) | "Desfazer" no aviso, por 6 s; "Mostrar" na barra |
| Aviso de dados públicos | botão × | não volta; o mesmo texto fica no rodapé do detalhe |
| Filtro ativo | × da pílula | a pílula sai e a lista troca |

- O bloco fecha com a linha da grade indo de `1fr` a `0fr`: nada é medido em JS.
- O gesto move o cartão pela propriedade `--dx` (CSSOM, permitido pela CSP).
- Atas ocultas e avisos fechados ficam no `localStorage` (`pncp-ti:atas-ocultas`,
  `pncp-ti:avisos-fechados`); sem armazenamento, nada é lembrado e nada quebra.
- Pelo teclado, ocultar leva o foco ao "Desfazer"; Esc fecha o aviso.
