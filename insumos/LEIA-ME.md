# Insumos — o que só você pode fornecer

O Claude Code consegue buscar tudo o que é público. Estes insumos dependem do seu critério pessoal
(projeto sem vínculo institucional, ADR 0011).

| Arquivo | Quando é necessário | O que fazer |
| --- | --- | --- |
| `perguntas_reais.csv` | Antes de iniciar a Fase 3, depois do aceite da F2 | Revise as sugestões antigas (algumas tratam de contratos/preços/anexos fora do escopo disponível) e complete 20 perguntas que você realmente faria sobre atas vigentes de TI. Não inclua dados pessoais. |
| `amostra_rotulada.csv` | Fase "Filtro de TI e preços" | Não preencha agora. O sistema gera a amostra; você marca o que é TI. |
| `normas/` | Opcional, só se quiser usar pesquisa de preços pra alguma decisão formal | Coloque normas de pesquisa de preços ou de contratação de TI que você queira como referência. Não bloqueia nenhuma fase. |
| Design system pessoal | Fase "Operação" (painel opcional) | Aponte onde estão os tokens/arquivos do design system, se você tiver um. |

## Cuidados

- **Não inclua dados pessoais** (CPF, nomes de servidores, fiscais) nestes arquivos.
- Não coloque documentos internos (pareceres, minutas não publicadas) nesta pasta. A base é só de dados públicos (ver ADR 0001 e README).

## Formato

CSV separado por vírgula, UTF-8, primeira linha = cabeçalho. Datas em `AAAA-MM-DD`. Valores com ponto decimal, sem "R$".
