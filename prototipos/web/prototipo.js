// Fechar o aviso e remover filtros com animação (ADR 0039). O movimento é transição CSS: o JS só
// troca classes e lembra, neste navegador, quais avisos o leitor já fechou. Sem estilo inline no
// HTML (CSP `style-src 'self'`).
(() => {
  "use strict";

  const CHAVE = "pncp-ti:avisos-fechados";

  // O armazenamento pode faltar (janela privada, site bloqueado): sem ele, nada é lembrado.
  const ler = () => {
    try { return new Set(JSON.parse(localStorage.getItem(CHAVE) || "[]")); } catch { return new Set(); }
  };
  const gravar = (conjunto) => {
    try { localStorage.setItem(CHAVE, JSON.stringify([...conjunto])); } catch { /* sem persistência */ }
  };

  function sair(bloco) {
    bloco.classList.add("saindo");
    bloco.inert = true;
    bloco.setAttribute("aria-hidden", "true");
    const ao = (e) => {
      if (e.target === bloco && e.propertyName === "grid-template-rows") {
        bloco.removeEventListener("transitionend", ao);
        bloco.classList.add("oculta");
      }
    };
    bloco.addEventListener("transitionend", ao);
  }

  // Ao carregar e a cada troca de resultados do HTMX, avisos já fechados entram fechados.
  function aplicar() {
    const fechados = ler();
    document.querySelectorAll("[data-dispensar]").forEach((bloco) => {
      if (fechados.has(bloco.dataset.chave)) {
        bloco.classList.add("saindo", "oculta");
        bloco.inert = true;
      }
    });
  }

  document.addEventListener("click", (e) => {
    const alvo = e.target.closest("[data-acao]");
    if (!alvo) return;
    if (alvo.dataset.acao === "fechar") {
      const bloco = alvo.closest("[data-dispensar]");
      const fechados = ler();
      fechados.add(bloco.dataset.chave);
      gravar(fechados);
      sair(bloco);
    } else if (alvo.dataset.acao === "remover-filtro") {
      // A pílula sai já; a lista troca quando a resposta chegar (HTMX ou navegação).
      alvo.closest(".pilula")?.classList.add("saindo");
    }
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", aplicar);
  else aplicar();
  document.addEventListener("htmx:afterSwap", aplicar);
})();
