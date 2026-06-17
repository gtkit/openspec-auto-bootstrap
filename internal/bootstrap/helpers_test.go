package bootstrap

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseVersion(t *testing.T) {
	cases := []struct {
		raw     string
		want    semVersion
		wantErr bool
	}{
		{"1.2.3", semVersion{1, 2, 3}, false},
		{" 20.19.0 ", semVersion{20, 19, 0}, false},
		{"1.2.3-rc.1", semVersion{1, 2, 3}, false},
		{"1.2", semVersion{1, 2, 0}, false},
		{"1", semVersion{1, 0, 0}, false},
		{"1.2.3.4", semVersion{1, 2, 3}, false},
		{"v1.2.3", semVersion{}, true},
		{"1..3", semVersion{}, true},
		{"", semVersion{}, true},
	}
	for _, tc := range cases {
		got, err := parseVersion(tc.raw)
		if tc.wantErr {
			if err == nil {
				t.Errorf("parseVersion(%q) expected error, got %+v", tc.raw, got)
			}
			continue
		}
		if err != nil {
			t.Errorf("parseVersion(%q) unexpected error: %v", tc.raw, err)
			continue
		}
		if got != tc.want {
			t.Errorf("parseVersion(%q) = %+v, want %+v", tc.raw, got, tc.want)
		}
	}
}

func TestSemVersionCompare(t *testing.T) {
	cases := []struct {
		a, b semVersion
		want int
	}{
		{semVersion{20, 19, 0}, semVersion{20, 19, 0}, 0},
		{semVersion{20, 19, 1}, semVersion{20, 19, 0}, 1},
		{semVersion{20, 18, 9}, semVersion{20, 19, 0}, -1},
		{semVersion{21, 0, 0}, semVersion{20, 99, 99}, 1},
		{semVersion{19, 99, 99}, semVersion{20, 0, 0}, -1},
	}
	for _, tc := range cases {
		if got := tc.a.compare(tc.b); got != tc.want {
			t.Errorf("%+v.compare(%+v) = %d, want %d", tc.a, tc.b, got, tc.want)
		}
	}
}

func TestEnsureLineOnce(t *testing.T) {
	path := filepath.Join(t.TempDir(), "CLAUDE.md")

	if err := ensureLineOnce(path, "@AGENTS.md"); err != nil {
		t.Fatalf("first ensureLineOnce: %v", err)
	}
	if err := ensureLineOnce(path, "@AGENTS.md"); err != nil {
		t.Fatalf("second ensureLineOnce: %v", err)
	}

	content := readFile(t, path)
	if n := strings.Count(content, "@AGENTS.md"); n != 1 {
		t.Fatalf("expected @AGENTS.md exactly once, got %d in:\n%s", n, content)
	}
}

func TestUpsertManagedBlockIdempotentAndDollarSafe(t *testing.T) {
	path := filepath.Join(t.TempDir(), "AGENTS.md")

	// Block content intentionally contains "$" sequences that would be
	// mangled if a non-literal regexp replacement were used.
	block := managedBlockStart + "\nUse $HOME and ${VAR} and $1 here.\n" + managedBlockEnd

	if err := writeTextFile(path, "# Title\n\nExisting prose.\n", 0o644); err != nil {
		t.Fatalf("seed file: %v", err)
	}

	if err := upsertManagedBlock(path, []byte(block)); err != nil {
		t.Fatalf("first upsert: %v", err)
	}
	first := readFile(t, path)
	if !strings.Contains(first, "$HOME and ${VAR} and $1") {
		t.Fatalf("dollar signs were mangled:\n%s", first)
	}
	if !strings.Contains(first, "Existing prose.") {
		t.Fatalf("existing content was dropped:\n%s", first)
	}

	// Re-running must replace in place, not append a second block.
	if err := upsertManagedBlock(path, []byte(block)); err != nil {
		t.Fatalf("second upsert: %v", err)
	}
	second := readFile(t, path)
	if n := strings.Count(second, managedBlockStart); n != 1 {
		t.Fatalf("expected exactly one managed block, got %d:\n%s", n, second)
	}
}

func TestRemoveManagedBlock(t *testing.T) {
	path := filepath.Join(t.TempDir(), "AGENTS.md")
	block := managedBlockStart + "\nmanaged content\n" + managedBlockEnd
	original := "# Title\n\nExisting prose.\n"

	if err := writeTextFile(path, original, 0o644); err != nil {
		t.Fatalf("seed: %v", err)
	}
	if err := upsertManagedBlock(path, []byte(block)); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	if err := removeManagedBlock(path); err != nil {
		t.Fatalf("remove: %v", err)
	}

	content := readFile(t, path)
	if strings.Contains(content, managedBlockStart) || strings.Contains(content, "managed content") {
		t.Fatalf("managed block was not removed:\n%s", content)
	}
	if !strings.Contains(content, "Existing prose.") {
		t.Fatalf("user content was lost:\n%s", content)
	}
}

func TestMergeJSONDedupesHooksAndPreservesKeys(t *testing.T) {
	path := filepath.Join(t.TempDir(), "settings.json")

	existing := `{
  "model": "keep-me",
  "hooks": {
    "PreToolUse": [
      {"hooks": [{"command": "user-hook"}]}
    ]
  }
}`
	if err := writeTextFile(path, existing, 0o644); err != nil {
		t.Fatalf("seed: %v", err)
	}

	incoming := []byte(`{
  "model": "should-not-override",
  "permissions": {"allow": ["x"]},
  "hooks": {
    "PreToolUse": [
      {"hooks": [{"command": "user-hook"}]},
      {"hooks": [{"command": "openspec-hook"}]}
    ]
  }
}`)

	// Merge twice to confirm idempotency (no duplicate hook entries).
	if err := mergeJSON(path, incoming); err != nil {
		t.Fatalf("first merge: %v", err)
	}
	if err := mergeJSON(path, incoming); err != nil {
		t.Fatalf("second merge: %v", err)
	}

	var result map[string]any
	if err := json.Unmarshal([]byte(readFile(t, path)), &result); err != nil {
		t.Fatalf("parse result: %v", err)
	}

	if result["model"] != "keep-me" {
		t.Errorf("existing key was overridden: model=%v", result["model"])
	}
	if _, ok := result["permissions"]; !ok {
		t.Errorf("new key was not added: permissions missing")
	}

	hooks, _ := result["hooks"].(map[string]any)
	pre, _ := hooks["PreToolUse"].([]any)
	if len(pre) != 2 {
		t.Fatalf("expected 2 deduped PreToolUse entries, got %d: %v", len(pre), pre)
	}
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(data)
}
