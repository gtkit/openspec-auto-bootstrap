package bootstrapassets

import (
	"embed"
	"io/fs"
	"strings"
)

//go:embed all:templates/repo VERSION
var embeddedFiles embed.FS

func TemplateFS() (fs.FS, error) {
	return fs.Sub(embeddedFiles, "templates/repo")
}

func Version() string {
	versionBytes, err := embeddedFiles.ReadFile("VERSION")
	if err != nil {
		return "unknown"
	}
	return strings.TrimSpace(string(versionBytes))
}
