param(
  [string]$DatasetRoot = 'E:\냥심번역기 데이터셋\반려동물 구분을 위한 동물 영상',
  [string]$OutputDir = (Join-Path $env:USERPROFILE 'Desktop\cat-heart-dataset-audit')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $DatasetRoot -PathType Container)) { throw "Dataset folder not found: $DatasetRoot" }
$root = (Resolve-Path -LiteralPath $DatasetRoot).Path.TrimEnd('\')
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$files = Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction Stop
$manifest = foreach ($file in $files) {
  [pscustomobject]@{
    relative_path = $file.FullName.Substring($root.Length + 1)
    extension = $file.Extension.ToLowerInvariant()
    size_bytes = $file.Length
    directory = $file.DirectoryName.Substring($root.Length).TrimStart('\')
  }
}
$manifest | Export-Csv -LiteralPath (Join-Path $OutputDir 'files.csv') -NoTypeInformation -Encoding UTF8
$manifest | Group-Object extension | Sort-Object Name | ForEach-Object {
  [pscustomobject]@{ extension = $_.Name; file_count = $_.Count; size_bytes = ($_.Group | Measure-Object size_bytes -Sum).Sum }
} | Export-Csv -LiteralPath (Join-Path $OutputDir 'extension_counts.csv') -NoTypeInformation -Encoding UTF8
[pscustomobject]@{ root = $root; file_count = $files.Count; size_bytes = ($files | Measure-Object Length -Sum).Sum } |
  ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDir 'summary.json') -Encoding UTF8

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipEntries = foreach ($file in $files | Where-Object { $_.Extension -ieq '.zip' }) {
  try {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($file.FullName)
    try {
      foreach ($entry in $archive.Entries) {
        [pscustomobject]@{ archive = $file.FullName.Substring($root.Length + 1); entry = $entry.FullName; size_bytes = $entry.Length }
      }
    } finally { $archive.Dispose() }
  } catch {
    [pscustomobject]@{ archive = $file.FullName.Substring($root.Length + 1); entry = '[READ ERROR] ' + $_.Exception.Message; size_bytes = 0 }
  }
}
$zipEntries | Export-Csv -LiteralPath (Join-Path $OutputDir 'zip_entries.csv') -NoTypeInformation -Encoding UTF8

$jsonSamples = foreach ($file in $files | Where-Object { $_.Extension -ieq '.json' } | Select-Object -First 30) {
  try {
    $data = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $sample = if ($data -is [array]) { @($data | Select-Object -First 2) } else { $data }
    [pscustomobject]@{ path = $file.FullName.Substring($root.Length + 1); sample = $sample }
  } catch {
    [pscustomobject]@{ path = $file.FullName.Substring($root.Length + 1); error = $_.Exception.Message }
  }
}
$jsonSamples | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDir 'json_samples.json') -Encoding UTF8
Write-Host "Inventory saved to: $OutputDir"
Write-Host 'Source files were only read. ZIP files were listed without extraction.'
