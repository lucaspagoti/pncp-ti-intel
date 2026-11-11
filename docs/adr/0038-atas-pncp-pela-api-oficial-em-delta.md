# 0038 — Atas PNCP pela API oficial de consultas, em delta diário com varredura mensal

- Status: aceita pelo Lucas (09/11/2026, plano R3.1, PR 2).
- Altera a ADR 0016 (item 2: o snapshot diário de `/v1/atas` continua fora, mas a rota volta
  restrita a uma varredura mensal) e a ADR 0023 (a busca do portal deixa de ser o coletor
  diário e vira reserva). Complementa a ADR 0037.

## Contexto

A busca do portal (`/api/search/`) derruba 60–76% das conexões de script (ADR 0037). O retry e
o "publica e avisa" seguram a fonte no ar, mas não resolvem a causa: lemos o índice inteiro todo
dia, ~600–1.000 requisições, por uma rota interna do front-end, e os termos pesados ainda truncam
na janela de 10 mil resultados.

A API oficial de consultas do PNCP (`/api/consulta`, OpenAPI em `/api/consulta/v3/api-docs`)
tem duas rotas de atas, ambas com páginas de 500:

- `/v1/atas/atualizacao`: atas por data de atualização (`dataAtualizacaoGlobal`), ~2.200 por
  dia (~5 páginas). É o delta.
- `/v1/atas`: atas por vigência. Com a vigência de hoje são ~482 mil atas em ~965 páginas. A
  ADR 0016 abandonou o snapshot diário dela quando a página máxima era 50 (~9,7 mil requisições).

Medições de 09/11/2026 no banco descartável (`pncp-ti-qa-r31`):

- **Semente** (`/v1/atas`, vigência de hoje): 481.500 atas lidas em 977 requisições, 14 respostas
  5xx recuperadas no retry, nenhum 429 a 0,4 req/s. Levou **6h40**: o portal responde cada
  página de 500 em 6–20 s, mais lento à tarde. 18.198 atas de TI pelos 57 termos.
- **Delta** (`/v1/atas/atualizacao`, 08–09/11): 3.754 atualizações em 8 requisições e 33 s; 52
  atas de TI novas e 1 removida (cancelada).
- **Equivalência** contra a carga ativa da busca do portal (16.878 atas, 09/11 14:23): 16.800 em
  comum (99,5%), 1.398 só na API e 78 só na busca. Das só na API, `toner` (332), `software` (280),
  `equipamentos de informatica` (157), `tablet` e `notebook` são termos que a busca truncava ou
  perdia. Contra as 6.847 atas de TI do ARP com número de controle PNCP, a API cobre 3.615 e a
  busca 3.349. As 78 só na busca foram procuradas uma a uma na API: 65 estão canceladas (a busca
  `status=vigente` ainda as mostrava) e 13 têm vigência que começa depois de hoje (fora do
  filtro da semente medida). Nenhuma ata vigente ficou de fora (`evals/pncp_atas_20261109.md`).
- Durante as horas de leitura a lista muda: 203 registros a mais ou a menos que o total
  declarado na primeira página. Uma ata pode ser pulada pela paginação.
- A API só informa a data da atualização (sem hora); a busca do portal informa data e hora.

## Decisão

1. **Coletor novo `pncp_atas`, mesma fonte.** Publica em `fonte = 'pncp_busca'`, com as mesmas
   colunas e `motivo_ti = termo_pncp:<termos>`; views, web, migrações e o gancho
   `resultados_por_termo` não mudam. O filtro é o mesmo `casa_termo` sobre o objeto, sem a
   janela de 10 mil. `valor_total` fica nulo, como já era na busca; esfera, UF e município vêm
   do cadastro de unidades (ADR 0034) ou da ata que já estava na base; `status_origem` é
   herdado da base ou "Divulgada no PNCP". O link da ata é montado do número de controle.
   O cliente é o `PNCPClient.get_json` do `compras-mcp` (ADR 0004), com página de 500, 0,4
   req/s e retry próprio (6 tentativas, 5–120 s); 4xx é mudança de contrato (saída 2).
