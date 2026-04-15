# OpenSpec Auto Bootstrap

一个独立可复用的 bootstrap 目录，用来把 **OpenSpec-first 工作流** 自动接入到 **Codex** 和 **Claude Code**。

目标是让你在业务仓库里做到下面这件事：

- 用户只说“实现 X / 修复 Y / 修改 Z”
- 不需要用户手动输入 `openspec ...`
- 不需要用户手动输入 `/opsx:*`
- Agent 自动进入 OpenSpec 流程：
  - 检查 active changes
  - 选择或创建 change
  - 生成 proposal / design / specs / tasks
  - 在 apply-ready 后再改业务代码
  - 在收尾时做 validate 和常规测试

这套 bootstrap 采用的是：

- **仓库内规则**：`AGENTS.md`、`CLAUDE.md`
- **仓库内技能**：`.claude/skills/openspec-auto`、`.agents/skills/openspec-auto`
- **仓库内 hooks**：Claude Code / Codex 分别挂钩
- **仓库内工具脚本**：`tools/openspec/*`
- **外部安装器**：本目录下的 `install.sh`

这样做的好处是：

- 不依赖某台机器里“碰巧正确”的全局 prompt
- 规则可以跟仓库一起版本化、审查、回滚
- 同一套仓库配置可以给团队成员统一复用
- 更适合生产环境和多人协作

---

## 1. 适用范围

适合接入 OpenSpec 的请求类型：

- 新功能开发
- Bug 修复
- 会改变行为的重构
- API / DTO / DB / migration / 前端行为修改
- 会改变运行时行为的配置修改

不应该强制走 OpenSpec 的请求类型：

- 纯解释、纯问答
- 只读代码审查
- 纯文档修改
- 与仓库运行时行为无关的运维说明类问题

---

## 2. 目录结构

```text
openspec-auto-bootstrap/
  README.md
  install.sh
  uninstall.sh
  doctor.sh
  templates/
    repo/
      AGENTS.md
      CLAUDE.md
      .claude/
        settings.json
        hooks/
          openspec_context.py
          openspec_router.py
          openspec_guard.py
          openspec_stop.py
        skills/
          openspec-auto/
            SKILL.md
      .codex/
        config.toml.append
        prompts/
          openspec-auto.md
        hooks.json
        hooks/
          openspec_context.py
          openspec_router.py
          openspec_guard.py
          openspec_stop.py
      .agents/
        skills/
          openspec-auto/
            SKILL.md
      tools/
        openspec/
          env.sh
          healthcheck.sh
          hook_common.py
          classify_request.py
          resolve_change.py
          validate_repo.py
          sync_templates.sh
```

设计原则：

- `templates/repo/` 里的内容就是最终要落到业务仓库里的文件
- 根目录脚本只负责安装、卸载、体检
- 仓库落地后，即使不保留这个 bootstrap 目录，仓库本身仍然可以工作

---

## 3. 环境要求

最少要求：

- `python3`
- `node >= 20.19.0`
- `openspec`
- `git`

推荐同时具备：

- `claude`
- `codex`

你当前本地已经确认是 `node v24.6.0`，满足 OpenSpec / Codex / Claude Code 这一层的运行要求。

注意两点：

1. **不要只看你装了什么版本，要看当前 shell 实际跑的是哪个 `node`**
   - 之前你机器上出现过“安装的是新版，但执行时落到了旧版 `node v13.14.0`”的情况
   - 这会导致 `openspec` 和 `codex` 直接报现代语法错误

2. **bootstrap 默认关闭 OpenSpec telemetry**
   - 脚本会设置 `OPENSPEC_TELEMETRY=0`
   - 这是为了减少离线环境、受限网络、CI 环境里的噪音和不确定性

---

## 4. 快速安装

假设你要把它接到业务仓库：

```bash
/Users/xiaozhaofu/openspec-auto-bootstrap/install.sh /absolute/path/to/your-repo
```

安装完成后，直接在目标仓库里打开 Claude Code 或 Codex，然后正常说需求即可：

- `实现订单超时自动取消`
- `修复支付回调重复入库`
- `把会员试用逻辑改成 7 天`

你不需要手动输入：

- `openspec ...`
- `/opsx:propose ...`
- `/opsx:apply ...`

---

## 5. 安装脚本会做什么

`install.sh` 会按下面顺序工作。

