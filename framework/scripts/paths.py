#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paths.py — 项目路径集中定义（A-04）

所有路径由此文件导出，默认值从 __file__ 推导（相对定位，不写死用户名/项目路径），
均支持环境变量覆盖。脚本与 framework 模块统一 `from paths import ...` 取值。

覆盖点（原 scripts/*.py 与 framework/ 共 20 处 /Users/lianghaizhen 硬编码）：
  PROJECT_ROOT      项目根（github-ip-plan）           覆盖：PULSE_ROOT
  WORKBUDDY_ROOT    工作区根（WorkBuddy）             覆盖：PULSE_WORKBUDDY_ROOT
  STAGE             _stage（构建暂存）                = PROJECT_ROOT/_stage
  GIT_PULSE         _git_pulse（线上源）              = PROJECT_ROOT/_git_pulse
  GIT_ENGINE        _git_engine（决策引擎仓）         = PROJECT_ROOT/_git_engine
  ENGINE_STAGE      _engine_stage（引擎暂存）         = PROJECT_ROOT/_engine_stage
  FRAMEWORK         framework                         = PROJECT_ROOT/framework
  CONFIG            framework/config                  = FRAMEWORK/config
  EVIDENCE          evidence                          = PROJECT_ROOT/evidence
  SCRIPTS           scripts                           = PROJECT_ROOT/scripts
  SANITIZER         scripts/sanitizer                 = SCRIPTS/sanitizer
  MANAGED_PY        托管 Python 解释器               覆盖：PULSE_MANAGED_PY
  GH_IP_TOKEN_PATH  fine-grained PAT 路径            覆盖：GH_IP_TOKEN_PATH

导入约定（跟随项目现有 sys.path 惯例）：在消费脚本顶部
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "framework" / "scripts"))
    import paths
（framework/engine 下的模块用 HERE.parent / "scripts"）。
"""
from __future__ import annotations

import os
from pathlib import Path

# 本文件位置：<project>/framework/scripts/paths.py
# _HERE=framework/scripts
#   parents[0]=framework  parents[1]=project(github-ip-plan)
#   parents[2]=日期目录(2026-10-14-10-29-45)  parents[3]=WorkBuddy
_HERE = Path(__file__).resolve().parent

PROJECT_ROOT = Path(os.environ.get("PULSE_ROOT", str(_HERE.parents[1]))).resolve()
# 默认值取 ~/WorkBuddy 而非 __file__ 上溯：框架仓可被 clone 到任意路径
# （2026-10-17 修复： parents[3] 假设仓库位于 <WorkBuddy>/<日期目录>/<项目> 三级
# 之下，换机器或换目录克隆即解析错根，集成测试全红）
WORKBUDDY_ROOT = Path(os.environ.get("PULSE_WORKBUDDY_ROOT",
                                    str(Path.home() / "WorkBuddy"))).resolve()

STAGE = PROJECT_ROOT / "_stage"
GIT_PULSE = PROJECT_ROOT / "_git_pulse"
GIT_ENGINE = PROJECT_ROOT / "_git_engine"
ENGINE_STAGE = PROJECT_ROOT / "_engine_stage"
FRAMEWORK = PROJECT_ROOT / "framework"
CONFIG = FRAMEWORK / "config"
EVIDENCE = PROJECT_ROOT / "evidence"
SCRIPTS = PROJECT_ROOT / "scripts"
SANITIZER = SCRIPTS / "sanitizer"

# 托管 Python 解释器（默认按本机 ~/.workbuddy 推导，可覆盖；不写死用户名）
MANAGED_PY = os.environ.get(
    "PULSE_MANAGED_PY",
    str(Path.home() / ".workbuddy" / "binaries" / "python" / "envs" / "default"
        / "bin" / "python3"),
)

# fine-grained PAT（默认按本机 ~/.config/gh-ip/token 推导，可覆盖）
GH_IP_TOKEN_PATH = Path(os.environ.get(
    "GH_IP_TOKEN_PATH",
    str(Path.home() / ".config" / "gh-ip" / "token")))


def slug_stage_path() -> Path:
    """SLUG_STAGE 单一数据源文件（A-19 收敛产物）。"""
    return CONFIG / "slug_stage.json"
