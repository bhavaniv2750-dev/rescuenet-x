<#
 RescueNet X: regional (South India) vector tile pipeline for Windows PowerShell 5.1 / 7.
 NOT EXECUTED in the cloud build environment (no Windows, no real PBF there). Start with `-Step Check`; every step prints what it will do.

 Steps:  Check | Setup | Validate | Benchmark | Build | Search | Verify | Serve | Clean
 Example: .\regional-gis.ps1 -Step Check

 Isolation: everything (JDK, Maven, Planetiler/Protomaps profile, Python venv, temp files, output) lives under -Work (default C:\RescueNetGIS).
 Nothing is installed system-wide and your FastAPI / React environments are not touched. The original PBF is only ever READ.
 Keep -Work OUTSIDE OneDrive (OneDrive would try to sync gigabytes of temporary files).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][ValidateSet('Check', 'Setup', 'Validate', 'Benchmark', 'Build', 'Search', 'Verify', 'Serve', 'Clean')][string]$Step,
  [string]$Pbf = 'C:\Users\Bhavana\OneDrive\Documents\Flood degi twin rescuenet X\datasets\southern-zone-261124.osm.pbf',
  [string]$Work = 'C:\RescueNetGIS',
  [string]$Frontend = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
  [int]$HeapGB = 3,          # Java heap. Planetiler's guidance is about 0.5x the PBF size (about 0.3 GB here); 3 GB leaves headroom and stays inside the 2-4 GB target.
  [int]$Threads = 4,         # of 12 logical CPUs on an i5-13420H: keeps the laptop responsive.
  [int]$JdkVersion = 25,     # newest LTS: satisfies "Java 21+" (Protomaps profile) and "Java 25+" (current Planetiler README). Lower it if your checkout's pom says otherwise.
  [switch]$Approve,          # required for -Step Build (explicit approval of the resource budget after reviewing the Benchmark)
  [switch]$Tools             # with -Step Clean: also remove the downloaded JDK/Maven/profile build (re-downloadable)
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$dirTools = Join-Path $Work 'tools'; $dirSrc = Join-Path $Work 'src'; $dirTmp = Join-Path $Work 'tmp'; $dirOut = Join-Path $Work 'out'; $venv = Join-Path $Work 'venv'
$jdkHome = Join-Path $dirTools 'jdk'; $mvnHome = Join-Path $dirTools 'maven'; $profile = Join-Path $dirSrc 'basemaps'
$archive = Join-Path $dirOut 'south-india.pmtiles'; $bench = Join-Path $dirOut 'benchmark-bengaluru.pmtiles'
$BengaluruBounds = '77.35,12.75,77.85,13.25'

function Say($m) { Write-Host "[regional-gis] $m" }
function Need-Tool($path, $what) { if (-not (Test-Path $path)) { throw "$what not found at $path. Run: .\regional-gis.ps1 -Step Setup" } }
function Free-GB($path) { $root = (Get-Item $path -ErrorAction SilentlyContinue); $drive = if ($path -match '^([A-Za-z]):') { $Matches[1] } else { 'C' }; [math]::Round((Get-PSDrive $drive).Free / 1GB, 1) }
function Use-Jdk { $env:JAVA_HOME = $jdkHome; $env:PATH = "$jdkHome\bin;$mvnHome\bin;$env:PATH" }
function Profile-Jar { Get-ChildItem (Join-Path $profile 'tiles\target') -Filter '*with-deps.jar' -ErrorAction SilentlyContinue | Select-Object -First 1 }
function Assert-Flags($helpText, [string[]]$required, $what) {
  # Fail clearly if the installed Planetiler/profile does not list an option we depend on (never silently drop a required option).
  $missing = @(); foreach ($r in $required) { if ($helpText -notmatch [regex]::Escape($r)) { $missing += $r } }
  if ($missing.Count -gt 0) { throw ("$what: this build does not list required option(s): " + ($missing -join ', ') + ". Compare with: java -jar <profile jar> --help-all . Update the script (or the profile checkout) before continuing; nothing was run.") }
}
function Py { Join-Path $venv 'Scripts\python.exe' }

