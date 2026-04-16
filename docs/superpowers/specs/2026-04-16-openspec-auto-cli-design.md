# OpenSpec Auto CLI Design

## Goal

把当前仓库里的 `install.sh`、`uninstall.sh`、`doctor.sh` 收敛为一个可独立发布的单文件二进制 `openspec-auto`。该二进制安装到 `/usr/local/bin` 或 `$HOME/go/bin` 后，应当可以在任意项目目录执行，不依赖当前源码仓库路径。

同时清理仓库中泄漏的本机绝对路径，补充防回归校验，并发布一个不包含该类泄漏的新版本。

## Requirements

- 提供单一命令入口：`openspec-auto install|uninstall|doctor|version`
- 二进制必须内嵌模板资源，不依赖运行时读取当前仓库的 `templates/`
- `install` 行为需要覆盖现有 shell 脚本的核心能力：
  - 备份目标文件
  - 更新 `AGENTS.md` 和 `CLAUDE.md` managed block
  - 拷贝 hooks、skills、repo-local tools
  - 合并 `.claude/settings.json` 和 `.codex/hooks.json`
  - 处理 `.gitignore`
  - 可选补丁 `~/.codex/config.toml`
  - 可选执行 `openspec init --tools none`
  - 记录版本并运行 healthcheck
- `uninstall` 和 `doctor` 行为与现有脚本保持兼容
- README 中不得再出现任何本机绝对路径
- 增加自动化校验，阻止未来再次提交本机绝对路径
- 删除已泄漏版本对应的 tag / release，发布新版本

## Approach

### CLI

使用 Go 1.26 实现新的 CLI。推荐目录结构：

- `cmd/openspec-auto/main.go`
- `internal/cli/`
- `internal/bootstrap/`

入口层只做参数解析和错误输出；安装、卸载、doctor 的行为集中在 `internal/bootstrap`。

### Embedded Assets

使用 `embed` 将 `templates/repo/**` 和 `VERSION` 打进二进制。安装时从内嵌文件系统读取模板，避免任何运行时仓库路径依赖。

### Compatibility

命令行接口保持接近现有脚本：

- `openspec-auto install [--force] [--skip-codex-user-config] [--skip-openspec-init] <repo>`
- `openspec-auto uninstall <repo>`
- `openspec-auto doctor [repo]`
- `openspec-auto version`

README 示例全部改成基于命令名而非本机路径。

### Testing

优先保留现有 Python `unittest` 体系，新增针对 Go CLI 的集成测试：

- 通过 `go run ./cmd/openspec-auto ...` 验证安装/卸载流程
- 验证 `doctor` 输出
- 验证 README/仓库内容中不存在 `/Users/<user>` 这类本机绝对路径

Go 侧补充少量单元测试，覆盖模板读写和文本补丁等纯逻辑函数。

### Release Cleanup

已确认 `v1.0.0`、`v1.1.0`、`v1.1.1` 的 `README.md` 均包含本机绝对路径，应视为脏版本：

- 删除本地 tag
- 删除远端 tag
- 删除 GitHub Release（若存在）
- 发新版本 `v1.2.0`

## Risks

- shell 到 Go 的迁移如果一次性塞进单文件，会造成维护成本过高；需要提前拆分责任
- 写入 `/usr/local/bin` 与远端 release/tag 删除都需要越过当前 sandbox，需在本地验证完成后单独申请执行
- `openspec` 可执行形式可能既可能是原生命令，也可能是 node 包 shim，需要保留当前脚本里的兼容逻辑

## Out Of Scope

- 不做跨平台安装器（如 Homebrew、Scoop、apt）
- 不重写模板本身的业务逻辑
- 不改现有目标仓库里的 OpenSpec 行为约束
