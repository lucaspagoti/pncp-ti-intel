# Insumos — o que só você pode fornecer

O Claude Code consegue buscar tudo o que é público. Estes insumos dependem do seu conhecimento da PGE-RJ.

| Arquivo | Quando é necessário | O que fazer |
| --- | --- | --- |
| `contratos_ti_pge.csv` | **Antes da Fase 1** | Liste os contratos e atas de TI da PGE-RJ vigentes ou encerrados nos últimos 12 meses. É o gabarito para medir a cobertura do PNCP. |
| `perguntas_reais.csv` | Antes da Fase 4 | Complete até 20 perguntas que você realmente faz no trabalho. Já há algumas sugestões para revisar. |
| `amostra_rotulada.csv` | Fase 3 | Não preencha agora. O sistema gera a amostra; você marca o que é TI. |
| `normas/` | Antes de usar pesquisa de preços em processo (D5) | Coloque o regulamento estadual de pesquisa de preços aplicável ao RJ e normas internas de contratação de TI que quiser como referência. |
| Design system da PGE | Fase 6 (painel opcional) | Aponte onde estão os tokens/arquivos do design system usado nos outros painéis. |

## Cuidados

- **Não inclua dados pessoais** (CPF, nomes de servidores, fiscais) nestes arquivos.
- `contratos_ti_pge.csv` tem só dados que já são públicos no PNCP ou deveriam ser; mesmo assim, ele fica fora do Git por padrão (`.gitignore`). Mude isso só se o repositório for institucional.
- Não coloque documentos internos (pareceres, minutas não publicadas) nesta pasta. A base é só de dados públicos (ver ADR 0001 e README).

## Formato

CSV separado por vírgula, UTF-8, primeira linha = cabeçalho. Datas em `AAAA-MM-DD`. Valores com ponto decimal, sem "R$".