### 5.1 校验本机环境

会检查：

- `python3`
- `node`
- `openspec`
- `node` 版本是否 `>= 20.19.0`

### 5.2 初始化仓库级 OpenSpec 目录

如果目标仓库还没有 `openspec/`，脚本会运行：

```bash
openspec init --tools none /path/to/repo
```

为什么用 `--tools none`：

- 我们只要 OpenSpec 的仓库结构
- 不想让 OpenSpec CLI 自己去改你的全局 Codex / Claude 配置
- 真正的 Claude/Codex 集成由本 bootstrap 自己接管

这一步会创建最基础的：

- `openspec/specs/`
- `openspec/changes/`
- OpenSpec 配置文件

### 5.3 安装仓库内规则

脚本会把一个 **managed block** 注入到：

- `AGENTS.md`
- `CLAUDE.md`

其中：

- `AGENTS.md` 是真正的流程约束源
- `CLAUDE.md` 负责把 Claude 引到 `@AGENTS.md`

### 5.4 安装技能

会安装两份 `openspec-auto`：

- `.claude/skills/openspec-auto/SKILL.md`
- `.agents/skills/openspec-auto/SKILL.md`

原因：

- Claude Code 走 `.claude/skills`
- Codex 官方技能目录走 `.agents/skills`

### 5.5 安装 hooks

会安装：

- Claude hooks：`.claude/hooks/*.py`
- Codex hooks：`.codex/hooks/*.py`
- Claude hook 配置：`.claude/settings.json`
- Codex hook 配置：`.codex/hooks.json`

### 5.6 安装仓库内工具脚本

会安装到：

- `tools/openspec/env.sh`
- `tools/openspec/healthcheck.sh`
- `tools/openspec/hook_common.py`
- `tools/openspec/classify_request.py`
- `tools/openspec/resolve_change.py`
- `tools/openspec/validate_repo.py`
- `tools/openspec/sync_templates.sh`

### 5.7 修补用户级 Codex 配置

默认会尝试把下面这项确保写进 `~/.codex/config.toml`：

```toml
[features]
codex_hooks = true
```

这是为了让 Codex 的 repo-local hooks 真正生效。

如果你不想自动修改用户配置，可以安装时加：

```bash
--skip-codex-user-config
```

---

## 6. 安装参数

### 6.1 `--force`

```bash
./install.sh --force /path/to/repo
```

含义：

- 允许覆盖 managed 文件
- 覆盖前会先做备份

### 6.2 `--skip-codex-user-config`

```bash
./install.sh --skip-codex-user-config /path/to/repo
```

含义：

- 不修改 `~/.codex/config.toml`
- 适合你自己要手工管理 Codex 全局配置的场景

### 6.3 `--skip-openspec-init`

```bash
./install.sh --skip-openspec-init /path/to/repo
```

含义：

- 不执行 `openspec init --tools none`
- 适合仓库里已经有完整 OpenSpec 目录的场景

---

## 7. 备份策略

每次安装都会在目标仓库下创建备份目录：

```text
.openspec-auto-backup/<UTC 时间戳>/
```

用途：

- 回滚被覆盖的配置文件
- 审计本次安装改了什么

这也是为什么生产环境建议所有接入都通过 `install.sh`，而不是人工拷文件。

---

## 8. 日常使用方式

安装完成后，日常使用分成两种。

### 8.1 正常业务开发

直接说业务需求：

- `实现短信登录`
- `修复库存扣减并发问题`
- `把导出接口改成异步任务`

期望行为：

1. Router hook 判断这是“会改行为”的请求
2. 注入额外上下文，提醒 agent 走 `openspec-auto`
3. `openspec-auto` skill 检查 active changes
4. 没有 change 就自动创建
5. 补齐 proposal / design / specs / tasks
6. 到 apply-ready 后再改业务代码
7. 最后跑 `openspec validate`

### 8.2 只读问题

例如：

- `解释一下这个仓库的分层`
- `review 这段 SQL 有没有问题`
- `总结一下订单状态机`

期望行为：

- 不强行进入 OpenSpec
- 正常回答或只读审查

---

## 9. 自动触发机制

这是整个方案的核心。

### 9.1 SessionStart

作用：

- 会话开始时注入 OpenSpec 状态上下文
- 告诉 agent 当前仓库启用了 OpenSpec-first
- 摘要 active changes

