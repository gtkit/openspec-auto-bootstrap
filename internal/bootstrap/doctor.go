package bootstrap

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

func Doctor(repoPath string, stdout, stderr io.Writer) error {
	if repoPath == "" {
		executablePath, err := os.Executable()
		if err != nil {
			executablePath = "openspec-auto"
		}
		fmt.Fprintf(stdout, "OpenSpec Auto binary looks present:\n  %s\n\n", executablePath)
		fmt.Fprintln(stdout, "Pass a repo path to run the full healthcheck:")
		fmt.Fprintln(stdout, "  openspec-auto doctor /absolute/path/to/repo")
		return nil
	}

	repoDir, err := absoluteDirectory(repoPath)
	if err != nil {
		return err
	}

	fmt.Fprintf(stdout, "[openspec-auto] Running healthcheck for %s\n", repoDir)
	return runCommand(
		context.Background(),
		stdout,
		stderr,
		repoDir,
		nil,
		filepath.Join(repoDir, "tools", "openspec", "healthcheck.sh"),
		repoDir,
	)
}
