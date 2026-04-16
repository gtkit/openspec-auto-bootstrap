package bootstrap

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"

	bootstrapassets "github.com/gtkit/openspec-auto-bootstrap"
)

const managedBlockStart = "<!-- OPENSPEC-AUTO:START -->"
const managedBlockEnd = "<!-- OPENSPEC-AUTO:END -->"

var executableFiles = []string{
	".claude/hooks/openspec_context.py",
	".claude/hooks/openspec_router.py",
	".claude/hooks/openspec_guard.py",
	".claude/hooks/openspec_stop.py",
	".codex/hooks/openspec_context.py",
	".codex/hooks/openspec_router.py",
	".codex/hooks/openspec_guard.py",
	".codex/hooks/openspec_stop.py",
	"tools/openspec/env.sh",
	"tools/openspec/healthcheck.sh",
	"tools/openspec/sync_templates.sh",
}

var copiedTemplateFiles = []string{
	".claude/hooks/openspec_context.py",
	".claude/hooks/openspec_router.py",
	".claude/hooks/openspec_guard.py",
	".claude/hooks/openspec_stop.py",
	".claude/skills/openspec-auto/SKILL.md",
	".agents/skills/openspec-auto/SKILL.md",
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
}

type logger struct {
	stdout io.Writer
	stderr io.Writer
}

func (l logger) log(format string, args ...any) {
	fmt.Fprintf(l.stdout, "[openspec-auto] %s\n", fmt.Sprintf(format, args...))
}

func (l logger) warn(format string, args ...any) {
	fmt.Fprintf(l.stderr, "[openspec-auto][warn] %s\n", fmt.Sprintf(format, args...))
}

func requireCommand(name string) error {
	if _, err := exec.LookPath(name); err != nil {
		return fmt.Errorf("missing required command: %s", name)
	}
	return nil
}

type semVersion struct {
	major int
	minor int
	patch int
}

func parseVersion(raw string) (semVersion, error) {
	parts := strings.Split(strings.TrimSpace(raw), ".")
	values := [3]int{}
	for i := range 3 {
		if i >= len(parts) {
			break
		}
		segment := parts[i]
		if dash := strings.Index(segment, "-"); dash >= 0 {
			segment = segment[:dash]
		}
		if segment == "" {
			return semVersion{}, fmt.Errorf("invalid version: %q", raw)
		}
		value, err := strconv.Atoi(segment)
		if err != nil {
			return semVersion{}, fmt.Errorf("invalid version: %q", raw)
		}
		values[i] = value
	}
	return semVersion{major: values[0], minor: values[1], patch: values[2]}, nil
}

func (v semVersion) compare(other semVersion) int {
	switch {
	case v.major != other.major:
		return cmpInt(v.major, other.major)
	case v.minor != other.minor:
		return cmpInt(v.minor, other.minor)
	default:
		return cmpInt(v.patch, other.patch)
	}
}

func cmpInt(left, right int) int {
	switch {
	case left < right:
		return -1
	case left > right:
		return 1
	default:
		return 0
	}
}

func resolveNodeBin() (string, error) {
	required := semVersion{major: 20, minor: 19, patch: 0}
	candidates := []string{}

	if envNode := os.Getenv("NODE_BIN"); envNode != "" {
		candidates = append(candidates, envNode)
	}
	if pathNode, err := exec.LookPath("node"); err == nil {
		candidates = append(candidates, pathNode)
	}
	if home, err := os.UserHomeDir(); err == nil {
		globbed, _ := filepath.Glob(filepath.Join(home, ".nvm", "versions", "node", "*", "bin", "node"))
		candidates = append(candidates, globbed...)
	}

	seen := map[string]struct{}{}
	bestPath := ""
	bestVersion := semVersion{}
	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		if _, ok := seen[candidate]; ok {
			continue
		}
		seen[candidate] = struct{}{}

		versionText, err := commandOutput(candidate, "-p", "process.versions.node")
		if err != nil {
			continue
		}
		version, err := parseVersion(versionText)
		if err != nil || version.compare(required) < 0 {
			continue
		}
		if bestPath == "" || version.compare(bestVersion) > 0 {
			bestPath = candidate
			bestVersion = version
		}
	}

	if bestPath == "" {
		return "", errors.New("Node.js must be >= 20.19.0")
	}
	return bestPath, nil
}

