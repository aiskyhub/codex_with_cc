# macOS Scripts

macOS support is not implemented yet.

When installing this workflow on macOS, the installing AI should use the behavior in `../windows_scripts` as the reference and implement equivalent native macOS scripts in this directory.

Do not copy Windows PowerShell commands directly into macOS instructions. Preserve the same workflow boundaries: the Codex main thread plans and reviews, a Codex child thread invokes the delegate entrypoint, and the delegate entrypoint calls Claude Code CLI.
