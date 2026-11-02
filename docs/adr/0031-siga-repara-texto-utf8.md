# 0031 — SIGA RJ repara texto UTF-8 dentro do cp1252 e aceita arquivo inteiro em UTF-8

- Status: aceita pelo Lucas (02/11/2026).
- Altera a ADR 0019 (validação de codificação dos CSVs do SIGA RJ). Vale também, de forma
  preventiva, para o texto da ARP e da busca PNCP.

## Contexto

Desde 29/10/2026 a carga diária falha todo dia. O `PARTICIPANTES_ATAS_REGISTRO_PRECO.CSV`
continua em cp1252, mas o nome de uma única unidade nova ("SEIJES - Secretaria de Estado
Intergeracional de Juventude e Envelhecimento Saudável", 44 linhas) chega gravado em UTF-8 e
aparece como "SaudÃ¡vel". A validação recusava o arquivo inteiro na primeira ocorrência
(`codificacao`), e o SIGA ficou parado na carga de 28/10. O erro está na origem, sem prazo
para correção.

A mesma regra também derrubaria a carga em casos parecidos: uma maiúscula acentuada em UTF-8
(`Á` e `Í` viram bytes indefinidos em cp1252), pontuação tipográfica em UTF-8 (`â€“`), texto
codificado duas vezes ou o SIGA passar a publicar o arquivo inteiro em UTF-8.

## Decisão

- `pncp_ti.codificacao.reparar` troca cada sequência UTF-8 lida como cp1252 (`Â`/`Ã` mais um
  byte de continuação, ou `â€`/`â‚` mais um byte de continuação) pelo caractere original, em
  até 3 passadas. Bytes indefinidos em cp1252 entram como *surrogate* para que `Ã`+0x81 vire
  `Á`. Pontuação logo depois de `Ã`/`Â` (`MAÇÔ`) só é reparada se vier uma letra a seguir.
- O SIGA lê UTF-8 (com ou sem BOM) quando o arquivo inteiro decodifica em UTF-8; caso
  contrário lê cp1252. O reparo vale nos dois casos. O cabeçalho, que tem acentos, continua
  conferido e pega uma leitura com a codificação errada.
- Continuam falhando com `codificacao`: um byte indefinido que não faz parte de uma sequência
  reparável e mais de 1% das linhas (`LIMITE_TEXTO_QUEBRADO`) com texto quebrado que sobrou
  depois do reparo.
- `cargas.contagens` registra `reparos_codificacao`, `trechos_nao_reparados` e
  `arquivos_utf8`; o log registra `siga_texto_reparado` (warning).
- O reparo acontece antes do cálculo das chaves. A chave de um participante com o nome
  reparado é igual à do nome que o SIGA publicar já corrigido: a troca não gera
  "novidades" nem órfãos.
- ARP e busca PNCP passam o texto pelo mesmo reparo em `_texto`, sem contador (em 02/11/2026
  não havia nenhum caso no banco).

## Consequências

- Um valor quebrado na origem deixa de parar o SIGA inteiro; a web mostra o texto corrigido.
- Quando o SIGA corrigir a origem, nada muda deste lado: o contador volta a 0 e as chaves
  continuam as mesmas.
- Texto legítimo com `Ã`/`Â` seguido de símbolo da faixa 0x80–0xBF do cp1252 seria reparado
  por engano. Isso não acontece em português (depois de `Ã`/`Â` vem letra ASCII) e a
  pontuação tem a proteção acima.
- Uma mudança real de formato continua derrubando a carga pelo cabeçalho, pelas colunas ou
  pelo limite de 1%.
