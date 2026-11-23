# Abre el Word, actualiza índice y campos, lo guarda (reescribe el .docx) y exporta a PDF.
# Requiere Microsoft Word. Uso: .\word_pdf.ps1 -Docx memoria.docx -Pdf memoria.pdf
param([Parameter(Mandatory)][string]$Docx, [Parameter(Mandatory)][string]$Pdf)
$ErrorActionPreference = "Stop"
$Docx = (Resolve-Path -LiteralPath $Docx).Path
$Pdf = [System.IO.Path]::GetFullPath($Pdf, (Get-Location).Path)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($Docx, $false, $false)
    if ($null -eq $doc) { throw "Word no pudo abrir $Docx" }
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Save()
    $doc.ExportAsFixedFormat($Pdf, 17)
    "paginas: " + $doc.ComputeStatistics(2)
    $doc.Close($false)
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
