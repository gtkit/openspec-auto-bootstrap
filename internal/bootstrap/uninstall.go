package bootstrap

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
)

var uninstallTargets = []string{
	".claude/hooks/openspec_context.py",
	".claude/hooks/openspec_router.py",
	".claude/hooks/openspec_guard.py",
	".claude/hooks/openspec_stop.py",
	".claude/skills/openspec-auto",
	".agents/skills/openspec-auto",
	".codex/hooks/openspec_context.py",
	".codex/hooks/openspec_router.py",
	".codex/hooks/openspec_guard.py",
	".codex/hooks/openspec_stop.py",
	".codex/prompts/openspec-auto.md",
	".codex/config.toml.append",
	"tools/openspec/env.sh",
	"tools/openspec/healthcheck.sh",
	"tools/openspec/hook_common.py",
	"tools/openspec/classify_request.py",
	"tools/openspec/resolve_change.py",
	"tools/openspec/validate_repo.py",
	"tools/openspec/sync_templates.sh",
	"tools/openspec/__pycache__",
	".openspec-auto",
}

func Uninstall(repoPath string, stdout, stderr io.Writer) error {
	repoDir, err := absoluteDirectory(repoPath)
	if err != nil {
		return err
	}

	if err := removeManagedBlock(filepath.Join(repoDir, "AGENTS.md")); err != nil {
		return err
	}
	if err := removeManagedBlock(filepath.Join(repoDir, "CLAUDE.md")); err != nil {
		return err
	}

	for _, relPath := range uninstallTargets {
		if err := removePath(filepath.Join(repoDir, filepath.FromSlash(relPath))); err != nil {
			return err
		}
	}

	if err := cleanupHookConfig(filepath.Join(repoDir, ".claude", "settings.json")); err != nil {
		return err
	}
	if err := cleanupHookConfig(filepath.Join(repoDir, ".codex", "hooks.json")); err != nil {
		return err
	}

	homeDir, err := os.UserHomeDir()
	if err == nil {
		configPath := filepath.Join(homeDir, ".codex", "config.toml")
		if err := cleanCodexUserConfig(configPath); err != nil {
			fmt.Fprintln(stderr, "[openspec-auto][warn] Failed to clean ~/.codex/config.toml automatically. Remove openspec-auto markers manually if needed.")
		}
	}

	cleanupEmptyDirectories(repoDir)

	fmt.Fprintf(stdout, "Uninstall complete for:\n  %s\n\nOpenSpec artifacts under %s/openspec were left intact.\n", repoDir, repoDir)
	return nil
}
