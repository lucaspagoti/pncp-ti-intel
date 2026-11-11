# 0040 — Ajuste fino: seleção em pílula neutra, busca com ícone dentro do campo e Inter

- Status: aceita pelo Lucas (11/11/2026), depois de comparar as opções num HTML interativo.
- Ajusta a ADR 0039 (itens 1, 3 e 6). Altera a CSP da ADR 0018 com `font-src 'self'`.

## Contexto

Com o front novo em produção, o Lucas apontou quatro incômodos: a opção de filtro marcada, em azul
sólido, estava forte demais; o botão azul "Buscar" era o objeto mais forte da tela; a home parecia
desalinhada; e a tipografia incomodava sem que ele soubesse dizer por quê.

O que se mediu:

- A web usava a fonte do sistema: San Francisco no Mac, Segoe UI no Windows (o aparelho do Lucas),
  Roboto no Android. O desenho foi pensado para a San Francisco; na Segoe, o espaçamento negativo
  entre letras apertava o texto, e a Segoe UI não tem o peso 500. Tudo que era destaque ficava em
  600 (título, preço, opção marcada, prazo, rótulos), então nada se destacava.
- Na home, o conjunto campo + botão estava centrado, mas o campo sozinho ficava 56 px à esquerda
  do título. O rótulo "Experimente" empurrava os exemplos, e o rodapé saía como "11/11/2026.SIGA RJ".

## Decisão

1. **Seleção em pílula neutra.** A opção marcada fica branca, com sombra leve, e sobe para o peso 500.
   Sem cor e sem anel de rádio (o rádio continua cobrindo a linha, invisível, então o toque e o
   teclado funcionam). Referência: barra lateral da Apple. No celular, o painel de filtros passa a
   cinza para a pílula branca aparecer.
2. **Busca com ícone dentro do campo.** O botão vira um círculo grafite com seta, dentro do campo, apagado
   enquanto o campo está vazio. Continua um `<button type="submit">` com nome acessível "Buscar". O
   campo volta ao eixo; no celular ocupa a largura toda, e o botão tem 44 px de toque. O "×" nativo
   do Chrome some. O azul fica só para links e foco, com anel mais leve (3 px a 16%).
3. **Tipografia Inter, servida pela própria web.** Arquivo variável, subconjunto latino
   (`static/fonts/inter-latin-wght-normal.woff2`, 48 KB), com a licença SIL OFL ao lado. `@font-face`
   no `app.css`, com `preload` no `base.html`. A fonte do sistema fica como reserva.
   - Escala nova: 11 · 13 · 14 · 16 · 20 · 26 · 36 px. Três pesos: 400 no corpo, 500 no que está
     marcado, nos botões e nos rótulos, e 600 só em títulos e preço.
   - Rótulos de grupo e de campo em cinza e peso 500; espaçamento entre letras só nos títulos
     (`--tracking-display` e `--tracking-titulo`).
4. **CSP.** `font-src 'self'`. Continua sem `unsafe-inline` e sem nenhum host externo: a fonte não vem
   de CDN.
5. **Home.** Sai o rótulo "Experimente"; o rodapé ganha o espaço que faltava depois da data.

## Consequências

- A web passa a servir um arquivo de fonte (48 KB, em cache). Sem a fonte, cai na do sistema, sem quebra.
- Troca de fonte exige novo arquivo em `static/fonts/` e ADR; a licença da Inter permite embarcar.
- O contraste continua medido: texto 4,5:1, borda de controle 3:1; o botão apagado usa `--ink-2`
  sobre o fundo claro (5,5:1).
- A seleção por cor (azul) não existe mais nos filtros; quem precisar de mais destaque pode voltar
  a uma das opções avaliadas (tonal, marca lateral ou check) sem mexer na estrutura.
