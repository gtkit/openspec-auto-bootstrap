# OpenSpec Auto CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `openspec-auto` Go binary that replaces the current shell entrypoints, removes leaked local paths from docs, and ships a clean new release.

**Architecture:** Add a small Go CLI entrypoint and a focused bootstrap package that embeds template assets and ports the shell behaviors into testable Go helpers. Keep the current Python integration-test harness, then add a repository scan to prevent future absolute-path leaks and verify the new command shape end to end.

**Tech Stack:** Go 1.26, standard library `embed`, Python `unittest`, existing shell healthcheck scripts inside installed target repos.

---

### Task 1: Lock the public CLI behavior with failing tests

**Files:**
- Modify: `tests/test_install_script.py`
- Create: `tests/test_cli_safety.py`

- [ ] **Step 1: Write failing CLI integration assertions**

```python
result = subprocess.run(
    ["go", "run", "./cmd/openspec-auto", "install", "--skip-codex-user-config", str(repo)],
    text=True,
    capture_output=True,
    check=False,
    cwd=ROOT,
    env=env,
)
self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python3 -m unittest tests.test_install_script tests.test_cli_safety -v`
Expected: FAIL because `cmd/openspec-auto` does not exist yet.

- [ ] **Step 3: Add a repository leak scan test**

```python
for path in ROOT.rglob("*"):
    if ".git" in path.parts or path.is_dir():
        continue
    self.assertIsNone(re.search(r"/Users/[^/\\s]+", path.read_text()))
```

- [ ] **Step 4: Re-run to keep the suite red for the right reason**

Run: `python3 -m unittest tests.test_install_script tests.test_cli_safety -v`
Expected: FAIL on missing CLI and current leaked README paths.

### Task 2: Add the standalone Go CLI skeleton

**Files:**
- Create: `go.mod`
- Create: `cmd/openspec-auto/main.go`
- Create: `internal/cli/app.go`
- Create: `internal/bootstrap/assets.go`

- [ ] **Step 1: Add a minimal Go module**

```go
module github.com/gtkit/openspec-auto-bootstrap

go 1.26
```

- [ ] **Step 2: Parse subcommands and route to typed handlers**

```go
switch os.Args[1] {
case "install":
    return cli.RunInstall(...)
case "uninstall":
    return cli.RunUninstall(...)
case "doctor":
    return cli.RunDoctor(...)
case "version":
    return cli.RunVersion(...)
}
```

- [ ] **Step 3: Embed `templates/repo/**` and `VERSION`**

```go
//go:embed ../../templates/repo/**
var templateFS embed.FS
```

- [ ] **Step 4: Run tests again to move from “missing CLI” to behavior failures**

Run: `python3 -m unittest tests.test_install_script tests.test_cli_safety -v`
Expected: FAIL on unimplemented install behavior, not on missing files.

### Task 3: Port install/uninstall/doctor behavior into Go

**Files:**
- Create: `internal/bootstrap/install.go`
- Create: `internal/bootstrap/uninstall.go`
- Create: `internal/bootstrap/doctor.go`
- Create: `internal/bootstrap/textpatch.go`
- Create: `internal/bootstrap/jsonmerge.go`

- [ ] **Step 1: Port text mutation helpers first**

```go
func UpsertManagedBlock(...)
func EnsureLineOnce(...)
func RemoveManagedBlock(...)
```

- [ ] **Step 2: Port filesystem copy, backup, chmod, and embedded asset extraction**

```go
func (i *Installer) copyTemplateFile(ctx context.Context, rel string) error
```

- [ ] **Step 3: Port external command resolution for `node`, `openspec`, and healthcheck**

```go
func ResolveOpenSpecRunner(...) ([]string, error)
```

- [ ] **Step 4: Implement install/uninstall/doctor with parity to shell behavior**

Run: `python3 -m unittest tests.test_install_script -v`
Expected: PASS for install/uninstall flows.

### Task 4: Clean docs and add release-facing guidance

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace all absolute-path command examples with command-name examples**

```text
openspec-auto install /absolute/path/to/your-repo
openspec-auto doctor
openspec-auto uninstall /absolute/path/to/repo
```

- [ ] **Step 2: Add binary build/install instructions**

Run: `go build -o ./bin/openspec-auto ./cmd/openspec-auto`
Expected: a standalone binary at `./bin/openspec-auto`

- [ ] **Step 3: Re-run the leak scan**

Run: `python3 -m unittest tests.test_cli_safety -v`
Expected: PASS

### Task 5: Verify, build, install, and release cleanup

**Files:**
- Modify: `VERSION`

- [ ] **Step 1: Bump the clean release version**

```text
1.2.0
```

- [ ] **Step 2: Run the full local verification**

Run: `python3 -m unittest -v`
Expected: PASS

Run: `go test ./...`
Expected: PASS

Run: `go build -o ./bin/openspec-auto ./cmd/openspec-auto`
Expected: PASS

- [ ] **Step 3: Install the binary to the requested global locations**

Run: `cp ./bin/openspec-auto /usr/local/bin/openspec-auto`
Run: `cp ./bin/openspec-auto "$HOME/go/bin/openspec-auto"`

- [ ] **Step 4: Delete dirty tags and releases, then publish the clean version**

Run: `git tag -d v1.0.0 v1.1.0 v1.1.1`
Run: `git push gtkit :refs/tags/v1.0.0 :refs/tags/v1.1.0 :refs/tags/v1.1.1`
Run: `gh release delete v1.0.0 --yes`
Run: `gh release delete v1.1.0 --yes`
Run: `gh release delete v1.1.1 --yes`
Run: `git tag -a v1.2.0 -m "v1.2.0"`
Run: `git push gtkit v1.2.0`
