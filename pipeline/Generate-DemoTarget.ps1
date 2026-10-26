#!/usr/bin/env pwsh
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#Requires -Version 7.0
<#
.SYNOPSIS
    Generate the owned demo with the existing server Pillow environment.
.PARAMETER OutputDirectory
    Destination for demo-target.png.
.PARAMETER ArcoreImgPath
    Optional official arcoreimg executable; reject references scoring below 75.
.EXAMPLE
    .\Generate-DemoTarget.ps1 -ArcoreImgPath '..\.tools\arcore-validation-1.48.0\arcoreimg.exe'
#>
[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\assets'),
    [string]$ArcoreImgPath = ''
)
$ErrorActionPreference = 'Stop'
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$destination = Join-Path $OutputDirectory 'demo-target.png'
& uv run --project (Join-Path $PSScriptRoot '..\server') --no-sync python `
    (Join-Path $PSScriptRoot 'generate_reference_texture.py') `
    --panel-map (Join-Path $PSScriptRoot '..\assets\panel_map.json') --output $destination
if ($LASTEXITCODE -ne 0) { throw 'Original demo reference generation failed.' }
Write-Output "Wrote original synthetic reference: $destination"
if ($ArcoreImgPath) {
    $qualityOutput = & $ArcoreImgPath eval-img "--input_image_path=$destination"
    if ($LASTEXITCODE -ne 0) { throw 'ARCore reference evaluation failed.' }
    $quality = 0
    if (-not [int]::TryParse(([string]$qualityOutput).Trim(), [ref]$quality) -or $quality -lt 75) {
        throw "ARCore reference quality must be at least 75; measured: $qualityOutput"
    }
    Write-Output "ARCore reference quality: $quality/100 (minimum 75)"
}