func resolveOpenSpecRunner(nodeBin string) ([]string, error) {
	openspecPath, err := exec.LookPath("openspec")
	if err != nil {
		return nil, errors.New("missing required command: openspec")
	}
	if err := exec.Command(openspecPath, "--version").Run(); err == nil {
		return []string{openspecPath}, nil
	}

	cmd := exec.Command(nodeBin, openspecPath, "--version")
	if err := cmd.Run(); err != nil {
		return nil, errors.New("unable to run openspec with the resolved Node.js binary")
	}
	return []string{nodeBin, openspecPath}, nil
}

func commandOutput(name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = err.Error()
		}
		return "", errors.New(message)
	}
	return strings.TrimSpace(stdout.String()), nil
}

func templateFS() (fs.FS, error) {
	return bootstrapassets.TemplateFS()
}

func readTemplateFile(relPath string) ([]byte, error) {
	assets, err := templateFS()
	if err != nil {
		return nil, err
	}
	return fs.ReadFile(assets, relPath)
}

func ensureLineOnce(destPath, line string) error {
	content, err := readIfExists(destPath)
	if err != nil {
		return err
	}
	lines := []string{}
	if strings.TrimSpace(content) != "" {
		lines = strings.Split(strings.TrimRight(content, "\n"), "\n")
	}
	if slices.Contains(lines, line) {
		return nil
	}

	var updated string
	if strings.TrimSpace(content) == "" {
		updated = line + "\n"
	} else {
		updated = line + "\n\n" + strings.TrimLeft(content, "\n")
	}
	return writeTextFile(destPath, updated, 0o644)
}

func upsertManagedBlock(destPath string, block []byte) error {
	content, err := readIfExists(destPath)
	if err != nil {
		return err
	}
	blockText := strings.TrimSpace(string(block))
	pattern := regexp.MustCompile(regexp.QuoteMeta(managedBlockStart) + `(?s:.*?)` + regexp.QuoteMeta(managedBlockEnd))

	var updated string
	switch {
	case pattern.MatchString(content):
		updated = pattern.ReplaceAllString(content, blockText)
	case strings.TrimSpace(content) != "":
		updated = strings.TrimRight(content, "\n") + "\n\n" + blockText + "\n"
	default:
		updated = blockText + "\n"
	}
	return writeTextFile(destPath, updated, 0o644)
}

func removeManagedBlock(destPath string) error {
	content, err := readIfExists(destPath)
	if err != nil {
		return err
	}
	if content == "" {
		return nil
	}
	pattern := regexp.MustCompile(`\n?` + regexp.QuoteMeta(managedBlockStart) + `(?s:.*?)` + regexp.QuoteMeta(managedBlockEnd) + `\n?`)
	updated := strings.TrimSpace(pattern.ReplaceAllString(content, "\n"))
	if updated == "" {
		return writeTextFile(destPath, "", 0o644)
	}
	return writeTextFile(destPath, updated+"\n", 0o644)
}

