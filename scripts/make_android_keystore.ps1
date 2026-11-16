# Creates the Android release signing key for Rishu and walks you through
# adding it to GitHub, so every APK is signed with the same key.
#
# Run once on your Windows laptop:   powershell -ExecutionPolicy Bypass -File scripts\make_android_keystore.ps1
#
# The key is saved in  <your user folder>\rishu-signing  (outside the project).
# Keep a private backup of that folder. Never share it and never put it in the repo:
# whoever has this key can publish updates that look like they come from you.
$ErrorActionPreference = "Stop"

$repo = "neeleshyadav603/RishuAI"
$folder = Join-Path $HOME "rishu-signing"
$keystore = Join-Path $folder "rishu-upload.jks"
$alias = "rishu"

function Find-Keytool {
    $command = Get-Command keytool -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @()
    if ($env:JAVA_HOME) { $candidates += (Join-Path $env:JAVA_HOME "bin\keytool.exe") }
    $candidates += "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
    $candidates += Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Filter keytool.exe -Recurse -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName }
    foreach ($path in $candidates) { if ($path -and (Test-Path $path)) { return $path } }
    return $null
}

$keytool = Find-Keytool
if (-not $keytool) {
    Write-Host "Java is needed for this one step. Install it with this command, then run this script again:" -ForegroundColor Yellow
    Write-Host "    winget install EclipseAdoptium.Temurin.17.JDK"
    exit 1
}

if (Test-Path $keystore) {
    Write-Host "A signing key already exists at $keystore. Not creating a new one." -ForegroundColor Yellow
    Write-Host "Its password is in $folder\password.txt"
    $password = (Get-Content (Join-Path $folder "password.txt") -Raw).Trim()
} else {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = ([Convert]::ToBase64String($bytes)) -replace "[^A-Za-z0-9]", "x"
    & $keytool -genkeypair -keystore $keystore -storetype PKCS12 -keyalg RSA -keysize 2048 `
        -validity 10000 -alias $alias -storepass $password -keypass $password `
        -dname "CN=Rishu, O=Rishu, C=IN"
    if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
    Set-Content -Path (Join-Path $folder "password.txt") -Value $password -Encoding ASCII
    Write-Host "Created the signing key in $folder" -ForegroundColor Green
}

$base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($keystore))
$secrets = [ordered]@{
    "ANDROID_KEYSTORE_BASE64"   = $base64
    "ANDROID_KEYSTORE_PASSWORD" = $password
    "ANDROID_KEY_ALIAS"         = $alias
    "ANDROID_KEY_PASSWORD"      = $password
}

Write-Host ""
Write-Host "Now add 4 secrets on GitHub. For each one this script copies the value to the clipboard." -ForegroundColor Cyan
Write-Host "In the browser page that opens: type the Name shown here, paste (Ctrl+V) into 'Secret', click 'Add secret'."
foreach ($name in $secrets.Keys) {
    Set-Clipboard -Value $secrets[$name]
    Start-Process "https://github.com/$repo/settings/secrets/actions/new"
    Write-Host ""
    Write-Host "Name:  $name" -ForegroundColor Green
    Write-Host "Value: copied to the clipboard."
    Read-Host "Press Enter here after you clicked 'Add secret'"
}
Set-Clipboard -Value " "
Write-Host ""
Write-Host "Done. The next build signs the APK with your key." -ForegroundColor Green
Write-Host "Keep a private backup of the folder $folder (for example on a pen drive)."
