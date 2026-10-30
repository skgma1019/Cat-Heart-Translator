param(
  [string]$DatasetRoot = '',
  [string]$OutputDir = (Join-Path $env:USERPROFILE 'Desktop')
)
$ErrorActionPreference = 'Stop'
if (-not $DatasetRoot -or -not (Test-Path -LiteralPath $DatasetRoot -PathType Container)) { throw "Pass the existing dataset folder with -DatasetRoot. Path: $DatasetRoot" }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$samplesDir = Join-Path $OutputDir "cat-heart-label-samples-$stamp"
New-Item -ItemType Directory -Path $samplesDir | Out-Null
$index = @()
$labelPrefix = '[' + [char]0xB77C + [char]0xBCA8 + ']'
$sourcePrefix = '[' + [char]0xC6D0 + [char]0xCC9C + ']'
$archives = @(Get-ChildItem -LiteralPath $DatasetRoot -Recurse -File | Where-Object { $_.Name.StartsWith($labelPrefix) -and $_.Extension -ieq '.zip' })
if ($archives.Count -eq 0) { throw "No label ZIP archives found under: $DatasetRoot" }
Write-Host "Label ZIP archives found: $($archives.Count)"
foreach ($file in $archives) {
  $animal = $file.Directory.Name
  $split = $file.Directory.Parent.Name
  if ($animal -eq 'DOG' -and $file.Name -ne ($labelPrefix + 'BODYLOWER.zip')) { continue }
  $class = $file.BaseName.Substring(4)
  $zip = [System.IO.Compression.ZipFile]::OpenRead($file.FullName)
  try {
    $selected = @{}
    foreach ($entry in $zip.Entries) {
      if (-not $entry.Name.EndsWith('.json')) { continue }
      $kind = if ($entry.Name.EndsWith('.mp4.json')) { 'video' } else { 'other' }
      if (-not $selected.ContainsKey($kind)) { $selected[$kind] = $entry }
      if ($selected.Count -eq 2) { break }
    }
    foreach ($kind in $selected.Keys) {
      $entry = $selected[$kind]
      $name = "${split}_${animal}_${class}_${kind}.json"
      $destination = Join-Path $samplesDir $name
      $inputStream = $entry.Open()
      $outputStream = [System.IO.File]::Create($destination)
      try { $inputStream.CopyTo($outputStream) }
      finally { $outputStream.Dispose(); $inputStream.Dispose() }
      $index += [pscustomobject]@{ sample = $name; archive = $file.FullName; entry = $entry.FullName; size_bytes = $entry.Length }
    }
  } finally { $zip.Dispose() }
  $sourcePath = Join-Path $file.DirectoryName ($file.Name.Replace($labelPrefix, $sourcePrefix))
  if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
    $sourceZip = [System.IO.Compression.ZipFile]::OpenRead($sourcePath)
    try {
      $prefixes = @{}
      foreach ($kind in $selected.Keys) {
        $clip = $selected[$kind].Name.Substring(0, $selected[$kind].Name.Length - 5)
        $prefixes[$kind] = "$class/$clip/"
      }
      $found = @{}
      foreach ($entry in $sourceZip.Entries) {
        if (-not $entry.Name.EndsWith('.jpg')) { continue }
        foreach ($kind in $prefixes.Keys) {
          if ($found.ContainsKey($kind) -or -not $entry.FullName.StartsWith($prefixes[$kind], [System.StringComparison]::OrdinalIgnoreCase)) { continue }
          $name = "${split}_${animal}_${class}_${kind}.jpg"
          $destination = Join-Path $samplesDir $name
          $inputStream = $entry.Open()
          $outputStream = [System.IO.File]::Create($destination)
          try { $inputStream.CopyTo($outputStream) }
          finally { $outputStream.Dispose(); $inputStream.Dispose() }
          $index += [pscustomobject]@{ sample = $name; archive = $sourcePath; entry = $entry.FullName; size_bytes = $entry.Length }
          $found[$kind] = $true
        }
        if ($found.Count -eq $prefixes.Count) { break }
      }
    } finally { $sourceZip.Dispose() }
  }
}
if ($index.Count -eq 0) { throw 'No JSON or JPG samples were copied.' }
$index | Export-Csv -LiteralPath (Join-Path $samplesDir 'sample_index.csv') -NoTypeInformation -Encoding UTF8
$destinationZip = Join-Path $OutputDir "cat-heart-label-samples-$stamp.zip"
Compress-Archive -Path (Join-Path $samplesDir '*') -DestinationPath $destinationZip
Write-Host "Sample ZIP saved to: $destinationZip"
Write-Host 'Source ZIP files were only read. No full extraction was performed.'
