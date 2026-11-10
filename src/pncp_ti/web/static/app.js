// Comportamento da web (ADR 0039). Sem estilo inline: o movimento é transição CSS e o JS só
// troca classes e atributos. Tudo o que depende de armazenamento funciona sem ele.
(() => {
  "use strict";

  // ---------- Troca de resultados do HTMX ----------
  // A casca fica `aria-busy` e a barra de progresso corre (se a resposta demorar) enquanto o HTMX
  // busca a página.
  // Texto dos campos que aplicam sozinhos depois de uma pausa na digitação (órgão e preço).
  const textoDosCampos = () =>
    [...document.querySelectorAll("input[data-auto]")].map((campo) => campo.value).join("\u0001");
  let enviado = null;

  document.addEventListener("htmx:beforeRequest", () => {
    document.getElementById("casca")?.setAttribute("aria-busy", "true");
    document.documentElement.setAttribute("data-ocupado", "");
    enviado = textoDosCampos();
  });

  // Se algum desses campos mudou depois do envio, a resposta é velha e apagaria o que foi
  // escrito, mesmo que o leitor já tenha passado para outro campo: ela é descartada, e a pausa
  // na digitação que ainda vai terminar envia o texto novo. Os demais filtros (rádio, UF, data,
  // ordem) enviam na hora e cancelam o pedido anterior; a busca pelo termo só envia no botão.
  document.addEventListener("htmx:beforeSwap", (e) => {
    if (enviado !== null && textoDosCampos() !== enviado) e.detail.shouldSwap = false;
    enviado = null;
  });

  document.addEventListener("htmx:afterRequest", () => {
    document.getElementById("casca")?.removeAttribute("aria-busy");
    document.documentElement.removeAttribute("data-ocupado");
  });

  // ---------- Fechar o aviso e remover filtros ----------
  const CHAVE_AVISOS = "pncp-ti:avisos-fechados";

  // O armazenamento pode faltar (janela privada, site bloqueado): sem ele, nada é lembrado.
  const lerFechados = () => {
    try { return new Set(JSON.parse(localStorage.getItem(CHAVE_AVISOS) || "[]")); } catch { return new Set(); }
  };
  const gravarFechados = (conjunto) => {
    try { localStorage.setItem(CHAVE_AVISOS, JSON.stringify([...conjunto])); } catch { /* sem persistência */ }
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

  // Ao carregar e a cada troca do HTMX, avisos já fechados entram fechados.
  function aplicarFechados() {
    const fechados = lerFechados();
    document.querySelectorAll("[data-dispensar]").forEach((bloco) => {
      if (fechados.has(bloco.dataset.chave)) {
        bloco.classList.add("saindo", "oculta");
        bloco.inert = true;
        bloco.setAttribute("aria-hidden", "true");
      }
    });
  }

  // ---------- Voltar à busca ----------
  // Quem chegou à ata por um cartão volta à busca exatamente como estava (filtros, página e
  // rolagem). Sem esse caminho (link direto, nova aba, outra ata digitada na barra), o link leva
  // à lista inteira. O cartão guarda a ata que abriu, e só ela vale como "veio da busca".
  const CHAVE_VOLTAR = "pncp-ti:veio-da-busca";
  const guardar = (ata) => {
    try { sessionStorage.setItem(CHAVE_VOLTAR, ata); } catch { /* sem sessão */ }
  };
  const veioDaBusca = () => {
    try { return sessionStorage.getItem(CHAVE_VOLTAR) === location.pathname; } catch { return false; }
  };

  document.addEventListener("click", (e) => {
    const alvo = e.target.closest("a, button");
    if (!alvo) return;
    if (alvo.matches(".lista-atas a")) {
      guardar(new URL(alvo.href, location.href).pathname);
    } else if (alvo.matches("[data-voltar]")) {
      const nova = e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0;
      if (!nova && veioDaBusca() && history.length > 1) {
        e.preventDefault();
        history.back();
      }
    } else if (alvo.dataset.acao === "fechar") {
      const bloco = alvo.closest("[data-dispensar]");
      const fechados = lerFechados();
      fechados.add(bloco.dataset.chave);
      gravarFechados(fechados);
      sair(bloco);
    } else if (alvo.dataset.acao === "remover-filtro") {
      // A pílula sai já; a lista troca quando a resposta chegar.
      alvo.closest(".pilula")?.classList.add("saindo");
    }
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", aplicarFechados);
  else aplicarFechados();
  document.addEventListener("htmx:afterSwap", aplicarFechados);
})();
