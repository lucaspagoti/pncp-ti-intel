# 0019 — Carga do SIGA RJ e critério de TI (IN PRODERJ 05/2024)

- Status: aceita (13/10/2026). Decisão do Lucas: **seguir o Anexo Único da IN 05**, inclusive nas
  três categorias que contrariavam a resposta anterior dele (ver "Decisão — critério de TI").
- Detalha: ADR 0016 (fontes). Respeita ADR 0005 (ingestão idempotente) e ADR 0013 (privacidade).

## Contexto

O perfil dos 3 CSVs do SIGA de 13/10/2026 mostrou que o modelo "uma linha por ata" não vale:

| Achado | Número |
|---|---|
| `ID Ata` repetido em `atas` (uma linha por processo SEI; só `id processo`/`processo` divergem) | 13.090 linhas, 11.662 ids; 406 ids repetidos (até 31x) |
| Linhas idênticas em itens e participantes, por efeito do mesmo join | 19.752 de 71.765 e 34.697 de 172.951 |
| Mesmo item+fornecedor com quantidade/valor diferentes depois do dedupe | 383 e 828 chaves |
| Codificação `cp1252` (travessão e aspas tipográficas), e não `latin-1` | bytes 0x94 e 0x96 em itens e participantes |
| Início de vigência vazio | 10 atas (2 `Válida`) |
| Valor unitário vazio ou ≤ 0 | 10 e 33 |
| `Qtd Consumida` > `Qtd Demandada` | 4.155 linhas |
| CPF no nome do fornecedor | 8 itens e 1 participante |
| Status | `Válida` 1.923 linhas (1.574 ids); `Interrompida` 160, 22 delas com vigência cobrindo hoje |

## Decisão — carga

1. **Uma carga é a unidade de publicação.** `cargas` registra fonte, data de referência
   (`data_extracao` dos arquivos), sha256/bytes/Last-Modified de cada arquivo e contagens. Atas,
   itens e participantes pertencem a uma `carga_id`; só uma carga por fonte fica `ativa`.
2. **Tudo numa transação.** Insere a carga nova, troca a ativa, apaga a anterior e registra
   `atas_vistas`. Falha em qualquer ponto faz rollback e a carga anterior continua visível; a
   falha, inclusive a de **download**, fica em `cargas` (`falhou`, tipo e mensagem curta). Para
   exceções do driver grava só a classe e o SQLSTATE, porque a mensagem do Postgres pode trazer
   a linha inteira; mensagens de validação passam por `sanitizar`. Uma trava consultiva
   **de sessão**, tomada antes do download e mantida até fechar a conexão, impede duas execuções
   simultâneas; a de transação continua como segunda proteção na publicação.
3. **Chaves.** Ata: `ID Ata` (as linhas por processo são colapsadas; todos os processos ficam em
   `processos[]`). Item e participante: hash do conteúdo da linha sem `data_extracao`, **calculado
   sobre o texto já mascarado** (a primeira versão hasheava a linha bruta com o CPF completo, o
   que permitia enumerar o CPF; corrigido na revisão). Linhas idênticas colapsam. Variações
   legítimas de quantidade/valor são preservadas, e aparecem como linhas distintas em
   `v_ata_itens_ti`; quem consome preço deve agrupar por `(id_ata, id_item)`.
4. **Sem mudança é registrado, não reprocessado.** Se os 3 sha256 **e a versão da regra de TI**
   (hash de `CATEGORIAS`, exclusões e termos) coincidem com a carga ativa, a execução grava uma
   `cargas` com `sem_mudanca` e a defasagem em dias; acima de 3 dias, avisa no log. Mudar a regra
   reclassifica na carga seguinte sem `--forcar`.
