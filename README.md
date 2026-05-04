# Breakpoint / 破发点

为业余网球爱好者打造的比赛视频智能剪辑工具。

把一段完整的高位机位比赛录像，自动剪成节奏紧凑、保留高光分的精剪视频。

> Breakpoint = 破发点 = 一场比赛中决定胜负的瞬间，也是最值得被剪进集锦的镜头。

## 项目定位

- **输入**：一段完整的业余网球比赛录像（高位机位、未剪辑）
- **输出**：保留高质量回合、去除死时间的精剪视频，分辨率与源一致
- **路线**：先做剪辑工作流，后续扩展到 Web、微信小程序等多端

## 目录结构

```
skills/
  tennis-match-video-editing/   # 核心剪辑 skill：AI prompt + 决策原则 + Python 工具
    SKILL.md
    references/                 # 剪辑原则、模板、示例
    tools/                      # 候选片段生成 + 自动渲染脚本
apps/
  review-tool/                  # 浏览器端片段复核工具（HTML + 本地 server）
    server.py                   # 本地后端，桥接 skill 工具与浏览器
    clip_app.html
    clip_selector.html
    clip_workflow.html
```

## 当前能力

- **自动候选生成**：基于音频降噪 + 球击声节奏分组，从原始视频中识别候选回合（典型召回率 85-90%）
- **自动渲染**：根据剪辑清单 manifest 直接产出最终视频
- **浏览器复核**：可视化检视/调整候选片段后再渲染
- **双路径执行**：自动失败时可降级到半自动 / CapCut / 剪映手动导出

## 快速开始

启动浏览器复核工具：

```bash
python3 apps/review-tool/server.py --root ~/Videos
```

详细工作流见 [skills/tennis-match-video-editing/SKILL.md](skills/tennis-match-video-editing/SKILL.md)。

## Roadmap

- [ ] Web 版（在线上传 + 渲染）
- [ ] 微信小程序版
- [ ] 多视角拼接（双机位/手机+全景机）
- [ ] 球员维度的高光自动归类
