# GitHub 工具仓上传与版本管理指南（REPO-UPLOAD-GUIDE）

> 文档版本：v1.0.0  
> 适用对象：工程维护人员、部署人员  
> 归档日期：2026-10-17  
> 适用代码库：`github-ip-plan`（内容站统一框架与决策引擎发布管道）

---

## 一、双仓架构与职责边界

在推进自动化部署与 GitHub Pages 发布前，必须彻底理清本项目所涉及的**两个独立 GitHub 仓库**，严禁代码混淆或推错远端：

```
+-------------------------------------------------------------+
| 1. 工具与框架仓 (Tool/Framework Repo)                       |
|    - 建议名称：daily-pulse-framework                         |
|    - 本地目录：github-ip-plan/                              |
|    - 包含内容：scripts/ (渲染与消毒脚本)、framework/ (引擎核心)、|
|                .github/workflows/ (Actions 编排)、测试套件等 |
|    - 职责：负责策略解析、行情容灾、站点渲染与发布调度       |
+-------------------------------------------------------------+
                              |
                              | 自动推送 docs/ 静态产物
                              v
+-------------------------------------------------------------+
| 2. 内容呈现仓 (Content/Pages Repo)                          |
|    - 远端仓库：seaquake97/daily-market-pulse                |
|    - 本地副本：github-ip-plan/_git_pulse/ (独立 git 嵌套仓)   |
|    - 包含内容：仅包含 docs/ 目录（生成的静态 HTML、JSON、XML） |
|    - 职责：供 GitHub Pages 直接托管上线，提供公开访问        |
+-------------------------------------------------------------+
```

**红线禁令**：
- **严禁**将 `github-ip-plan` 工具源码直接推入 `seaquake97/daily-market-pulse` 仓库根目录；
- 内容仓必须保持极简，仅承载静态输出与 Pages 服务，防止工程构建脚本污染内容历史。

---

## 二、本地工具仓现状说明

当前本地工程目录 `github-ip-plan/` 已通过 `git init` 纳入本地 Git 版本控制（A-01 任务已闭环），但**尚未配置 GitHub 远端 remote**。

执行以下命令可查看当前状态：
```bash
git status --short
git remote -v
# 当前输出为空，表示尚未关联任何远端仓库
```

---

## 三、新建 GitHub 工具仓与首次推送

### 3.1 在 GitHub 创建新仓库
1. 登录 GitHub，点击右上角 `+` -> `New repository`；
2. 仓库名称填写：`daily-pulse-framework`（或团队自定工具仓名）；
3. 仓库可见性：建议设为 `Private`（保护策略与自动化配置）或 `Public`；
4. **不要勾选** “Initialize this repository with a README, .gitignore or license”（本地已有完整代码与文件）。

### 3.2 配置本地 Remote 并推送

根据你的 Git 凭证方式选择其一：

#### 方式 A：采用 SSH 密钥（推荐）
```bash
cd github-ip-plan

# 关联远端仓库
git remote add origin git@github.com:<你的GitHub用户名>/daily-pulse-framework.git

# 确保默认分支名为 main
git branch -M main

# 首次全量推送并建立跟踪
git push -u origin main
```

#### 方式 B：采用 HTTPS 协议与个人访问令牌（PAT）
```bash
cd github-ip-plan

# 关联远端仓库
git remote add origin https://github.com/<你的GitHub用户名>/daily-pulse-framework.git

# 推送（提示输入 Password 时填写带有 repo 权限的 Personal Access Token）
git push -u origin main
```

---

## 四、.gitignore 核心过滤清单与防泄密红线

工具仓必须防止临时构建产物、测试快照及个人凭证被误提交。`github-ip-plan/.gitignore` 必须严格包含以下项目：

```gitignore
# 嵌套独立仓库（严禁被主仓整体追踪）
_git_pulse/
_git_engine/
_engine_stage/

# 编译与缓存
__pycache__/
*.py[cod]
.pytest_cache/

# 本地暂存构建产物
_stage/

# 敏感凭证与令牌（最高安全等级）
*token*
*.key
*.pem
.env
.env.*

# 平台与编辑器缓存
.workbuddy/
.DS_Store
.idea/
.vscode/

# 临时测试证据（可按需保留关键基线）
evidence/tmp/
```

**提交前预检命令**：
```bash
# 确认没有凭证或 _stage 被 staged
git status --short
# 若发现敏感文件被暂存，立即撤销：
# git reset HEAD <敏感文件路径>
```

---

## 五、融合作业流与自动化集成（CI/CD）

推荐的标准化开发与自动化发布流程如下：

```
本地特性开发 / 策略调整
        │
        ▼
本地执行统一 CI 门禁
python3 scripts/ci_verify.py
        │
   [24项全通过]
        ▼
提交并推送到工具仓 Feature 分支
git commit -m "feat: 增加新策略"
git push origin feature/xxx
        │
        ▼
在 GitHub 发起 Pull Request 到 main 分支
        │
        ▼
GitHub Actions 自动触发 `verify` 工作流（零网络跑全量 CI）
        │
   [CI 校验绿灯]
        ▼
Merge 进入 main 分支
        │
        ▼
GitHub Actions 定时工作流按交易日时间表触发（09:28 / 11:00 / 14:30 / 15:30）
构建最新站点静态产物并自动 push 到 seaquake97/daily-market-pulse 内容仓
```

---

## 六、常见故障与避坑指南

### 1. 误将工具仓推入内容仓导致文件冲突
- **现象**：执行 `git push origin main` 提示冲突或将 `scripts/` 覆盖到了 `daily-market-pulse`；
- **排查**：检查 `git remote -v`，确认 `origin` 指向的是 `daily-pulse-framework.git`，而不是 `daily-market-pulse.git`。

### 2. 线上 GitHub Actions 跑构建提示 `scripts/ci_verify.py` 超时
- **排查**：检查是否有网络测试未加离线守卫；CI 环境中必须设置默认不连公网测试，仅在配置了代理或特定环境变量时跑真实网络。

### 3. Git 推送提示 Permission denied (publickey)
- **排查**：本机 SSH Key 未添加到 GitHub 账号后台，或者当前机器使用的密钥不具备该仓库的写入权限。可改用 HTTPS + 带有 Contents:write 权限的 PAT 进行推送。
