"""Seletores e utilitários compartilhados pelos E2E da web (W2 e W5)."""

from __future__ import annotations

from playwright.sync_api import Page

# Lista de todas as atas, sem filtro: a home só mostra a busca (ADR 0039).
TODAS = "/?explorar=1"
RESULTADOS = ".resultados .ata-objeto > a"


def buscar(page: Page) -> None:
    page.get_by_role("button", name="Buscar", exact=True).click()


# Razão de contraste WCAG entre a cor do texto e o primeiro fundo opaco dos ancestrais.
CONTRASTE_JS = """
(seletor) => {
  const canal = (s) => {
    const m = s.match(/rgba?\\(([^)]+)\\)/) || s.match(/color\\(srgb ([^)]+)\\)/);
    const partes = m[1].replace('/', ' ').split(/[ ,]+/).filter(Boolean).map(Number);
    const escala = s.startsWith('color(') ? 255 : 1;
    return {rgb: partes.slice(0, 3).map((v) => v * escala), a: partes.length > 3 ? partes[3] : 1};
  };
  const lum = ([r, g, b]) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const el = document.querySelector(seletor);
  if (!el) return null;
  const cor = canal(getComputedStyle(el).color).rgb;
  let fundo = null;
  for (let n = el; n; n = n.parentElement) {
    const c = canal(getComputedStyle(n).backgroundColor);
    if (c.a >= 0.99) { fundo = c.rgb; break; }
  }
  fundo = fundo || [255, 255, 255];
  const [a, b] = [lum(cor), lum(fundo)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}
"""