2. **Delta diário.** A carga das 03:00 lê `/v1/atas/atualizacao` desde a marca d'água da última
   carga deste coletor menos 1 dia até hoje, e aplica sobre a carga ativa: entra ou atualiza a
   ata vigente, não cancelada, cujo objeto casa algum termo; sai a cancelada, a vencida ou a
   que deixou de casar. A ata cuja vigência começa no futuro entra. A marca d'água fica em
   `cargas.contagens.marca_dagua` e é lida da última carga com `coletor = api_consulta`, mesmo
   que a reserva tenha publicado depois. Sem marca, lê os últimos 7 dias; com marca de mais de
   30 dias, lê só 30, grava `janela_truncada` e a verificação das 08:30 avisa (`pncp:lacuna`).
3. **Varredura mensal, aditiva, fora da carga diária.** `--semente` lê `/v1/atas` com vigência
   de hoje até hoje + 364 dias (a API recusa período maior que 365), em unit própria
   (`pncp-ti-semente`, primeiro domingo do mês às 10:00, `TimeoutStartSec=14h`). Ela é aplicada
   como um delta grande: só tira da base a ata que a API mostra cancelada, vencida ou sem termo
   (o checkpoint guarda as atas que casam termo e as que já estão na base); a ata que a
   paginação pulou continua. Lê as páginas sem a trava da fonte, guarda cada uma num checkpoint
   em `~/.local/state/pncp-ti/` e retoma da página seguinte (até 3 retomadas em processo, e
   entre execuções se o checkpoint tiver até 3 dias). No fim pega a trava de sessão da fonte
   (espera até ~1h30 se a carga diária estiver rodando) e, já com ela, relê pelo delta o que
   mudou desde a véspera do início da varredura, que vale sobre o que ela leu, e só então lê a
   base e publica. Versão da API com data anterior à da base também é ignorada. Assim a
   varredura de horas não desfaz um delta publicado no meio. Mantém a marca d'água anterior.
   Falha dela avisa numa frase própria e não interrompe o delta.
4. **Reserva automática.** Se `pncp_atas` sair com código diferente de 0, o `carga_diaria.sh`
   roda a busca do portal (`pncp_busca`, ADR 0037) na hora, que publica na mesma fonte. Sobre
   uma carga da API, a reserva mantém as atas ativas vigentes, não canceladas e que casam termo
   que ela não achou (`atas_preservadas_api`): o delta seguinte só lê o que mudou e não as
   devolveria. A reserva grava `preserva_api`, e a seguinte também preserva, até a API voltar. A verificação das 08:30 avisa quando a carga ativa não veio da API (`pncp:reserva`). A
   aposentadoria da busca do portal fica para decisão do Lucas depois de um período de uso.
5. **Telemetria.** `cargas.contagens` grava `coletor`, `modo`, `motivo_modo`, `janela`,
   `marca_dagua`, registros declarados, lidos e divergentes, atas novas, removidas e com versão
   antiga, comparação com a carga anterior e as falhas de rede por tipo (ADR 0037).

## Consequências

- A carga diária das atas PNCP cai de ~25 min e ~600–1.000 requisições numa rota instável para
  menos de 1 min e ~10 requisições na rota documentada.
- Cancelamentos passam a sair da base: a busca `status=vigente` não os via.
- O primeiro delta em produção roda sobre a carga ativa da busca do portal com janela de 7 dias;
  a primeira varredura completa é manual (`make ingest FONTE=pncp_atas ARGS=--semente`, ~7 h)
  ou espera o primeiro domingo do mês. Ativar o timer novo é decisão do Lucas.
- A varredura depende do ritmo do portal (6h40 medidas). Se passar de 14 h, o checkpoint
  permite completar em execuções seguintes.
- Ata da base que a API nunca mostra (pulada pela paginação ou fora dos filtros) só sai quando
  vence; o delta continua tirando a que for cancelada ou alterada.
