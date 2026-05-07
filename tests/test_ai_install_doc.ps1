$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repoRoot 'codex_with_cc\windows_scripts\test_helpers.ps1')

$aiInstallPath = Join-Path $repoRoot 'AI_INSTALL.md'
$projectStructurePath = Join-Path $repoRoot 'PROJECT_STRUCTURE.md'
$workflowContractPath = Join-Path $repoRoot 'codex_with_cc\CODEX_WITH_CC.md'

Assert-True -Condition (Test-Path -LiteralPath $aiInstallPath) -Name 'ai-install-doc-exists'
Assert-True -Condition (Test-Path -LiteralPath $projectStructurePath) -Name 'project-structure-doc-exists'
Assert-True -Condition (Test-Path -LiteralPath $workflowContractPath) -Name 'workflow-contract-doc-exists'

$aiInstallText = Get-Content -LiteralPath $aiInstallPath -Raw
$projectStructureText = Get-Content -LiteralPath $projectStructurePath -Raw
$workflowContractText = Get-Content -LiteralPath $workflowContractPath -Raw

Assert-Contains -Text $aiInstallText -Needle '默认按上游仓库原样接入，不要擅自混入目标项目专属示例、业务规则、验证命令或定制说明。' -Name 'ai-install-doc-keeps-upstream-workflow-verbatim-by-default'
Assert-Contains -Text $aiInstallText -Needle '只有用户明确要求你“顺手定制”或“改成项目特化版本”时，才允许额外改工作流文档。' -Name 'ai-install-doc-allows-customization-only-on-explicit-request'
Assert-Contains -Text $aiInstallText -Needle '工作流文件放在 `codex_with_cc/...`' -Name 'ai-install-doc-documents-source-repo-path-context'
Assert-Contains -Text $aiInstallText -Needle '工作流文件放在 `docs/codex_with_cc/...`' -Name 'ai-install-doc-documents-target-project-path-context'
Assert-Contains -Text $aiInstallText -Needle 'Windows 安装入口是 `scripts/install_codex_with_cc.ps1`' -Name 'ai-install-doc-documents-windows-installer-script-location'
Assert-Contains -Text $aiInstallText -Needle 'Linux/macOS 安装入口是 `scripts/install_codex_with_cc.sh`' -Name 'ai-install-doc-documents-posix-installer-script-location'
Assert-Contains -Text $aiInstallText -Needle '都必须强制走本仓库定义的自定义委派链路：`Codex 主线程 -> Codex 子代理 -> docs/codex_with_cc/<windows_scripts|unix_scripts>/delegate_to_claude.* -> Claude Code CLI`。' -Name 'ai-install-doc-forces-custom-delegate-chain'
Assert-Contains -Text $aiInstallText -Needle 'macOS 和 Linux 直接使用源仓库里的 `codex_with_cc/unix_scripts`。' -Name 'ai-install-doc-documents-unix-scripts-for-posix-platforms'
Assert-Contains -Text $aiInstallText -Needle 'Windows 目标项目不要安装 `unix_scripts`；Linux/macOS 目标项目不要安装 `windows_scripts`。' -Name 'ai-install-doc-documents-platform-script-filtering'
Assert-Contains -Text $aiInstallText -Needle '## Linux/macOS 安装' -Name 'ai-install-doc-has-combined-linux-macos-install-section'
Assert-Contains -Text $aiInstallText -Needle 'bash ./scripts/install_codex_with_cc.sh --target-root <target-project>' -Name 'ai-install-doc-documents-posix-installer-command'
Assert-Contains -Text $aiInstallText -Needle 'Linux/macOS 模板中的子代理标准调用形态：' -Name 'ai-install-doc-documents-posix-delegate-command-section'
Assert-Contains -Text $aiInstallText -Needle 'bash ./docs/codex_with_cc/unix_scripts/delegate_to_claude.sh \' -Name 'ai-install-doc-documents-posix-delegate-command'
Assert-Contains -Text $aiInstallText -Needle '--session-mode PrimaryReuse \' -Name 'ai-install-doc-documents-posix-primary-reuse-mode'
Assert-Contains -Text $aiInstallText -Needle '--allow-parallel' -Name 'ai-install-doc-documents-posix-parallel-flag'
Assert-Contains -Text $aiInstallText -Needle '不要把 Codex 自带的默认子代理工作流、宿主环境内置代理流程，或者“直接让当前 AI 自己继续开子代理干活”当作这套链路的等价替代。' -Name 'ai-install-doc-forbids-native-subagent-fallback'
Assert-Contains -Text $aiInstallText -Needle '只要任务需要进入子代理执行层，就必须使用本工作流提供的自定义委派链路，不要退回 Codex 默认子代理工作流充当执行层。' -Name 'ai-install-doc-makes-custom-chain-a-hard-rule'
Assert-Contains -Text $aiInstallText -Needle '.codex/codex_with_cc/tasks' -Name 'ai-install-doc-moves-task-files-under-codex'
Assert-Contains -Text $aiInstallText -Needle '.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-file>.md' -Name 'ai-install-doc-uses-dated-unique-task-file'
Assert-Contains -Text $aiInstallText -Needle '.gitignore` 包含 `.codex/codex_with_cc`' -Name 'ai-install-doc-ensures-targeted-codex-with-cc-is-ignored'
Assert-Contains -Text $aiInstallText -Needle 'Linux/macOS 模板里，检查单次委派产物：' -Name 'ai-install-doc-documents-posix-artifact-verification-section'
Assert-Contains -Text $aiInstallText -Needle 'bash ./docs/codex_with_cc/unix_scripts/verify_delegate_artifacts.sh' -Name 'ai-install-doc-documents-posix-artifact-verifier-command'
Assert-Contains -Text $aiInstallText -Needle 'Linux/macOS 模板里，检查多轮链路连续性：' -Name 'ai-install-doc-documents-posix-chain-verification-section'
Assert-Contains -Text $aiInstallText -Needle 'bash ./docs/codex_with_cc/unix_scripts/verify_delegate_chain.sh' -Name 'ai-install-doc-documents-posix-chain-verifier-command'
Assert-Contains -Text $workflowContractText -Needle 'Delegation artifacts are written under `.codex/codex_with_cc/claude-delegate` by default' -Name 'workflow-contract-keeps-artifacts-under-codex-with-cc'
Assert-Contains -Text $aiInstallText -Needle '安装器不支持把源仓库自身作为 `-TargetRoot`；请使用外部目标项目目录，避免安装时移除源工作流目录。' -Name 'ai-install-doc-forbids-self-target-install'
Assert-Contains -Text $aiInstallText -Needle '不要追问“要保留上游原样接入，还是顺手按当前项目定制”这类范围选择题。' -Name 'ai-install-doc-forbids-unnecessary-scope-questions'
Assert-Contains -Text $aiInstallText -Needle '如果 Codex 沙箱或代跑环境无法执行同一委派命令，Codex 应改由受信任本机终端运行同一命令' -Name 'ai-install-doc-documents-trusted-terminal-fallback'
Assert-Contains -Text $workflowContractText -Needle 'If the Codex sandbox or delegated runner cannot execute the same worker command, run that exact command in a trusted local terminal instead.' -Name 'workflow-contract-documents-trusted-terminal-fallback'
Assert-Contains -Text $workflowContractText -Needle 'This file is written as a portable workflow contract' -Name 'workflow-contract-documents-portable-path-context'
Assert-Contains -Text $workflowContractText -Needle 'Use source-repo paths when changing this repository. Use target-project paths when writing delegate commands, verification commands, or `AGENTS.md` guidance for an installed project.' -Name 'workflow-contract-explains-when-to-use-source-vs-target-paths'
Assert-Contains -Text $projectStructureText -Needle '当前仓库是**源仓库**，工作流文件放在 `codex_with_cc/...`' -Name 'project-structure-documents-source-repo-path-root'
Assert-Contains -Text $projectStructureText -Needle '安装到别的项目后是**目标项目**，工作流文件放在 `docs/codex_with_cc/...`' -Name 'project-structure-documents-target-project-path-root'
Assert-Contains -Text $projectStructureText -Needle 'scripts/' -Name 'project-structure-lists-scripts-directory'
Assert-Contains -Text $projectStructureText -Needle 'Windows 安装脚本在 `scripts/install_codex_with_cc.ps1`' -Name 'project-structure-documents-windows-installer-script-location'
Assert-Contains -Text $projectStructureText -Needle 'Linux/macOS 安装脚本在 `scripts/install_codex_with_cc.sh`' -Name 'project-structure-documents-posix-installer-script-location'
Assert-Contains -Text $projectStructureText -Needle '| `codex_with_cc/unix_scripts/delegate_to_claude.sh` | `docs/codex_with_cc/unix_scripts/delegate_to_claude.sh` |' -Name 'project-structure-includes-unix-script-path-mapping'
Assert-Contains -Text $workflowContractText -Needle 'Normally run this inside a Codex child thread.' -Name 'workflow-contract-standard-command-allows-documented-fallback'
Assert-Contains -Text $aiInstallText -Needle 'Claude Code worker 必须读取并遵守目标项目 `.codex` 下约定的 skills、技能文档和工作流要求。' -Name 'ai-install-doc-requires-worker-codex-project-skills'
Assert-Contains -Text $workflowContractText -Needle 'Claude workers must read and follow all applicable Codex project skills under `.codex` before implementing or changing behavior.' -Name 'workflow-contract-requires-worker-codex-project-skills'

Write-Host 'AI install doc tests passed' -ForegroundColor Green
