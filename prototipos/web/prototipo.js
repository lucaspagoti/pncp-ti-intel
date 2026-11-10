// Dispensar com animação interrompível (ADR 0038). O movimento é todo transição CSS: tirar a
// classe `saindo` no meio do caminho faz o bloco voltar do ponto em que está. O JS só troca
// classes, guarda o que foi dispensado no navegador e conduz o gesto de arrastar.
// Sem estilo inline no HTML (CSP `style-src 'self'`): o gesto usa a propriedade --dx pelo CSSOM.
(() => {
  "use strict";

  const LIMITE = 500;
  const MOSTRA_TOAST_MS = 6000;
  const LIMIAR_ARRASTE = 0.35;   // fração da largura que dispensa ao soltar
  const LIMIAR_VELOCIDADE = 0.6; // px/ms que dispensa mesmo antes do limiar

  // ---------- Armazenamento (pode faltar: janela privada, site bloqueado) ----------
  const ler = (chave) => {
    try { return new Set(JSON.parse(localStorage.getItem(chave) || "[]")); } catch { return new Set(); }
  };
  const gravar = (chave, conjunto) => {
    try { localStorage.setItem(chave, JSON.stringify([...conjunto].slice(-LIMITE))); } catch { /* sem persistência */ }
  };
  const CHAVE = { ata: "pncp-ti:atas-ocultas", aviso: "pncp-ti:avisos-fechados" };

  const blocos = (tipo) => document.querySelectorAll(`[data-dispensar="${tipo}"]`);
  const fim = (el, fn) => {
    // `transitionend` dispara uma vez por propriedade; basta a da altura.
    const ao = (e) => { if (e.target === el && e.propertyName === "grid-template-rows") { el.removeEventListener("transitionend", ao); fn(); } };
    el.addEventListener("transitionend", ao);
  };

  // ---------- Saída e volta ----------
  function sair(bloco, lado = -1) {
    if (bloco.classList.contains("saindo")) return;
    bloco.style.setProperty("--lado", String(lado));
    bloco.classList.add("saindo");
    bloco.setAttribute("aria-hidden", "true");
    bloco.inert = true;
    fim(bloco, () => { if (bloco.classList.contains("saindo")) bloco.classList.add("oculta"); });
  }

  function voltar(bloco) {
    bloco.inert = false;
    bloco.removeAttribute("aria-hidden");
    bloco.classList.remove("arrastando");
    if (bloco.classList.contains("oculta")) {
      // Já saiu de vez: reaparece fechado e abre no quadro seguinte.
      bloco.classList.remove("oculta");
      void bloco.offsetHeight;
    }
    bloco.style.setProperty("--dx", "0px");
    bloco.classList.remove("saindo");
  }

  // ---------- Atas ocultas, Desfazer e "Mostrar" ----------
  let ultimas = [];   // dispensadas desde que o aviso de Desfazer abriu
  let relogio = 0;

  const toast = () => document.querySelector("[data-toast]");

  function avisar() {
    const t = toast();
    if (!t) return;
    t.querySelector("[data-toast-texto]").textContent =
      ultimas.length === 1 ? "Ata oculta" : `${ultimas.length} atas ocultas`;
    t.classList.add("visivel");
    rearmar();
  }
  function rearmar() {
    clearTimeout(relogio);
    relogio = setTimeout(fecharToast, MOSTRA_TOAST_MS);
  }
  function fecharToast() {
    clearTimeout(relogio);
    ultimas = [];
    toast()?.classList.remove("visivel");
  }

  function contarOcultas() {
    const el = document.querySelector("[data-ocultas]");
    if (!el) return;
    const n = [...blocos("ata")].filter((b) => b.classList.contains("saindo")).length;
    el.hidden = n === 0;
    el.querySelector("[data-ocultas-texto]").textContent =
      n === 1 ? "1 ata oculta nesta página" : `${n} atas ocultas nesta página`;
  }

  function ocultarAta(bloco, lado, porTeclado) {
    const guardadas = ler(CHAVE.ata);
    guardadas.add(bloco.dataset.chave);
    gravar(CHAVE.ata, guardadas);
    // O foco não pode ficar num bloco que vai sumir.
    const seguinte = bloco.nextElementSibling?.querySelector("a") || bloco.previousElementSibling?.querySelector("a");
    sair(bloco, lado);
    ultimas.push(bloco);
    avisar();
    contarOcultas();
    if (porTeclado) toast()?.querySelector("button")?.focus();
    else if (bloco.contains(document.activeElement)) seguinte?.focus();
  }

  function mostrarAtas(lista) {
    const guardadas = ler(CHAVE.ata);
    lista.forEach((bloco) => { guardadas.delete(bloco.dataset.chave); voltar(bloco); });
    gravar(CHAVE.ata, guardadas);
    contarOcultas();
  }

  function desfazer() {
    const lista = ultimas;
    fecharToast();
    mostrarAtas(lista);
    lista[0]?.querySelector("a")?.focus();
  }

  // Ao carregar e a cada troca de resultados do HTMX: ocultas de antes já entram fechadas.
  function aplicar() {
    const guardadas = ler(CHAVE.ata);
    blocos("ata").forEach((b) => {
      if (guardadas.has(b.dataset.chave)) { b.classList.add("saindo", "oculta"); b.inert = true; b.setAttribute("aria-hidden", "true"); }
    });
    const fechados = ler(CHAVE.aviso);
    blocos("aviso").forEach((b) => { if (fechados.has(b.dataset.chave)) b.classList.add("saindo", "oculta"); });
    contarOcultas();
  }

  // ---------- Cliques ----------
  document.addEventListener("click", (e) => {
    const alvo = e.target.closest("[data-acao]");
    if (!alvo) return;
    const acao = alvo.dataset.acao;
    const porTeclado = e.detail === 0;
    if (acao === "ocultar") {
      e.preventDefault();
      const bloco = alvo.closest("[data-dispensar]");
      if (bloco.dataset.dispensar === "ata") ocultarAta(bloco, -1, porTeclado);
      else {
        const fechados = ler(CHAVE.aviso);
        fechados.add(bloco.dataset.chave);
        gravar(CHAVE.aviso, fechados);
        sair(bloco, -1);
      }
    } else if (acao === "desfazer") {
      desfazer();
    } else if (acao === "mostrar-ocultas") {
      fecharToast();
      mostrarAtas([...blocos("ata")].filter((b) => b.classList.contains("saindo")));
    } else if (acao === "remover-filtro") {
      // A pílula sai já; a lista troca quando a resposta chegar (HTMX ou navegação).
      alvo.closest(".pilula")?.classList.add("saindo");
    }
  });

  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && toast()?.classList.contains("visivel")) fecharToast(); });
  document.addEventListener("pointerover", (e) => { if (e.target.closest?.("[data-toast]")) clearTimeout(relogio); });
  document.addEventListener("pointerout", (e) => { if (e.target.closest?.("[data-toast]") && ultimas.length) rearmar(); });

  // ---------- Arrastar para dispensar (toque e caneta) ----------
  let gesto = null;

  document.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || !e.isPrimary) return;
    const cartao = e.target.closest('[data-dispensar="ata"] > .cartao');
    if (!cartao || e.target.closest("button")) return;
    gesto = { bloco: cartao.parentElement, cartao, x0: e.clientX, y0: e.clientY, dx: 0, t: e.timeStamp, v: 0, ativo: false, id: e.pointerId };
  });

  document.addEventListener("pointermove", (e) => {
    if (!gesto || e.pointerId !== gesto.id) return;
    const dx = e.clientX - gesto.x0;
    const dy = e.clientY - gesto.y0;
    if (!gesto.ativo) {
      if (Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) { gesto = null; return; } // é rolagem
      if (Math.abs(dx) < 10) return;
      gesto.ativo = true;
      gesto.bloco.classList.add("arrastando");
      gesto.cartao.setPointerCapture(e.pointerId);
    }
    const dt = Math.max(1, e.timeStamp - gesto.t);
    gesto.v = (dx - gesto.dx) / dt;
    gesto.dx = dx;
    gesto.t = e.timeStamp;
    gesto.bloco.style.setProperty("--dx", `${dx}px`);
  });

  function soltar(e) {
    if (!gesto || e.pointerId !== gesto.id) return;
    const { bloco, cartao, dx, v, ativo } = gesto;
    gesto = null;
    if (!ativo) return;
    bloco.classList.remove("arrastando");
    const passou = Math.abs(dx) > cartao.offsetWidth * LIMIAR_ARRASTE || Math.abs(v) > LIMIAR_VELOCIDADE;
    if (passou && e.type === "pointerup") {
      const lado = Math.sign(dx || v) || -1;
      bloco.style.setProperty("--dx", `${lado * cartao.offsetWidth}px`); // termina o arraste para fora
      ocultarAta(bloco, lado, false);
    } else {
      bloco.style.setProperty("--dx", "0px"); // volta do ponto em que soltou
    }
    fimDoArraste = e.timeStamp;
  }
  document.addEventListener("pointerup", soltar);
  document.addEventListener("pointercancel", soltar);
  // O clique que segue um arraste não abre a ata.
  let fimDoArraste = -Infinity;
  document.addEventListener("click", (e) => {
    if (e.timeStamp - fimDoArraste < 400 && e.target.closest('[data-dispensar="ata"]')) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  // ---------- Início ----------
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", aplicar);
  else aplicar();
  document.addEventListener("htmx:afterSwap", aplicar);
})();
