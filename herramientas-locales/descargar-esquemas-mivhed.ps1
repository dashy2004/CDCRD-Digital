# Descarga únicamente esquemas públicos. El directorio final debe ser nuevo.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Destino)
$ErrorActionPreference = 'Stop'
$api = 'https://wa-vuc-prod-normapi.azurewebsites.net/api/public'
$final = [IO.Path]::GetFullPath($Destino)
if ([IO.File]::Exists($final) -or [IO.Directory]::Exists($final)) {
    throw 'El destino ya existe. Indique una carpeta nueva para esta captura.'
}
$padre = [IO.Path]::GetDirectoryName($final)
[void][IO.Directory]::CreateDirectory($padre)
$tmp = Join-Path $padre ('.esquemas-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $tmp -ErrorAction Stop)
try {
    $ids = [Collections.Generic.HashSet[int]]::new()
    $captura = [Collections.Generic.List[object]]::new()
    $pagina = 1
    do {
        $lista = Invoke-RestMethod "$api/templates?page=$pagina&pageSize=20" -TimeoutSec 40
        if ($lista.page -ne $pagina -or $lista.totalPages -lt $pagina -or $lista.totalPages -gt 1000) {
            throw 'Paginación no reconocida en el portal.'
        }
        foreach ($version in $lista.items) {
            $id = [int]$version.id
            if ($id -lt 1 -or !$ids.Add($id)) { throw "Versión inválida o repetida: $id" }
            $url = "$api/schemas/templates/$id"
            $archivo = Join-Path $tmp "schema$id.json"
            Invoke-WebRequest -UseBasicParsing $url -OutFile $archivo -TimeoutSec 40
            $datos = Get-Content -Raw -Encoding UTF8 -LiteralPath $archivo | ConvertFrom-Json
            if ($datos.jsonSchema.x_template_version.templateVersionId -ne $id -or
                $datos.jsonSchema.x_template.code -cne $version.template.code) {
                throw "Respuesta incompatible con la plantilla anunciada: $id"
            }
            $captura.Add([ordered]@{versionId=$id; codigo=$version.template.code; url=$url;
                sha256=(Get-FileHash -LiteralPath $archivo).Hash})
        }
        $pagina++
    } while ($pagina -le $lista.totalPages)
    if ($ids.Count -eq 0 -or $ids.Count -ne $lista.totalItems) {
        throw 'El número de esquemas descargados difiere del total anunciado.'
    }
    $indice = [ordered]@{consultadoUtc=[DateTime]::UtcNow.ToString('o'); esquemas=$captura}
    [IO.File]::WriteAllText((Join-Path $tmp 'captura.json'), ($indice | ConvertTo-Json -Depth 4))
    [IO.Directory]::Move($tmp, $final)
    Write-Output ("Esquemas descargados y verificados: {0}" -f $ids.Count)
} finally {
    # El temporal es hijo directo del padre elegido y su nombre se genera en esta ejecución.
    if ([IO.Directory]::Exists($tmp)) {
        foreach ($archivo in [IO.Directory]::EnumerateFiles($tmp)) { [IO.File]::Delete($archivo) }
        [IO.Directory]::Delete($tmp)
    }
}
