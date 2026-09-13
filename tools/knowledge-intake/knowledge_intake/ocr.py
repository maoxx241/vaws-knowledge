"""Optional OCR using installed OS/tool capabilities; no model downloads."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from pathlib import Path

from .common import IntakeError, command

_WINDOWS_SCRIPT = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null=[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
function AwaitOperation($Operation,$ResultType) {
  $method=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'} | Select-Object -First 1
  $task=$method.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
  $task.Wait()
  $task.Result
}
$memory=[System.IO.MemoryStream]::new([System.IO.File]::ReadAllBytes($env:KNOWLEDGE_INTAKE_OCR_FILE))
try {
  $randomAccess=[System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($memory)
  $decoder=AwaitOperation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($randomAccess)) ([Windows.Graphics.Imaging.BitmapDecoder])
  if ($decoder.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or $decoder.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) { throw 'Image exceeds Windows OCR dimensions' }
  $bitmap=AwaitOperation ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  try {
    if ($env:KNOWLEDGE_INTAKE_OCR_LANGUAGE) { $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($env:KNOWLEDGE_INTAKE_OCR_LANGUAGE)) }
    else { $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
    if ($null -eq $engine) { throw 'Requested Windows OCR language is not installed' }
    $result=AwaitOperation ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    @{text=$result.Text;language=$engine.RecognizerLanguage.LanguageTag;provider='windows'} | ConvertTo-Json -Compress
  } finally { $bitmap.Dispose() }
} finally { $memory.Dispose() }
'''


def capability(provider: str) -> dict:
    """Inspect already installed OCR resources, without installing or fetching any."""
    if provider == "windows":
        if os.name != "nt":
            return {"available": False, "reason": "Windows OCR is not an OS capability here", "languages": []}
        script = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
try {
  $null=[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
  $languages=@([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object {$_.LanguageTag})
  @{available=($languages.Count -gt 0);languages=$languages;reason='Installed Windows OCR resources'} | ConvertTo-Json -Compress
} catch {
  @{available=$false;languages=@();reason='Windows OCR WinRT capability unavailable on this OS image'} | ConvertTo-Json -Compress
}
'''
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        _, raw = command([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=15, max_bytes=16_384)
        return json.loads(raw.decode("utf-8-sig"))
    if provider != "tesseract":
        raise ValueError("OCR provider must be windows or tesseract")
    executable = shutil.which("tesseract")
    if not executable:
        return {"available": False, "reason": "tesseract executable is not installed", "languages": []}
    _, raw = command([executable, "--list-langs"], timeout=15, max_bytes=65_536)
    languages = [line.strip() for line in raw.decode("utf-8").splitlines() if re.fullmatch(r"[A-Za-z0-9_/-]+", line.strip())]
    return {"available": bool(languages), "languages": languages, "reason": "Installed tesseract language data"}


def recognize(path: Path, config: dict, *, timeout: float = 30, output_chars: int = 100_000) -> dict:
    provider = config.get("provider", "windows" if os.name == "nt" else "tesseract")
    if provider == "windows":
        if os.name != "nt":
            raise IntakeError("Windows OCR requires Windows; use installed tesseract on other systems")
        # Windows PowerShell 5.1 supplies WinRT projection; pwsh 7 does not.
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        env = os.environ.copy()
        env["KNOWLEDGE_INTAKE_OCR_FILE"] = str(path.resolve())
        env["KNOWLEDGE_INTAKE_OCR_LANGUAGE"] = str(config.get("language", ""))
        encoded = base64.b64encode(_WINDOWS_SCRIPT.encode("utf-16le")).decode("ascii")
        _, raw = command([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=timeout, max_bytes=output_chars * 4 + 4096, env=env)
        result = json.loads(raw.decode("utf-8-sig"))
    elif provider == "tesseract":
        executable = shutil.which(str(config.get("executable", "tesseract")))
        if not executable:
            raise IntakeError("tesseract is not installed; no installation or model download was attempted")
        args = [executable, str(path.resolve()), "stdout"]
        if config.get("language"):
            args += ["-l", str(config["language"])]
        _, raw = command(args, timeout=timeout, max_bytes=output_chars * 4 + 4096)
        result = {"text": raw.decode("utf-8"), "provider": "tesseract", "language": config.get("language")}
    else:
        raise ValueError("OCR provider must be windows or tesseract")
    if len(result["text"]) > output_chars:
        raise IntakeError("OCR output exceeds character budget")
    return result