收益：

- 减少每轮都重新判断仓库是否启用 OpenSpec
- 降低上下文漂移

### 9.2 UserPromptSubmit

作用：

- 在用户每次发消息时做请求分类
- 判断是不是“会改代码 / 改行为”的请求

如果判定需要 OpenSpec：

- 注入额外上下文，明确要求使用 `openspec-auto`
- 如果仓库已有 active change，尽量建议继续那个 change
- 如果有多个可能 change，则提示 agent 必须问用户，不允许乱选

### 9.3 PreToolUse

作用：

- 在真正执行编辑前做一次守门

Claude Code 侧：

- 会尝试拦 `Edit | Write | MultiEdit | Bash`

Codex 侧：

- 当前按保守策略只挂 `Bash`
- 这是因为 Codex hooks 能力还在演进，不能假设它已经像 Claude 一样完整拦截所有写入工具

### 9.4 Stop

作用：

- 当 agent 准备收尾、给出“已完成”之类的答复时
- 做最后一层校验

校验内容：

- 有没有 active change
- 有没有代码修改落在 `openspec/` 外面但没有 change
- 当前 change 是否 `openspec validate` 通过

这个 hook 不是每轮都拦，它主要针对“要宣称完成”时的收口阶段。

---

## 10. `openspec-auto` skill 做什么

这份 skill 的职责不是替代 OpenSpec，而是把 OpenSpec 串起来。

它的默认流程是：

1. `openspec list --json`
2. 解析当前 active changes
3. 选择 change：
   - 用户明确指定 change：直接用
   - 只有一个明显匹配的 active change：继续
   - 多个可能 change：必须问用户
   - 没有 active change：自动创建
4. `openspec new change "<name>"`
5. `openspec status --change "<name>" --json`
6. 对每个 `ready` 的 artifact：
   - `openspec instructions <artifact-id> --change "<name>" --json`
   - 生成对应 artifact 文件
7. 当所有 `applyRequires` 都完成后，进入业务代码修改
8. 收尾时运行：
   - `openspec validate "<name>" --type change --strict --json --no-interactive`
   - 仓库自己的测试和校验

这个 skill 的设计重点是：

- 用户不需要记命令
- Agent 不要把“你先运行 openspec xxx”甩回给用户

---

## 11. 生产环境落地建议

这部分是最重要的。

### 11.1 不要只依赖 prompt

生产级必须至少有这三层：

1. `AGENTS.md / CLAUDE.md`
2. `skills`
3. `hooks + CI`

缺任何一层，都容易变成“偶尔遵守、偶尔漂移”。

### 11.2 一定要加 CI 门禁

推荐在 CI 里加至少一条：

```bash
python3 tools/openspec/validate_repo.py --repo . --ci
```

建议同时再加：

```bash
OPENSPEC_TELEMETRY=0 openspec validate --changes --strict --json --no-interactive
```

推荐门禁语义：

- 如果 `openspec/` 外有代码修改，但没有 active change：失败
- 如果 active change 校验失败：失败
- 如果只改文档，没有行为变化：通过

### 11.3 把 bootstrap 当成“标准接入器”

团队推广时，不要让每个人自己配。

正确方式：

1. 统一用本 bootstrap 安装
2. 所有接入都走 PR
3. 让 `AGENTS.md` / hooks / skills 一起纳入版本控制
4. 让 CI 去兜底

### 11.4 固定 Node 和 OpenSpec 版本

建议至少固定：

- Node LTS
- OpenSpec CLI 版本
- Claude / Codex 版本范围

可选方式：

- `mise`
- `asdf`
- `volta`
- `devcontainer`

目标不是“最新”，而是“团队一致”。

### 11.5 建议把 telemetry 在自动化链路里关掉

在下面这些场景里，建议默认关：

- CI
- 受限网络
- 沙箱环境
- 企业内网

本模板已经默认通过环境变量处理：

```bash
OPENSPEC_TELEMETRY=0
```

---

## 12. Codex 与 Claude Code 的差异

### Claude Code

强项：

- hooks 能力相对更成熟
- `CLAUDE.md` / skills / hooks 配合度更高
- 可以更强地拦截写入前动作

因此：

- Claude Code 是这套方案里“强约束”的主场

### Codex

强项：

- `AGENTS.md`
- `.agents/skills`
- repo-local hook 机制

