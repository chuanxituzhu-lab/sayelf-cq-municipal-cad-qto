#requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$AcceptOdaTerms,
    [switch]$CheckOnly,
    [switch]$Force,
    [string]$InstallRoot,
    [string]$OdaMsiPath
)

$ErrorActionPreference = "Stop"

$odaDownloadUrl = "https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_vc16_amd64dll_27.1.msi"
$odaMsiSha256 = "3D5961F510CF95F398B8E2920899DC8E8C51ADECDAF5B20A40B3D1A29269DE81"
$converterEnvironmentName = "MUNICIPAL_QTO_DWG_CONVERTER"

function Resolve-FullPath([string]$PathValue) {
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Get-DefaultInstallRoot {
    if (Test-Path -LiteralPath "D:\") {
        return "D:\ODA\ODAFileConverter"
    }
    return Join-Path $env:LOCALAPPDATA "SAYELF\ODAFileConverter"
}

function Find-Converter([string]$PreferredRoot) {
    $candidates = @()
    $configured = [Environment]::GetEnvironmentVariable($converterEnvironmentName, "User")
    if ($configured) {
        $candidates += $configured.Trim().Trim('"')
    }
    $processConfigured = [Environment]::GetEnvironmentVariable($converterEnvironmentName, "Process")
    if ($processConfigured) {
        $candidates += $processConfigured.Trim().Trim('"')
    }
    $candidates += (Join-Path $PreferredRoot "ODAFileConverter.exe")
    $candidates += "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
    $candidates += "C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe"
    $candidates += "D:\ODA\ODAFileConverter\ODAFileConverter.exe"
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-FullPath $candidate)
        }
    }
    foreach ($commandName in @("ODAFileConverter.exe", "ODAFileConverter")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            return (Resolve-FullPath $command.Source)
        }
    }
    return $null
}

function Assert-OdaSignature([string]$PathValue, [string]$Label) {
    $signature = Get-AuthenticodeSignature -LiteralPath $PathValue
    if ($signature.Status -ne "Valid") {
        throw "$Label 数字签名校验失败：$($signature.Status)"
    }
    if (-not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch "OPEN DESIGN ALLIANCE") {
        throw "$Label 签名方不是 Open Design Alliance"
    }
}

function Set-ConverterConfiguration([string]$PathValue) {
    [Environment]::SetEnvironmentVariable($converterEnvironmentName, $PathValue, "User")
    Set-Item -Path "Env:$converterEnvironmentName" -Value $PathValue
}

if (-not $InstallRoot) {
    $InstallRoot = Get-DefaultInstallRoot
}
$InstallRoot = Resolve-FullPath $InstallRoot
$converterPath = Find-Converter $InstallRoot

if ($converterPath -and -not $Force) {
    Assert-OdaSignature $converterPath "ODAFileConverter.exe"
    Set-ConverterConfiguration $converterPath
    [pscustomobject]@{
        Status = "READY"
        Converter = $converterPath
        Configuration = $converterEnvironmentName
        Message = "本机 ODA File Converter 已就绪"
    } | ConvertTo-Json -Compress
    exit 0
}

if ($CheckOnly) {
    [pscustomobject]@{
        Status = "MISSING"
        ExpectedInstallRoot = $InstallRoot
        Message = "未发现 ODA File Converter；请运行本脚本并确认 ODA 使用条款"
    } | ConvertTo-Json -Compress
    exit 2
}

if (-not $AcceptOdaTerms) {
    Write-Host "ODA File Converter 是 Open Design Alliance 的独立软件，本工具不重新分发其二进制。"
    Write-Host "请确认你已阅读并接受 ODA 官方使用条款；商业分发前需取得相应授权。"
    $confirmation = Read-Host "确认后输入 INSTALL"
    if ($confirmation -ne "INSTALL") {
        throw "未确认 ODA 使用条款，已取消安装"
    }
}

$workingRoot = Join-Path $env:TEMP ("sayelf-cq-oda-" + [guid]::NewGuid().ToString("N"))
$downloadedMsi = Join-Path $workingRoot "ODAFileConverter.msi"
$extractRoot = Join-Path $workingRoot "extracted"
$installLog = Join-Path $workingRoot "oda-install.log"
New-Item -ItemType Directory -Path $workingRoot,$extractRoot -Force | Out-Null

try {
    if ($OdaMsiPath) {
        $OdaMsiPath = Resolve-FullPath $OdaMsiPath
        if (-not (Test-Path -LiteralPath $OdaMsiPath -PathType Leaf)) {
            throw "指定的离线 MSI 不存在：$OdaMsiPath"
        }
        Copy-Item -LiteralPath $OdaMsiPath -Destination $downloadedMsi
    } else {
        Write-Host "正在从 ODA 官方下载页获取 ODA File Converter..."
        Invoke-WebRequest -UseBasicParsing -Uri $odaDownloadUrl -OutFile $downloadedMsi
    }

    $actualHash = (Get-FileHash -LiteralPath $downloadedMsi -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actualHash -ne $odaMsiSha256) {
        throw "ODA MSI SHA-256 不匹配；期望 $odaMsiSha256，实际 $actualHash"
    }
    Assert-OdaSignature $downloadedMsi "ODA MSI"

    $arguments = @(
        "/a", $downloadedMsi,
        "TARGETDIR=$extractRoot",
        "/qn", "/norestart",
        "/L*v", $installLog
    )
    $process = Start-Process -FilePath "msiexec.exe" -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "ODA MSI 提取失败，Windows Installer 返回码：$($process.ExitCode)；日志：$installLog"
    }

    $extractedConverter = Join-Path $extractRoot "ODAFileConverter.exe"
    if (-not (Test-Path -LiteralPath $extractedConverter -PathType Leaf)) {
        throw "ODA MSI 提取完成但未找到 ODAFileConverter.exe；日志：$installLog"
    }
    Assert-OdaSignature $extractedConverter "提取后的 ODAFileConverter.exe"

    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $extractRoot -Force | Copy-Item -Destination $InstallRoot -Recurse -Force
    $converterPath = Join-Path $InstallRoot "ODAFileConverter.exe"
    if (-not (Test-Path -LiteralPath $converterPath -PathType Leaf)) {
        throw "ODA 文件已提取但目标路径没有 ODAFileConverter.exe：$InstallRoot"
    }
    Assert-OdaSignature $converterPath "目标路径的 ODAFileConverter.exe"
    Set-ConverterConfiguration (Resolve-FullPath $converterPath)

    [pscustomobject]@{
        Status = "INSTALLED"
        Converter = (Resolve-FullPath $converterPath)
        Configuration = $converterEnvironmentName
        MsiSha256 = $actualHash
        Message = "ODA File Converter 已从官方来源校验并提取到本机；请重新启动 WebUI"
    } | ConvertTo-Json -Compress
} finally {
    if (Test-Path -LiteralPath $workingRoot) {
        Remove-Item -LiteralPath $workingRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