5. **Validação estrita (falha alto, nada é publicado):** cabeçalho exato (após `strip`) e número
   de colunas; **CSV estrito** (`strict=True`: aspas abertas ou texto depois do fechamento
   falham, mesmo com o número certo de colunas); os 3 `data_extracao` iguais, não futuros (mais de
   1 dia à frente de hoje) e não anteriores à da carga ativa; `Last-Modified` dentro de 15 min;
   cp1252 estrito sem indício de UTF-8; arquivo vazio; **pisos contra a carga ativa: 50% das
   atas e 70% dos itens e dos participantes**; mais de 5% das atas `Válida` sem nenhum item;
   órfãos, conflitos, datas ou números não parseáveis acima de 1%. **Data de vigência
   preenchida e inválida (ex.: 31/02) coloca a ata em quarentena** (não é gravada, e seus itens e
   participantes são descartados e contados): vazio é "não informado", inválido nunca vira
   vigente por omissão. Números só aceitam `12`,
   `12,50`, `,45`, `4.500,00` (com `-` opcional); `1.234` é inválido, por ser ambíguo.
6. **Vigente** = `status_origem = 'Válida'` **e** `inicio <= hoje <= fim` em `America/Sao_Paulo`
   (início **vazio** é aceito; início inválido, não). `Interrompida`, `Suspensa` e `Aguardando Vigência` ficam fora, mesmo
   com datas que cobrem hoje.
7. **Preço:** valor vazio ou ≤ 0 vira `NULL` com `valor_valido = false`. A linha do item
   **permanece** em `v_ata_itens_ti` (a ata continua tendo aquele item), mas com `valor_unitario`
   `NULL`: nunca há preço inválido na coluna de preço. A view de consumo se chama `v_ata_consumo_item` e expõe demandado e consumido
   por unidade participante, **sem** afirmar saldo (há consumo maior que a demanda na origem).
8. **`primeira_vez_vista`** fica em `atas_vistas`, fora do snapshot: a troca de carga não "renova"
   atas conhecidas. Na primeira carga, todas recebem a mesma data; o digest (R6) deve tratá-la
   como carga inicial.
9. **Privacidade:** toda célula de texto passa por `privacy.sanitizar` (CPF mascarado) já na
   leitura (`_ler_tabela`), inclusive ids e `processos`, que a view expõe; só as colunas numéricas
   e `data_extracao` ficam como vieram. O mascaramento vale também para a chave.
10. **Arquivos brutos** ficam em `data/siga/<timestamp>-<sufixo aleatório>/` (diretório exclusivo por execução) (fora do Git, pasta `0700`, arquivos
    `0600`), com as 3 últimas cargas; a poda roda também em falha e só toca pastas com nome de
    timestamp. **Os CSVs brutos contêm CPF completo** (8 itens e 1 participante em 13/10/2026):
    é o único lugar onde ele existe, e `identificar_fornecedor` ("CPF só em memória") não vale
    para esses arquivos. Apague `data/siga` ao descartar o ambiente.
11. **Limites de leitura:** 100 MB por arquivo (o maior real tem ~50 MB); a leitura inteira em
    memória usa cerca de 9x o tamanho (~660 MB para os 74 MB de hoje). Streaming fica para
    quando o volume pedir.

## Decisão — critério de TI

A fonte do critério é o **Anexo Único da IN PRODERJ/PRE nº 05/2024**
(`insumos/normas/IN_PRODERJ-PRE_05_2024.pdf`), rol exemplificativo (art. 1º, §1º). A regra
(`classificar/in05.py`) lê o **objeto** da ata e o **nome de catálogo** dos itens (texto antes do
primeiro " - "), nunca a especificação do item, onde há menções incidentais. Termos ambíguos
(`monitor`, `servidor`, `rack`) são ancorados. Cada decisão guarda um motivo auditável
(`categoria:termo@objeto|item`, ou `excluido:...`).

O Lucas havia dito que nobreak/energia, cabeamento/pontos lógicos, telefonia/VoIP/internet e
CFTV/catracas/drones não eram TI. Três dessas categorias **constam do anexo**; ao ver o conflito,
decidiu em 13/10/2026: **seguir o que diz a IN 05**.