当前要保守看待的点：

- 对非 Bash 类写入工具的 PreToolUse 拦截能力，不建议过度假设

因此：

- Codex 侧必须同时依赖：
  - `AGENTS.md`
  - `.agents/skills/openspec-auto`
  - `Stop` hook
  - CI 门禁

一句话总结：

- **Claude 侧偏“前置强约束”**
- **Codex 侧偏“规则 + 收口 + CI 兜底”**

---

## 13. 体检命令

### 13.1 体检 bootstrap 自身

```bash
/Users/xiaozhaofu/openspec-auto-bootstrap/doctor.sh
```

### 13.2 体检某个仓库

```bash
/Users/xiaozhaofu/openspec-auto-bootstrap/doctor.sh /absolute/path/to/repo
```

实际会调用仓库里的：

```bash
tools/openspec/healthcheck.sh
```

会检查：

- `python3`
- `node`
- `openspec`
- OpenSpec CLI 在当前仓库里是否能正常执行
- 仓库级 `validate_repo.py --smoke`

---

## 14. 卸载

卸载命令：

```bash
/Users/xiaozhaofu/openspec-auto-bootstrap/uninstall.sh /absolute/path/to/repo
```

会移除：

- managed block
- hooks
- skills
- repo-local OpenSpec auto 工具脚本
- `~/.codex/config.toml` 里 bootstrap 插入的标记行

不会移除：

- 仓库里的 `openspec/` 内容

原因很简单：

- 这些 artifact 往往已经是你真实项目的规格资产，不应该在卸载集成时被删掉

---

## 15. 常见问题

### 15.1 明明安装了新版 Node，为什么还是报语法错误？

根因通常不是“没装”，而是“当前 shell 实际执行的不是你以为的那个 `node`”。

先看：

```bash
node -v
which node
openspec --version
```

如果 `node -v` 不是 `>= 20.19.0`，先修 PATH，再谈 OpenSpec 自动化。

### 15.2 Agent 还是让我手动输入 openspec 命令

先检查四层：

1. 仓库里有没有 `AGENTS.md`
2. 仓库里有没有 `.claude/skills/openspec-auto` 或 `.agents/skills/openspec-auto`
3. hooks 是否启用
4. Codex 的 `codex_hooks = true` 是否生效

然后运行：

```bash
tools/openspec/healthcheck.sh
```

### 15.3 多个 active changes 时为什么还会问我？

这是故意的。

生产环境里不能让 agent 在多个 plausible changes 之间“凭感觉选一个”。

正确行为就是：

- 用户没指定
- 当前有多个活跃 change
- agent 必须问清楚

### 15.4 只改 README，为什么不该强制走 OpenSpec？

因为这类请求不改变系统行为。

OpenSpec-first 的目标是管住“行为变化”，不是把所有编辑都变成重流程。

### 15.5 为什么 `.codex/prompts/openspec-auto.md` 还要保留？

它是一个 **兼容性兜底**：

- 不是核心依赖
- 不是自动触发主链路
- 主要是给支持 prompt 文件的运行形态一个手动 fallback

真正核心的是：

- `AGENTS.md`
- `.agents/skills/openspec-auto`
- hooks
- CI

---

## 16. 推荐上线顺序

建议按下面顺序推广。

### 阶段 1：试点仓库

- 先选 1 个仓库安装
- 先让 Claude Code 跑顺
- 再验证 Codex

### 阶段 2：加入 CI

- 把 `validate_repo.py --ci` 放进流水线
- 确保没有 OpenSpec change 的行为改动无法合并

### 阶段 3：团队标准化

- 固定 Node / OpenSpec 版本
- 统一安装方式
- 接入文档走本 README

### 阶段 4：再考虑插件化

首版不要急着做成全局插件优先。

原因：

- 插件形态更适合做长期分发
- 但首版最重要的是“稳定接住生产流量”，不是“包装得很酷”

bootstrap + repo-local files 是更稳的第一阶段方案。

---

## 17. 你最该记住的三件事

1. 这套方案的关键不是某一个 skill，而是 **AGENTS + skill + hooks + CI** 这四层一起工作。
2. 生产环境里不要只靠“让模型自觉遵守流程”，一定要把规则写进仓库并加门禁。
3. 如果自动化失效，先查运行时 `node`、`openspec`、hook 是否真的生效，再查 prompt。