function Run-Measured($exe, $argList, $logName) {
  # Runs a process at BelowNormal priority and records elapsed time and PEAK working set (measured, not estimated).
  $log = Join-Path $Work $logName
  $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $dirSrc -PassThru -NoNewWindow -RedirectStandardOutput $log -RedirectStandardError "$log.err"
  try { $p.PriorityClass = 'BelowNormal' } catch { }
  $sw = [Diagnostics.Stopwatch]::StartNew(); $peak = 0; $tmpPeak = 0; $i = 0
  while (-not $p.HasExited) {
    try { $p.Refresh(); if ($p.PeakWorkingSet64 -gt $peak) { $peak = $p.PeakWorkingSet64 } } catch { }
    $i++; if (($i % 5) -eq 0) { $t = (Get-ChildItem $dirTmp -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum; if ($t -gt $tmpPeak) { $tmpPeak = $t } }
    Start-Sleep -Seconds 2
  }
  $sw.Stop()
  Say ("exit code {0}; elapsed {1:N1} min; PEAK working set {2:N2} GB (Java process); PEAK temp folder {3:N2} GB (sampled every 10 s); logs: {4}" -f $p.ExitCode, $sw.Elapsed.TotalMinutes, ($peak / 1GB), ($tmpPeak / 1GB), $log)
  if ($p.ExitCode -ne 0) { Get-Content "$log.err" -Tail 25; throw 'Process failed. See the log above.' }
}

switch ($Step) {

  'Check' {
    Say 'System'
    $cs = Get-CimInstance Win32_ComputerSystem; $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    Say ("CPU: {0} ({1} cores / {2} logical)" -f $cpu.Name.Trim(), $cpu.NumberOfCores, $cpu.NumberOfLogicalProcessors)
    Say ("RAM: {0:N1} GB total, {1:N1} GB free" -f ($cs.TotalPhysicalMemory / 1GB), ((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB))
    Say 'Disk (free space per drive)'
    Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } | ForEach-Object { Say ("  {0}: {1:N1} GB free" -f $_.Name, ($_.Free / 1GB)) }
    $pbfGB = if (Test-Path $Pbf) { (Get-Item $Pbf).Length / 1GB } else { 0.53 }
    # Estimates (see docs/frontend/REGIONAL_GIS.md): Planetiler documents 5-10x the PBF size as temporary disk; sources, tools and output are our estimates.
    $tmpLo = 5 * $pbfGB; $tmpHi = 10 * $pbfGB; $src = 2.0; $toolsGB = 1.0; $outGB = 1.5
    $peak = $tmpHi + $src + $toolsGB + $outGB; $persist = $pbfGB + $toolsGB + $outGB + 0.05
    Say ("ESTIMATED temporary disk (peak): {0:N1} to {1:N1} GB + sources {2:N1} GB. ESTIMATED persistent after cleanup: about {3:N1} GB including the PBF (target 3 GB)." -f $tmpLo, ($tmpHi + $src), $src, $persist)
    $free = Free-GB $Work
    Say ("Free space on the drive of -Work ($Work): $free GB; required for the peak estimate: {0:N1} GB" -f $peak)
    if ($free -lt $peak -and -not $Approve) { Write-Warning 'Free space is below the estimated peak. STOP. Free up space or choose another -Work drive, or re-run later steps with -Approve if you accept the risk.' } else { Say 'Disk check: OK' }
    if ($Work -match 'OneDrive') { Write-Warning '-Work is inside OneDrive. Choose a path such as C:\RescueNetGIS.' }
    if (Test-Path $Pbf) { Say ("PBF found: {0:N2} GB" -f ((Get-Item $Pbf).Length / 1GB)) } else { Write-Warning "PBF not found at $Pbf" }
    foreach ($t in 'git', 'node', 'npm', 'python') { if (Get-Command $t -ErrorAction SilentlyContinue) { Say "$t : found" } else { Write-Warning "$t : NOT found (needed by Setup/Serve/Search)" } }
    Say 'GPU is not used by any step.'
  }

  'Setup' {
    foreach ($d in $dirTools, $dirSrc, $dirTmp, $dirOut) { New-Item -ItemType Directory -Force $d | Out-Null }
    if (-not (Test-Path "$jdkHome\bin\java.exe")) {
      Say "Downloading Temurin JDK $JdkVersion (portable zip, about 200 MB) into $jdkHome"
      $zip = Join-Path $dirTools 'jdk.zip'; curl.exe -fL --retry 3 -o $zip "https://api.adoptium.net/v3/binary/latest/$JdkVersion/ga/windows/x64/jdk/hotspot/normal/eclipse"
      $x = Join-Path $dirTools 'jdk-x'; Expand-Archive $zip $x -Force; Move-Item (Get-ChildItem $x | Select-Object -First 1).FullName $jdkHome; Remove-Item $x, $zip -Recurse -Force
    }
    if (-not (Test-Path "$mvnHome\bin\mvn.cmd")) {
      Say 'Downloading Apache Maven 3.9.9 (portable zip) into tools'
      $zip = Join-Path $dirTools 'maven.zip'; curl.exe -fL --retry 3 -o $zip 'https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.zip'
      $x = Join-Path $dirTools 'mvn-x'; Expand-Archive $zip $x -Force; Move-Item (Get-ChildItem $x | Select-Object -First 1).FullName $mvnHome; Remove-Item $x, $zip -Recurse -Force
    }
    Use-Jdk; java -version
    if (-not (Test-Path $profile)) { Say 'Cloning the Protomaps basemap profile (Planetiler based, BSD-3)'; git clone --depth 1 https://github.com/protomaps/basemaps.git $profile }
    if (-not (Profile-Jar)) { Say 'Building the profile jar (a few minutes, needs internet for Maven dependencies)'; Push-Location (Join-Path $profile 'tiles'); mvn -q -DskipTests clean package; Pop-Location }
    $jar = Profile-Jar; if (-not $jar) { throw 'Profile jar was not produced. Read the Maven output above.' }
    Say "Profile jar: $($jar.FullName)"
    if (-not (Test-Path (Py))) { Say 'Creating an isolated Python venv with pyosmium (only for PBF inspection and the search index)'; python -m venv $venv; & (Py) -m pip install --quiet osmium }
    Say 'Setup complete. Next: -Step Validate'
  }

  'Validate' {
    if (-not (Test-Path $Pbf)) { throw "PBF not found: $Pbf" }
    $f = Get-Item $Pbf
    Say ("Size {0:N2} MB (expected about 534 MB)" -f ($f.Length / 1MB))
    if ($f.Attributes -band 0x400000 -or $f.Attributes -band 0x40000) { Write-Warning 'File looks like an OneDrive online-only placeholder. Right-click it in Explorer and choose "Always keep on this device" first.' }
    $fs = [IO.File]::OpenRead($Pbf); $buf = New-Object byte[] 256; [void]$fs.Read($buf, 0, 256); $fs.Close()
    if ([Text.Encoding]::ASCII.GetString($buf) -match 'OSMHeader') { Say 'Header block "OSMHeader": present (looks like a real .osm.pbf)' } else { throw 'No OSMHeader block found: this is not a valid .osm.pbf file.' }
    Say 'SHA-256 (record this in your notes):'; (Get-FileHash $Pbf -Algorithm SHA256).Hash
    try { $md5 = (curl.exe -fsSL 'https://download.geofabrik.de/asia/india/southern-zone-261124.osm.pbf.md5') -split '\s+' | Select-Object -First 1; $mine = (Get-FileHash $Pbf -Algorithm MD5).Hash.ToLower()
      if ($md5 -eq $mine) { Say 'MD5 matches the Geofabrik checksum file.' } else { Write-Warning "MD5 differs from Geofabrik ($md5 vs $mine). Re-download the file." } } catch { Say 'Geofabrik .md5 not reachable; skipped (the OSMHeader check above still applies).' }
    if (Test-Path (Py)) {
      Say 'Geographical coverage from the PBF header (bounding box, west/south/east/north):'
      & (Py) -c "import sys, osmium; h = osmium.io.Reader(sys.argv[1]).header(); b = h.box(); print(b.bottom_left.lon, b.bottom_left.lat, b.top_right.lon, b.top_right.lat); print('generator:', h.get('generator'), '| timestamp:', h.get('osmosis_replication_timestamp'))" $Pbf
    } else { Say 'Run -Step Setup first to inspect the bounding box (needs the venv).' }
  }

  'Benchmark' {
    Need-Tool "$jdkHome\bin\java.exe" 'JDK'; $jar = Profile-Jar; if (-not $jar) { throw 'Profile jar missing. Run -Step Setup' }
    if ((Free-GB $Work) -lt 8 -and -not $Approve) { throw 'Less than 8 GB free: STOP (use -Approve to override).' }
    Use-Jdk
    $help = (& "$jdkHome\bin\java.exe" -jar $jar.FullName --help-all 2>&1 | Out-String)
    Assert-Flags $help @('--osm-path', '--output', '--bounds', '--download', '--force', '--tmpdir', '--threads', '--storage', '--nodemap-storage') 'Benchmark'
    Say "Benchmark: Bengaluru only ($BengaluruBounds) from the same PBF, heap ${HeapGB}g, $Threads threads, BelowNormal priority. Downloads Natural Earth / water polygon sources on first run."
    $a = @("-Xmx${HeapGB}g", '-jar', "`"$($jar.FullName)`"", "--osm-path=`"$Pbf`"", "--output=`"$bench`"", "--bounds=$BengaluruBounds", '--download', '--force', "--tmpdir=`"$dirTmp`"", "--threads=$Threads", '--storage=mmap', '--nodemap-storage=mmap')
    Run-Measured "$jdkHome\bin\java.exe" ($a -join ' ') 'benchmark.log'
    Say ("Benchmark archive: {0:N1} MB. Compare elapsed time and peak memory with your budget before running -Step Build." -f ((Get-Item $bench).Length / 1MB))
  }

  'Build' {
    Need-Tool "$jdkHome\bin\java.exe" 'JDK'; $jar = Profile-Jar; if (-not $jar) { throw 'Profile jar missing. Run -Step Setup' }
    if (-not (Test-Path (Join-Path $Work 'benchmark.log'))) { throw 'Run -Step Benchmark first and review its measured time, peak memory and temp usage.' }
    if (-not $Approve) { throw 'The full build is NOT approved automatically (estimated 8 to 11 GB of temporary disk). Review the Benchmark numbers, then re-run with -Approve to confirm the resource budget.' }
    $need = 12; if ((Free-GB $Work) -lt $need) { throw "Less than $need GB free on the -Work drive: STOP. Free space or choose another -Work drive." }
    Use-Jdk
    $help = (& "$jdkHome\bin\java.exe" -jar $jar.FullName --help-all 2>&1 | Out-String)
    Assert-Flags $help @('--osm-path', '--output', '--download', '--force', '--tmpdir', '--threads', '--storage', '--nodemap-storage') 'Build'
    $flags = @("-Xmx${HeapGB}g", '-jar', "`"$($jar.FullName)`"", "--osm-path=`"$Pbf`"", "--output=`"$archive`"", '--download', '--force', "--tmpdir=`"$dirTmp`"", "--threads=$Threads", '--storage=mmap', '--nodemap-storage=mmap')
    Say "Generating the regional archive. Heap ${HeapGB}g, $Threads threads. Expect tens of minutes; the laptop stays usable (BelowNormal priority)."
    Run-Measured "$jdkHome\bin\java.exe" ($flags -join ' ') 'build.log'
    $prov = [ordered]@{ built = (Get-Date -Format 'yyyy-MM-dd'); source_pbf = (Split-Path $Pbf -Leaf); source_bytes = (Get-Item $Pbf).Length; pbf_sha256 = (Get-FileHash $Pbf -Algorithm SHA256).Hash; archive_bytes = (Get-Item $archive).Length; profile = 'protomaps/basemaps (Planetiler)'; licence = 'ODbL 1.0, (c) OpenStreetMap contributors; Natural Earth public domain' }
    $prov | ConvertTo-Json | Set-Content (Join-Path $dirOut 'provenance.json') -Encoding UTF8
    Say ("Archive: {0:N0} MB at {1}" -f ((Get-Item $archive).Length / 1MB), $archive)
    Say 'Next: -Step Verify, then -Step Search, then -Step Serve'
  }

  'Search' {
    Need-Tool (Py) 'Python venv'
    Say 'Building the compact offline place index (streaming; ways use a disk-backed index in tmp and are deleted afterwards). Add -nodes-only manually in the script call for less disk.'
    & (Py) (Join-Path $Frontend 'scripts\build_search_index.py') --pbf $Pbf --out (Join-Path $dirOut 'search') --tmp (Join-Path $dirTmp 'search')
    Say ("Search index size: {0:N1} MB" -f ((Get-ChildItem (Join-Path $dirOut 'search') -Recurse | Measure-Object Length -Sum).Sum / 1MB))
  }

  'Verify' {
    $target = if (Test-Path $archive) { $archive } elseif (Test-Path $bench) { $bench } else { throw 'No archive found. Run -Step Build (or Benchmark).' }
    Push-Location $Frontend; node scripts\pmtiles_inspect.mjs $target; Pop-Location
    Say 'Check the printed bounds against the PBF bounding box from -Step Validate, and that layers include earth, water, roads, buildings, landuse, places, pois, boundaries.'
  }

  'Serve' {
    Say "Serving $dirOut at http://127.0.0.1:8077/ (Range requests, localhost only). Leave this window open; start the app in another window."
    Say 'In the frontend window:  $env:VITE_REGIONAL_PMTILES_URL = "http://127.0.0.1:8077/south-india.pmtiles"; npm run dev'
    Push-Location $Frontend; node scripts\serve_tiles.mjs $dirOut 8077; Pop-Location
  }

  'Clean' {
    if (-not (Test-Path $archive)) { throw 'No finished archive found; refusing to clean while nothing has been validated.' }
    Push-Location $Frontend; node scripts\pmtiles_inspect.mjs $archive | Out-Null; $ok = $LASTEXITCODE; Pop-Location
    if ($ok -ne 0) { throw 'The archive did not validate; temporary files are kept.' }
    foreach ($d in $dirTmp, (Join-Path $dirSrc 'data\sources'), $bench, (Join-Path $Work 'benchmark.log'), (Join-Path $Work 'benchmark.log.err')) { if (Test-Path $d) { Say "Removing $d"; Remove-Item $d -Recurse -Force } }
    if ($Tools) { foreach ($d in $dirTools, $profile, $venv) { if (Test-Path $d) { Say "Removing $d"; Remove-Item $d -Recurse -Force } } }
    Say 'The original PBF was not touched. Remaining under -Work:'; Get-ChildItem $Work -Recurse -File | Measure-Object Length -Sum | ForEach-Object { Say ("{0:N2} GB" -f ($_.Sum / 1GB)) }
  }
}
