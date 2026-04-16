package bootstrap

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"

	bootstrapassets "github.com/gtkit/openspec-auto-bootstrap"
)

type InstallOptions struct {
	Force               bool
	SkipCodexUserConfig bool
	SkipOpenSpecInit    bool
	Stdout              io.Writer
	Stderr              io.Writer
}

func Install(repoPath string, opts InstallOptions) error {
	repoDir, err := absoluteDirectory(repoPath)
	if err != nil {
		return err
	}

	log := logger{stdout: opts.Stdout, stderr: opts.Stderr}
	backupDir := filepath.Join(repoDir, ".openspec-auto-backup", backupTimestamp())
	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		return err
	}

	if err := requireCommand("python3"); err != nil {
		return err
	}
	nodeBin, err := resolveNodeBin()
	if err != nil {
		return err
	}
	openSpecRunner, err := resolveOpenSpecRunner(nodeBin)
	if err != nil {
		return err
	}

	if _, err := os.Stat(filepath.Join(repoDir, ".git")); err != nil {
		log.warn("Target is not a git repository. The bootstrap still works, but production use is expected inside git.")
	}

	if _, err := os.Stat(filepath.Join(repoDir, "openspec")); os.IsNotExist(err) && !opts.SkipOpenSpecInit {
		log.log("Initializing OpenSpec structure in %s", repoDir)
		args := append(append([]string{}, openSpecRunner...), "init", "--tools", "none", repoDir)
		if err := runCommand(context.Background(), io.Discard, opts.Stderr, "", []string{"OPENSPEC_TELEMETRY=0"}, args...); err != nil {
			return err
		}
	}

	log.log("Installing managed text files")
	agentsBlock, err := readTemplateFile("AGENTS.md")
	if err != nil {
		return err
	}
	if err := backupPath(filepath.Join(repoDir, "AGENTS.md"), repoDir, backupDir); err != nil {
		return err
	}
	if err := upsertManagedBlock(filepath.Join(repoDir, "AGENTS.md"), agentsBlock); err != nil {
		return err
	}

	claudeBlock, err := readTemplateFile("CLAUDE.md")
	if err != nil {
		return err
	}
	if err := backupPath(filepath.Join(repoDir, "CLAUDE.md"), repoDir, backupDir); err != nil {
		return err
	}
	if err := ensureLineOnce(filepath.Join(repoDir, "CLAUDE.md"), "@AGENTS.md"); err != nil {
		return err
	}
	if err := upsertManagedBlock(filepath.Join(repoDir, "CLAUDE.md"), claudeBlock); err != nil {
		return err
	}

	log.log("Ensuring runtime directories are git-ignored")
	if err := ensureLineOnce(filepath.Join(repoDir, ".gitignore"), ".openspec-auto/"); err != nil {
		return err
	}
	if err := ensureLineOnce(filepath.Join(repoDir, ".gitignore"), ".openspec-auto-backup/"); err != nil {
		return err
	}

	log.log("Installing repo-local hook configs and skills")
	for _, relPath := range copiedTemplateFiles {
		if err := copyTemplateFile(repoDir, backupDir, relPath, opts.Force); err != nil {
			return err
		}
	}

	claudeSettings, err := readTemplateFile(".claude/settings.json")
	if err != nil {
		return err
	}
	if err := mergeJSON(filepath.Join(repoDir, ".claude", "settings.json"), claudeSettings); err != nil {
		return err
	}

	codexHooks, err := readTemplateFile(".codex/hooks.json")
	if err != nil {
		return err
	}
	if err := mergeJSON(filepath.Join(repoDir, ".codex", "hooks.json"), codexHooks); err != nil {
		return err
	}

	if err := makeExecutable(repoDir); err != nil {
		return err
	}

	homeDir, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	configPath := filepath.Join(homeDir, ".codex", "config.toml")
	if !opts.SkipCodexUserConfig {
		log.log("Ensuring ~/.codex/config.toml enables repo-local hooks")
		if err := patchCodexUserConfig(configPath, homeDir, backupDir); err != nil {
			log.warn("Failed to patch ~/.codex/config.toml automatically. Configure codex_hooks manually if needed.")
		}
	} else {
		log.warn("Skipped ~/.codex/config.toml patch. You must enable codex_hooks manually.")
	}

	log.log("Writing bootstrap version")
	versionPath := filepath.Join(repoDir, ".openspec-auto", "version")
	if err := writeTextFile(versionPath, bootstrapassets.Version()+"\n", 0o644); err != nil {
		return err
	}

	log.log("Running repo healthcheck")
	if err := runCommand(
		context.Background(),
		opts.Stdout,
		opts.Stderr,
		repoDir,
		nil,
		filepath.Join(repoDir, "tools", "openspec", "healthcheck.sh"),
		repoDir,
	); err != nil {
		return err
	}

	fmt.Fprintf(opts.Stdout, "\nInstall complete.\n\nRepo:   %s\nBackup: %s\n\nNext:\n", repoDir, backupDir)
	fmt.Fprintln(opts.Stdout, "  1. Open Claude Code or Codex in the repo root.")
	fmt.Fprintln(opts.Stdout, "  2. Ask for a behavior-changing task normally, for example:")
	fmt.Fprintln(opts.Stdout, "     - 实现订单超时自动取消")
	fmt.Fprintln(opts.Stdout, "     - 修复支付回调重复入库")
	fmt.Fprintln(opts.Stdout, "     - 把会员试用逻辑改成 7 天")
	fmt.Fprintln(opts.Stdout, "  3. The repository will route the request through OpenSpec automatically.")
	return nil
}
