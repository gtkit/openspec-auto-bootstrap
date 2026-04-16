package cli

import (
	"flag"
	"fmt"
	"io"

	bootstrapassets "github.com/gtkit/openspec-auto-bootstrap"
	"github.com/gtkit/openspec-auto-bootstrap/internal/bootstrap"
)

func Run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		printUsage(stdout)
		return 0
	}

	switch args[0] {
	case "install":
		return runInstall(args[1:], stdout, stderr)
	case "uninstall":
		return runUninstall(args[1:], stdout, stderr)
	case "doctor":
		return runDoctor(args[1:], stdout, stderr)
	case "version":
		fmt.Fprintln(stdout, bootstrapassets.Version())
		return 0
	case "-h", "--help", "help":
		printUsage(stdout)
		return 0
	default:
		fmt.Fprintf(stderr, "unknown subcommand: %s\n\n", args[0])
		printUsage(stderr)
		return 1
	}
}

func printUsage(w io.Writer) {
	fmt.Fprintln(w, "Usage:")
	fmt.Fprintln(w, "  openspec-auto install [options] /absolute/path/to/repo")
	fmt.Fprintln(w, "  openspec-auto uninstall /absolute/path/to/repo")
	fmt.Fprintln(w, "  openspec-auto doctor [/absolute/path/to/repo]")
	fmt.Fprintln(w, "  openspec-auto version")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Install options:")
	fmt.Fprintln(w, "  --force")
	fmt.Fprintln(w, "  --skip-codex-user-config")
	fmt.Fprintln(w, "  --skip-openspec-init")
}

func runInstall(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("install", flag.ContinueOnError)
	flags.SetOutput(stderr)

	var opts bootstrap.InstallOptions
	opts.Stdout = stdout
	opts.Stderr = stderr

	flags.BoolVar(&opts.Force, "force", false, "overwrite managed files after backing them up")
	flags.BoolVar(&opts.SkipCodexUserConfig, "skip-codex-user-config", false, "do not modify ~/.codex/config.toml")
	flags.BoolVar(&opts.SkipOpenSpecInit, "skip-openspec-init", false, `do not run "openspec init --tools none"`)
	flags.Usage = func() {
		fmt.Fprintln(stderr, "Usage:")
		fmt.Fprintln(stderr, "  openspec-auto install [options] /absolute/path/to/repo")
		flags.PrintDefaults()
	}

	if err := flags.Parse(args); err != nil {
		return 1
	}
	if flags.NArg() != 1 {
		flags.Usage()
		return 1
	}
	if err := bootstrap.Install(flags.Arg(0), opts); err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

func runUninstall(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("uninstall", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.Usage = func() {
		fmt.Fprintln(stderr, "Usage:")
		fmt.Fprintln(stderr, "  openspec-auto uninstall /absolute/path/to/repo")
	}
	if err := flags.Parse(args); err != nil {
		return 1
	}
	if flags.NArg() != 1 {
		flags.Usage()
		return 1
	}
	if err := bootstrap.Uninstall(flags.Arg(0), stdout, stderr); err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

func runDoctor(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("doctor", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.Usage = func() {
		fmt.Fprintln(stderr, "Usage:")
		fmt.Fprintln(stderr, "  openspec-auto doctor [/absolute/path/to/repo]")
	}
	if err := flags.Parse(args); err != nil {
		return 1
	}
	if flags.NArg() > 1 {
		flags.Usage()
		return 1
	}

	repoPath := ""
	if flags.NArg() == 1 {
		repoPath = flags.Arg(0)
	}
	if err := bootstrap.Doctor(repoPath, stdout, stderr); err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}
