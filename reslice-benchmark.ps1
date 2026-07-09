<#
.SYNOPSIS
  Đo thời gian in / khối lượng của một file .3mf bằng slicer CLI (không cần mở GUI).
  Kèm chế độ -Variants: tự sinh các phương án tối ưu (phẳng 0.2 / 0.24 / combo) và so sánh.

.DESCRIPTION
  OrcaSlicer 2.4.x CLI crash headless (0xC0000005) → tool ưu tiên Bambu Studio CLI.
  Đọc kết quả từ result.json (total_predication giây, feature_type_times, filaments[].main_used_g)
  và total layer number từ gcode header. Có vòng retry vì Bambu Studio CLI đôi khi crash ngẫu nhiên.

.EXAMPLE
  powershell -File reslice-benchmark.ps1 -Input "C:\Users\Admin\Downloads\Body 14 - LP.3mf"
.EXAMPLE
  powershell -File reslice-benchmark.ps1 -Input "...\Body 14 - LP.3mf" -Variants
#>
param(
  [Parameter(Mandatory=$true)][string]$Input,
  [switch]$Variants,
  [int]$Retry = 4
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

# --- Tìm slicer CLI ---
$SLICERS = @(
  "C:\Program Files\Bambu Studio\bambu-studio.exe",
  "C:\Program Files\OrcaSlicer\orca-slicer.exe"
)
$EXE = $SLICERS | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $EXE) { throw "Khong tim thay Bambu Studio / OrcaSlicer." }
Write-Host "Slicer: $EXE" -ForegroundColor Cyan

function HM([double]$s){ $s=[int]$s; "{0}h{1:00}m" -f [math]::Floor($s/3600), [math]::Floor(($s%3600)/60) }

# --- Slice 1 file, retry neu crash, tra ve object ket qua ---
function Invoke-Slice([string]$in, [string]$tag){
  for($i=1; $i -le $Retry; $i++){
    $od = Join-Path $env:TEMP ("rb_{0}_{1}" -f ($tag -replace '[^A-Za-z0-9]','_'), $i)
    New-Item -ItemType Directory -Force $od | Out-Null
    $p = Start-Process -FilePath $EXE -ArgumentList "--slice 0 --outputdir `"$od`" `"$in`"" `
         -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$od\o.txt" -RedirectStandardError "$od\e.txt"
    if (Test-Path "$od\result.json") {
      $r = Get-Content "$od\result.json" -Raw | ConvertFrom-Json
      $sp = $r.sliced_plates[0]
      $lay = (Select-String -Path "$od\plate_1.gcode" -Pattern "total layer number: (\d+)" | Select-Object -First 1).Matches.Groups[1].Value
      return [pscustomobject]@{
        Variant = $tag; Time = HM($sp.total_predication); Sec = [int]$sp.total_predication
        Grams = [math]::Round($sp.filaments[0].main_used_g,1); Layers = $lay; Tries = $i; Dir = $od
      }
    }
    Write-Host ("  [{0}] crash lan {1}/{2} (exit {3}) - retry..." -f $tag,$i,$Retry,$p.ExitCode) -ForegroundColor DarkYellow
  }
  return [pscustomobject]@{ Variant=$tag; Time="CRASH x$Retry"; Sec=0; Grams="-"; Layers="-"; Tries=$Retry; Dir="-" }
}

# --- Sinh variant: copy 3mf, sua Metadata/project_settings.config, tuy chon bo VLH profile ---
function New-Variant([string]$src, [string]$dst, [array]$pairs, [bool]$removeProfile){
  Copy-Item -LiteralPath $src -Destination $dst -Force
  $zip = [System.IO.Compression.ZipFile]::Open($dst,'Update')
  try {
    $e = $zip.Entries | Where-Object { $_.FullName -eq 'Metadata/project_settings.config' }
    $sr = New-Object System.IO.StreamReader($e.Open()); $txt = $sr.ReadToEnd(); $sr.Dispose()
    foreach($p in $pairs){ $txt = $txt.Replace($p[0], $p[1]) }
    $e.Delete()
    $ne = $zip.CreateEntry('Metadata/project_settings.config')
    $sw = New-Object System.IO.StreamWriter($ne.Open()); $sw.Write($txt); $sw.Dispose()
    if ($removeProfile) {
      $lp = $zip.Entries | Where-Object { $_.FullName -eq 'Metadata/layer_heights_profile.txt' }
      if ($lp) { $lp.Delete() }
    }
  } finally { $zip.Dispose() }
}

# ================= chay =================
$out = @()
$out += Invoke-Slice $Input "0-baseline"

if ($Variants) {
  $tmp = $env:TEMP
  New-Variant $Input "$tmp\rb_flat02.3mf"  @() $true
  $out += Invoke-Slice "$tmp\rb_flat02.3mf" "flat0.2"

  New-Variant $Input "$tmp\rb_flat024.3mf" @(
    @('"layer_height": "0.2"','"layer_height": "0.24"'),
    @('"initial_layer_print_height": "0.2"','"initial_layer_print_height": "0.24"')) $true
  $out += Invoke-Slice "$tmp\rb_flat024.3mf" "flat0.24"

  New-Variant $Input "$tmp\rb_combo.3mf" @(
    @('"layer_height": "0.2"','"layer_height": "0.24"'),
    @('"initial_layer_print_height": "0.2"','"initial_layer_print_height": "0.24"'),
    @('"sparse_infill_density": "10%"','"sparse_infill_density": "8%"'),
    @('"top_shell_layers": "5"','"top_shell_layers": "4"'),
    @('"enable_support": "1"','"enable_support": "0"')) $true
  $out += Invoke-Slice "$tmp\rb_combo.3mf" "combo(0.24+i8+t4+nosup)"
}

Write-Host "`n=== KET QUA ===" -ForegroundColor Green
$base = ($out | Where-Object { $_.Variant -eq '0-baseline' }).Sec
$out | ForEach-Object {
  $delta = if ($base -gt 0 -and $_.Sec -gt 0 -and $_.Variant -ne '0-baseline') { "{0:P0}" -f (($_.Sec - $base)/$base) } else { "" }
  $_ | Add-Member -NotePropertyName "Delta" -NotePropertyValue $delta -PassThru
} | Format-Table Variant, Time, Delta, Layers, Grams, Tries -AutoSize
