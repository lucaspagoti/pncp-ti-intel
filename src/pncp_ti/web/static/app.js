// Estado de carregamento acessível: a casca fica `aria-busy` enquanto o HTMX busca a página.
document.addEventListener("htmx:beforeRequest", (e) => {
  document.getElementById("casca")?.setAttribute("aria-busy", "true");
});
document.addEventListener("htmx:afterRequest", () => {
  document.getElementById("casca")?.removeAttribute("aria-busy");
});
