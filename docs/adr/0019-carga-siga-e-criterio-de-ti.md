# 0019 — Carga do SIGA RJ e critério de TI (IN PRODERJ 05/2024)

- Status: aceita (13/10/2026). A decisão sobre as três categorias do anexo marcadas abaixo como
  "em conflito" está **aberta** e volta para o Lucas.
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
   falha fica em `cargas` (`falhou`, tipo e mensagem curta, sem linhas dos arquivos). Uma trava
   consultiva impede duas cargas simultâneas.
3. **Chaves.** Ata: `ID Ata` (as linhas por processo são colapsadas; todos os processos ficam em
   `processos[]`). Item e participante: hash do conteúdo da linha sem `data_extracao`; linhas
   idênticas colapsam. Variações legítimas de quantidade/valor são preservadas.
4. **Sem mudança é registrado, não reprocessado.** Se os 3 sha256 coincidem com a carga ativa, a
   execução grava uma `cargas` com `sem_mudanca`.
5. **Validação estrita (falha alto, nada é publicado):** cabeçalho exato (após `strip`) e número
   de colunas; os 3 `data_extracao` iguais e `Last-Modified` dentro de 15 min; codificação
   cp1252 estrita sem indício de UTF-8; arquivo vazio; menos de 50% das atas da carga ativa;
   `data_extracao` anterior à da carga ativa; órfãos ou conflitos acima de 1%.
6. **Vigente** = `status_origem = 'Válida'` **e** `inicio <= hoje <= fim` em `America/Sao_Paulo`
   (início vazio é aceito). `Interrompida`, `Suspensa` e `Aguardando Vigência` ficam fora, mesmo
   com datas que cobrem hoje.
7. **Preço:** valor vazio ou ≤ 0 vira `NULL` com `valor_valido = false` e nunca entra em
   `v_ata_itens_ti`. A view de consumo se chama `v_ata_consumo_item` e expõe demandado e consumido
   por unidade participante, **sem** afirmar saldo (há consumo maior que a demanda na origem).
8. **`primeira_vez_vista`** fica em `atas_vistas`, fora do snapshot: a troca de carga não "renova"
   atas conhecidas. Na primeira carga, todas recebem a mesma data; o digest (R6) deve tratá-la
   como carga inicial.
9. **Privacidade:** todo texto de terceiros passa por `privacy.sanitizar` (CPF mascarado) antes
   de ser gravado ou usado na chave.
10. **Arquivos brutos** ficam em `data/siga/<timestamp>/` (fora do Git), com as 3 últimas cargas.

## Decisão — critério de TI

A fonte do critério é o **Anexo Único da IN PRODERJ/PRE nº 05/2024**
(`insumos/normas/IN_PRODERJ-PRE_05_2024.pdf`), rol exemplificativo (art. 1º, §1º). A regra
(`classificar/in05.py`) lê o **objeto** da ata e o **nome de catálogo** dos itens (texto antes do
primeiro " - "), nunca a especificação do item, onde há menções incidentais. Termos ambíguos
(`monitor`, `servidor`, `rack`) são ancorados. Cada decisão guarda um motivo auditável
(`categoria:termo@objeto|item`, ou `excluido:...`).

O Lucas decidiu (13/10/2026) que **nobreak/energia, cabeamento/pontos lógicos, telefonia/VoIP/
internet e CFTV/catracas/drones não são TI** neste projeto. Três dessas categorias **constam do
anexo**:

| Categoria do anexo | Onde | Estado na regra |
|---|---|---|
| Comunicação de dados, voz, telefonia, internet | I-a | **Em conflito.** Excluída (`I-telecom`) |
| Pontos de rede lógicos e elétricos, infraestrutura da rede | VIII-a | **Em conflito.** Excluída (`VIII-rede-fisica`) |
| Videomonitoramento, reconhecimento facial, LPR | VII-a | **Em conflito.** Excluída (`VII-videomonitoramento`) |
| Nobreak, drone, catraca | — (não constam) | Excluídos pelo termo, só no objeto |

A exclusão está em `CATEGORIAS_FORA_DE_ESCOPO` e `TERMOS_FORA_DO_ANEXO`, um lugar só. Se o Lucas
decidir seguir o anexo, remove-se a categoria do conjunto e recarrega-se. Enquanto isso, um item
de TI dentro do escopo (ex.: "SERVICOS SUPORTE EM TECNOLOGIA DA INFORMACAO") prevalece sobre um
objeto de categoria excluída (caso real: "RECONHECIMENTO FACIAL").

O anexo é de uma norma **estadual do RJ**. Aplicá-lo às atas federais e municipais (R2 e R3) é
decisão separada.

## Consequências

- Resultado em 13/10/2026: 11.662 atas, 52.013 itens, 138.254 participantes; 1.574 atas
  `Válida` vigentes, 21 delas classificadas como TI (a regra anterior marcava 27, com
  falsos positivos médicos e de laboratório). Carga completa em cerca de 36 s.
- O resultado do SIGA é pequeno (~1,3% das válidas); o valor do produto vem de somar as fontes.
- O recall da regra só é conhecido depois da rotulagem do censo (D6). A regra v1 não foi
  ajustada contra rótulos.
- A migração 0005 é destrutiva para o schema do snapshot `/v1/atas` (vazio) e não tem downgrade.
- Índices full-text e trigram ficam para a R4, quando houver a consulta que os use.