| Categoria | No anexo | Regra |
|---|---|---|
| Comunicação de dados, voz, telefonia, internet | I-a | **TI** (`I-telecom`) |
| Pontos de rede lógicos e elétricos, infraestrutura da rede | VIII-a | **TI** (`VIII-rede-fisica`) |
| Videomonitoramento, reconhecimento facial, LPR (inclui CFTV) | VII-a | **TI** (`VII-videomonitoramento`) |
| Nobreak, drone | não constam | Excluídos pelo termo, só no objeto (`TERMOS_FORA_DO_ANEXO`) |
| Catraca | não consta | Sem exclusão própria; "CATRACA - CFTV" é TI pelo CFTV |

`CATEGORIAS_FORA_DE_ESCOPO` está vazio; o mecanismo fica para uma exclusão pontual futura. Itens
que o anexo não lista nem equivalem a algo listado ficam `sem_sinal` e são revisados na rotulagem.
Nobreak e drone seguem excluídos porque o Lucas os excluiu e o anexo não os cita; se a rotulagem
mostrar que o rol exemplificativo (art. 1º, §1º) os alcança, a decisão volta para ele.

O anexo é de uma norma **estadual do RJ**. Aplicá-lo às atas federais e municipais (R2 e R3) é
decisão separada.

## Consequências

- Resultado em 13/10/2026: 11.662 atas, 52.013 itens, 138.254 participantes; 1.574 atas
  `Válida` vigentes, 24 delas classificadas como TI (a regra inicial marcava 27, com falsos
  positivos médicos e de laboratório; a v1.1 corrige mais um, de embalagem hospitalar). Carga completa em cerca de 36 s.
- O resultado do SIGA é pequeno (~1,6% das válidas); o valor do produto vem de somar as fontes.
- O recall da regra só é conhecido depois da rotulagem do censo (D6). A regra v1 não foi
  ajustada contra rótulos.
- A migração 0005 é destrutiva para o schema do snapshot `/v1/atas` (vazio) e não tem downgrade.
- Índices full-text e trigram ficam para a R4, quando houver a consulta que os use.
- A migração tem guarda: recusa-se a rodar se houver snapshot `/v1/atas` concluído e ativo, e
  `cargas` tem `CHECK (NOT ativa OR status = 'concluida')`.
- `make eval` confere o CSV rotulado contra a carga ativa (ids e `filtro_sistema`) e falha se
  estiver defasado, para não medir uma regra que não está mais valendo.
- **Risco para R2 e R3:** alguns termos da regra não são ancorados (`hospedagem`, `barramento`,
  `bpm`, `gestao de ativos`, `switch`) e nunca casaram nas atas do SIGA vigentes. Em fontes
  federais e municipais podem gerar falso positivo; reavaliar com amostra antes de reutilizar.
- Nobreak/drone no **objeto** só excluem quando o próprio objeto não cita TI
  ("microcomputadores e nobreaks" segue TI).

## Revisão do Codex no PR #5 (13/10/2026)

Três correções de substância depois da primeira revisão: `processos` e demais textos copiados
passam por `sanitizar`; data inválida deixa de ser promovida a "início não informado"; o CSV é
lido em modo estrito. Também: `avaliar` rejeita `id_ata` repetido (as métricas eram infláveis) e o
download usa diretório exclusivo mais trava de sessão. A ressalva do `evals/` permanece: os rótulos
foram aplicados pelo Claude, então 100% não é uma avaliação independente.

## Revisão independente (13/10/2026)

Um subagente revisou o commit `bee69ba`. Procedeu e foi corrigido: chave com CPF (bloqueante),
pisos para itens e participantes, falha de download fora de `cargas`, data de extração futura,
defasagem não detectada, avaliação sobre CSV defasado, mensagens com possível linha de origem,
permissões dos arquivos brutos, poda ampla demais, parsers permissivos, guarda da migração.
Ficou documentado e não corrigido: leitura inteira em memória (nota 11) e termos não ancorados.
