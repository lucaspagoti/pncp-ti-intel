# 0041 — Nome "Portal de Atas de TI" e ícone da marca

- Status: aceita pelo Lucas (11/11/2026), depois de comparar seis ícones num HTML interativo.
- Complementa as ADRs 0039 e 0040.

## Contexto

A web se chamava "Atas de TI". O Lucas quis o nome "Portal de Atas de TI" em todo lugar visível e um
ícone para a aba do navegador e para a barra de menu.

## Decisão

1. **Nome.** "Portal de Atas de TI" na marca da lateral, no título da home e nos títulos das abas
   (`Portal de Atas de TI`, `notebook · Portal de Atas de TI`, `Ata 014/2026 · Portal de Atas de TI`).
   Os alertas do WhatsApp (`operacao.py`, ADRs 0030 e 0032) **não** mudam: continuam começando por
   "Atas de TI:", frase curta como o Lucas pediu na ADR 0030. A decisão pode ser revista numa linha.
2. **Ícone.** "Pilha de atas" (uma folha com duas abas na frente), em grafite sólido, com o traço dos
   demais ícones da web (linha de 1,9 px, pontas redondas). Desenho próprio, sem biblioteca nem
   dependência. O mesmo desenho serve à aba, à lateral e à home.
3. **Arquivos** em `static/`: `icone.svg` (aba, vetorial), `icone-32.png` (aba, fallback),
   `icone-192.png` (instalação) e `icone-apple-180.png` (tela inicial do iPhone, fundo cheio porque o
   iOS arredonda sozinho). Ligados no `base.html` (`rel="icon"` e `rel="apple-touch-icon"`).
   A CSP não muda: `img-src 'self'` já cobre os arquivos.
4. **Lateral.** O selo de 32 px (`--selo`) fica ao lado do nome, em uma linha; na home, o selo de 56 px
   (`--selo-grande`) vem acima do título.

## Consequências

- Se o desenho mudar, os quatro arquivos precisam ser refeitos juntos; o SVG é a fonte (os PNG saem dele).
- A marca ocupa mais largura na lateral; o nome em 14 px e peso 600 cabe em uma linha (teste E2E).
- O nome do projeto no repositório (`pncp-ti-intel`) e nas units do systemd não muda.
