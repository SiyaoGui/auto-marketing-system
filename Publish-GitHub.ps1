$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Run-Git { & git @args; if ($LASTEXITCODE -ne 0) { throw 'Git command failed' } }
Get-Command gh,git -ErrorAction Stop | Out-Null
$login = gh api user --jq .login
if ($LASTEXITCODE -ne 0 -or $login -ne 'SiyaoGui') { throw 'Run gh auth login as SiyaoGui first.' }
if (Test-Path -LiteralPath .git) { throw 'Use a fresh extraction of the handover archive.' }
Run-Git init -b main
Run-Git add -- README.zh-CN.md HANDOFF.md Publish-GitHub.ps1 .gitignore requirements.txt run.cmd start.cmd brands config data docs engine examples scripts templates tests
Run-Git -c user.name=SiyaoGui -c user.email=74054739+SiyaoGui@users.noreply.github.com commit -m 'Hand over local marketing engine v0.1'
gh repo create SiyaoGui/local-marketing-engine --private --source . --remote origin --push
if ($LASTEXITCODE -ne 0) { throw 'Repository creation or push failed. Check GitHub before retrying.' }
gh repo view --json url --jq .url