func mergeJSON(destPath string, incoming []byte) error {
	current := map[string]any{}
	if currentBytes, err := os.ReadFile(destPath); err == nil {
		if err := json.Unmarshal(currentBytes, &current); err != nil {
			return err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	incomingData := map[string]any{}
	if err := json.Unmarshal(incoming, &incomingData); err != nil {
		return err
	}

	currentHooks := asObjectMap(current["hooks"])
	incomingHooks := asObjectMap(incomingData["hooks"])
	for event, rawEntries := range incomingHooks {
		currentEntries := asSlice(currentHooks[event])
		seen := map[string]struct{}{}
		for _, entry := range currentEntries {
			seen[jsonSignature(entry)] = struct{}{}
		}
		for _, entry := range asSlice(rawEntries) {
			signature := jsonSignature(entry)
			if _, ok := seen[signature]; ok {
				continue
			}
			currentEntries = append(currentEntries, entry)
			seen[signature] = struct{}{}
		}
		currentHooks[event] = currentEntries
	}
	current["hooks"] = currentHooks

	for key, value := range incomingData {
		if key == "hooks" {
			continue
		}
		if _, ok := current[key]; !ok {
			current[key] = value
		}
	}

	return writeJSON(destPath, current)
}

func asObjectMap(value any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return map[string]any{}
}

func asSlice(value any) []any {
	if value == nil {
		return nil
	}
	if typed, ok := value.([]any); ok {
		return typed
	}
	return nil
}

func jsonSignature(value any) string {
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

func writeJSON(path string, data map[string]any) error {
	encoded, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return writeFile(path, append(encoded, '\n'), 0o644)
}

func writeTextFile(path, content string, mode os.FileMode) error {
	return writeFile(path, []byte(content), mode)
}

func writeFile(path string, data []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, data, mode)
}

func readIfExists(path string) (string, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func backupPath(target, base, backupDir string) error {
	info, err := os.Lstat(target)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	relative, err := filepath.Rel(base, target)
	if err != nil {
		return err
	}
	destination := filepath.Join(backupDir, relative)
	return copyPath(target, destination, info)
}

func copyPath(src, dest string, info os.FileInfo) error {
	if info.Mode()&os.ModeSymlink != 0 {
		linkTarget, err := os.Readlink(src)
		if err != nil {
			return err
		}
		if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
			return err
		}
		_ = os.Remove(dest)
		return os.Symlink(linkTarget, dest)
	}
	if info.IsDir() {
		if err := os.MkdirAll(dest, info.Mode().Perm()); err != nil {
			return err
		}
		entries, err := os.ReadDir(src)
		if err != nil {
			return err
		}
		for _, entry := range entries {
			childInfo, err := entry.Info()
			if err != nil {
				return err
			}
			if err := copyPath(filepath.Join(src, entry.Name()), filepath.Join(dest, entry.Name()), childInfo); err != nil {
				return err
			}
		}
		return nil
	}

	source, err := os.Open(src)
	if err != nil {
		return err
	}
	defer source.Close()

	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	target, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer target.Close()

	if _, err := io.Copy(target, source); err != nil {
		return err
	}
	return os.Chmod(dest, info.Mode().Perm())
}

func copyTemplateFile(repoDir, backupDir, relPath string, force bool) error {
	srcData, err := readTemplateFile(relPath)
	if err != nil {
		return err
	}
	destPath := filepath.Join(repoDir, filepath.FromSlash(relPath))
	if existing, err := os.ReadFile(destPath); err == nil {
		if bytes.Equal(srcData, existing) {
			return nil
		}
		if !force {
			return fmt.Errorf("managed file differs from the template: %s. Re-run with --force to overwrite it", destPath)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	if err := backupPath(destPath, repoDir, backupDir); err != nil {
		return err
	}
	return writeFile(destPath, srcData, 0o644)
}

func patchCodexUserConfig(configPath, homeDir, backupDir string) error {
	if _, err := os.Stat(configPath); err == nil {
		if err := backupPath(configPath, homeDir, backupDir); err != nil {
			return err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	text, err := readIfExists(configPath)
	if err != nil {
		return err
	}

	markerLine := "codex_hooks = true # openspec-auto"
	commentLine := "# OPENSPEC-AUTO: enable repo-local Codex hooks"

	if strings.Contains(text, markerLine) {
		return nil
	}
	if regexp.MustCompile(`(?m)^\s*codex_hooks\s*=\s*true\b`).MatchString(text) {
		return nil
	}

	featuresPattern := regexp.MustCompile(`(?m)^\[features\]\s*$`)
	if location := featuresPattern.FindStringIndex(text); location != nil {
		replacement := "[features]\n" + commentLine + "\n" + markerLine
		text = text[:location[0]] + replacement + text[location[1]:]
	} else {
		addition := "# OPENSPEC-AUTO:START\n[features]\n" + commentLine + "\n" + markerLine + "\n# OPENSPEC-AUTO:END\n"
		if strings.TrimSpace(text) != "" {
			text = strings.TrimRight(text, "\n") + "\n" + addition
		} else {
			text = addition
		}
	}

	return writeTextFile(configPath, ensureTrailingNewline(text), 0o644)
}

func cleanCodexUserConfig(configPath string) error {
	text, err := readIfExists(configPath)
	if err != nil || text == "" {
		return err
	}
	text = regexp.MustCompile(`\n?# OPENSPEC-AUTO:START(?s:.*?)# OPENSPEC-AUTO:END\n?`).ReplaceAllString(text, "\n")
	text = regexp.MustCompile(`(?m)^\s*# OPENSPEC-AUTO: enable repo-local Codex hooks\s*$\n?`).ReplaceAllString(text, "")
	text = regexp.MustCompile(`(?m)^\s*codex_hooks\s*=\s*true\s*# openspec-auto\s*$\n?`).ReplaceAllString(text, "")
	text = strings.TrimSpace(text)
	if text == "" {
		return writeTextFile(configPath, "", 0o644)
	}
	return writeTextFile(configPath, text+"\n", 0o644)
}

func ensureTrailingNewline(text string) string {
	if strings.HasSuffix(text, "\n") {
		return text
	}
	return text + "\n"
}

func runCommand(ctx context.Context, stdout, stderr io.Writer, dir string, env []string, args ...string) error {
	if len(args) == 0 {
		return errors.New("missing command")
	}
	cmd := exec.CommandContext(ctx, args[0], args[1:]...)
	cmd.Dir = dir
	cmd.Stdout = stdout
	cmd.Stderr = stderr
	if len(env) > 0 {
		cmd.Env = append(os.Environ(), env...)
	}
	return cmd.Run()
}

func removePath(path string) error {
	if err := os.RemoveAll(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}

func makeExecutable(repoDir string) error {
	for _, relPath := range executableFiles {
		fullPath := filepath.Join(repoDir, filepath.FromSlash(relPath))
		if err := os.Chmod(fullPath, 0o755); err != nil {
			return err
		}
	}
	return nil
}

func cleanupHookConfig(path string) error {
	content, err := readIfExists(path)
	if err != nil || content == "" {
		return err
	}

	data := map[string]any{}
	if err := json.Unmarshal([]byte(content), &data); err != nil {
		return err
	}
	hooks := asObjectMap(data["hooks"])
	for event, rawEntries := range hooks {
		filteredEntries := []any{}
		for _, rawEntry := range asSlice(rawEntries) {
			entry, ok := rawEntry.(map[string]any)
			if !ok {
				continue
			}
			commands := []any{}
			for _, rawHook := range asSlice(entry["hooks"]) {
				hook, ok := rawHook.(map[string]any)
				if !ok {
					continue
				}
				command, _ := hook["command"].(string)
				if !strings.Contains(command, "openspec_") {
					commands = append(commands, hook)
				}
			}
			if len(commands) > 0 {
				entry["hooks"] = commands
				filteredEntries = append(filteredEntries, entry)
			}
		}
		if len(filteredEntries) == 0 {
			delete(hooks, event)
			continue
		}
		hooks[event] = filteredEntries
	}
	data["hooks"] = hooks
	return writeJSON(path, data)
}

func removeIfEmpty(path string) {
	info, err := os.Stat(path)
	if err != nil || !info.IsDir() {
		return
	}
	entries, err := os.ReadDir(path)
	if err != nil || len(entries) > 0 {
		return
	}
	_ = os.Remove(path)
}

func cleanupEmptyDirectories(repoDir string) {
	dirs := []string{
		".claude/hooks",
		".claude/skills",
		".claude",
		".agents/skills",
		".agents",
		".codex/hooks",
		".codex/prompts",
		".codex",
		"tools/openspec",
		"tools",
	}
	for i := len(dirs) - 1; i >= 0; i-- {
		removeIfEmpty(filepath.Join(repoDir, filepath.FromSlash(dirs[i])))
	}
}

func absoluteDirectory(path string) (string, error) {
	if path == "" {
		return "", errors.New("missing repo path")
	}
	absolutePath, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	info, err := os.Stat(absolutePath)
	if err != nil {
		return "", err
	}
	if !info.IsDir() {
		return "", fmt.Errorf("path is not a directory: %s", absolutePath)
	}
	return absolutePath, nil
}

func backupTimestamp() string {
	return time.Now().UTC().Format("20060102T150405Z")
}
