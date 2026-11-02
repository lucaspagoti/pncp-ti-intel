# Protótipo da web

Este protótipo é o MVP da web (ADR 0033).

Duas telas estáticas, com dados de exemplo e sem backend: `index.html` (busca) e `ata.html`
(detalhe). Servem de referência visual para a web real (`src/pncp_ti/web/`).

- Abra `index.html` no navegador. Não há JS nem estilo inline, o que é compatível com a CSP da web
  real (`style-src 'self'`).
- `tokens.css` é gerado; não edite. Os valores vêm do design system de referência, que fica fora do
  Git em `insumos/design-system/`:

  ```
  uv run python scripts/gerar_tokens_css.py             # regenera
  uv run python scripts/gerar_tokens_css.py --verificar # confere
  ```

- `prototipo.css` usa só `var(--token)`. Tema único, claro; fonte do sistema (`--font-sans`),
  sem arquivo embarcado.
- `tokens-projeto.css` cobre as lacunas do design system com tokens derivados dos dele, sem
  valor novo: `--on-navy`, `--control-border`, `--chip-warn-*`, `--band-badge-bg`, os marcadores
  com `var(--navy)`, a escala de sombra `--shadow-1` a `--shadow-3` (tingida de `navy-dark` por
  `color-mix`), `--anel-foco` e `--linha-realce`.

## Componentes usados

Casca de sistema: lateral clara sobre `--bg` e uma folha de trabalho branca flutuante. Cor só para
ação (`navy`) e alerta (`warn`, `crit`); profundidade por `--shadow-1` (controles), `--shadow-2`
(folha) e `--shadow-3` (= `shadow-pop`, menus).

| Tela | Componente do design system |
|---|---|
| Lateral com marca, filtros e o corte no rodapé | SideNav (anatomia: marca no topo, grupos, rodapé) |
| "Nesta ata" no detalhe | Itens âncora da SideNav, com `aria-current` |
| Filtros ativos ("Termo", "Vigente até") | Pílulas na forma do Chip, removíveis |
| Lista de atas e itens | Tabela com cabeçalho `muted` e separação por borda |
| "vence em 51 dias", "vence em 13 dias" | Chip `warn` (31 a 90 dias) e `crit` (até 30 dias) |
| Notas | Bloco de nota (`footnote-bg`) |

## Desvios do design system

- Sombra suave na folha, nos controles e nos botões, a pedido. O DS reserva sombra para
  `shadow-pop`; aqui a borda de 1px continua separando, e a sombra só dá profundidade.

- Borda de controle em `--muted` (5,47:1), e não em `--border` (1,4:1), pelo piso de 3:1.
- Chip `warn` com fundo `--panel` e borda `--warn` (4,87:1). O preview usa `warn` a 13% de
  fundo, e o texto mede 4,11:1. Chip `crit` na mesma forma (6,54:1) para até 30 dias.
- Abaixo de 600px, as tabelas viram linhas empilhadas, para o preço unitário não sumir na rolagem.
