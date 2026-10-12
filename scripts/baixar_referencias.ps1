# Baixa as referências oficiais para docs/referencias/.
# Uso (na raiz do projeto):  powershell -ExecutionPolicy Bypass -File scripts\baixar_referencias.ps1

$ErrorActionPreference = "Continue"
$dest = Join-Path $PSScriptRoot "..\docs\referencias"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# O WAF do PNCP recusa clientes sem User-Agent de navegador.
$headers = @{
    "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    "Accept"     = "application/json, text/html, text/plain, */*"
}

$arquivos = @(
    @{ url = "https://pncp.gov.br/api/consulta/v3/api-docs"; nome = "pncp-api-consulta-openapi.json" },
    @{ url = "https://pncp.gov.br/api/pncp/v3/api-docs"; nome = "pncp-api-pncp-openapi.json" },
    @{ url = "https://raw.githubusercontent.com/opedrosoares/MCP_Compras/main/README.md"; nome = "compras-mcp-README.md" },
    @{ url = "https://raw.githubusercontent.com/opedrosoares/MCP_Compras/main/manifest.json"; nome = "compras-mcp-manifest.json" },
    @{ url = "https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices.md"; nome = "mcp-security-best-practices.md" },
    @{ url = "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"; nome = "lei-14133-2021.htm" },
    @{ url = "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"; nome = "lgpd-13709-2018.htm" }
)

foreach ($a in $arquivos) {
    $saida = Join-Path $dest $a.nome
    try {
        Invoke-WebRequest -Uri $a.url -Headers $headers -OutFile $saida -UseBasicParsing -TimeoutSec 60
        $tam = (Get-Item $saida).Length
        Write-Host ("OK    {0} ({1:N0} bytes)" -f $a.nome, $tam)
    } catch {
        Write-Warning ("FALHOU {0}: {1}" -f $a.nome, $_.Exception.Message)
    }
}

Write-Host ""
Write-Host "Se o README/manifest do compras-mcp falhar, a branch padrao pode nao ser 'main': baixe pelo GitHub."
Write-Host "Baixe manualmente o Manual das APIs de consulta do PNCP (ver docs\referencias\LINKS.md)."
