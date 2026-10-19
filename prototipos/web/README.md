# Protótipo da web

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
  com `var(--navy)`.

## Componentes usados

Aparência de sistema, não de painel: barra fina no topo, filtros numa lateral e resultados numa
tabela. Cor só para ação (`navy`) e alerta (`warn`, `crit`).

| Tela | Componente do design system |
|---|---|
| Barra do topo com a data dos dados | Band, reduzida a barra (sem marca) |
| Filtros | Forma da SideNav (painel com régua), com rótulos do Controls; no celular, recolhe sem JS |
| Lista de atas e itens | Tabela com cabeçalho em versalete `muted` e separação por borda |
| "51 dias", "13 dias" | Chip `warn` (31 a 90 dias) e `crit` (até 30 dias) |
| "Itens" no detalhe | SectionTitle |
| Notas | Bloco de nota (`footnote-bg`) |

## Desvios do design system, todos para cumprir as regras dele

- Borda de controle em `--muted` (5,47:1), e não em `--border` (1,4:1), pelo piso de 3:1.
- Chip `warn` com fundo `--panel` e borda `--warn` (4,87:1). O preview usa `warn` a 13% de
  fundo, e o texto mede 4,11:1. Chip `crit` na mesma forma (6,54:1) para até 30 dias.
- Abaixo de 600px, as tabelas viram linhas empilhadas, para o preço unitário não sumir na rolagem.
