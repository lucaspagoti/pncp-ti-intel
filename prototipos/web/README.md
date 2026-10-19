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

## Componentes usados

| Tela | Componente do design system |
|---|---|
| Faixa do topo com a data dos dados | Band (sem marca) |
| Filtros | Controls: segmentado para fonte e esfera, `select` para UF e ordenação |
| "vence em N dias", "sem itens nesta fonte", fonte da ata | Chip (`warn` e neutra) |
| "325 atas encontradas", "Itens" | SectionTitle |
| Régua de vigência | Trilha de barra da LocationRow, com a marca de hoje |
| Ficha da ata e notas | Bloco de nota (`footnote-bg`) |

## Desvios do design system, todos para cumprir as regras dele

- Borda de controle em `--muted` (5,47:1), e não em `--border` (1,4:1), pelo piso de 3:1.
- Chip `warn` com fundo `--panel` e borda `--warn` (4,87:1). O preview usa `warn` a 13% de
  fundo, e o texto mede 4,11:1.
- Abaixo de 600px, a tabela de itens vira blocos, para o preço unitário não sumir na rolagem.
