# shot-deps：镜头依赖预检 🎬

在开始下一轮 AI 视频生成或动画渲染前，离线检查素材缺失、参考图版本变化、镜头依赖阻塞，并找出哪些下游镜头需要重做。

Python 3.10+，仅标准库，无需安装依赖，不联网，不修改素材。

## 立即体验

在仓库点 Code → Download ZIP，解压后在该文件夹打开终端：

```sh
python shot_deps.py examples/project.json --changed hero
python -m unittest discover -s tests -v
```

也可用 Git：

```sh
git clone https://github.com/BohaoWorks/shot-deps.git
cd shot-deps
python shot_deps.py examples/project.json --changed hero --json
```

macOS/Linux 可将 python 换成 python3；Windows 可换成 py。

示例都是原创合成文本素材，无真实生产资料。正常示例会显示 PASS；hero 的变更影响 S010、S020、S030。故障示例：

```sh
python shot_deps.py examples/broken.json --json
```

预期退出码为 1：voice 文件缺失导致 S010 阻塞，S020 被上游 S010 阻塞。

## 接入自己的项目

在素材根目录创建 UTF-8 JSON 清单：

```json
{
  "version": 1,
  "assets": {
    "hero": {"path": "assets/hero.png"},
    "voice": {"path": "audio/line.wav"}
  },
  "shots": {
    "S010": {"assets": ["hero", "voice"], "needs": []},
    "S020": {"assets": ["hero"], "needs": ["S010"]}
  }
}
```

assets 为素材 ID；needs 是当前镜头依赖的上游镜头 ID。运行层级仅表达先后依赖，不代表完成或审核状态。同层镜头可独立处理；一个上游出现问题会阻塞所有下游，其他健康分支仍会列出。

默认以清单所在目录解析素材，即使从其他目录启动也不受影响。可通过 --root 指定其他本地根目录。路径使用 /；拒绝绝对路径、盘符、反斜线、..，不读取指向根目录外的符号链接。它不是针对恶意并发文件替换的安全沙箱。

可给素材添加 sha256 字段，锁定已确认版本。哈希不匹配时标为 changed，并追踪全部受影响镜头。用下列命令本地计算摘要，确认素材正确后手动填入清单：

```sh
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('assets/hero.png').read_bytes()).hexdigest())"
```

检查器分块读取，不把大文件整体载入内存；上面的便捷摘要命令会整体读取。没有 sha256 时只检查文件存在性。重复使用 --changed hero --changed voice 可模拟变更影响，不修改素材、不阻塞健康镜头。

## 结果与退出码

- 0：通过；1：素材或依赖问题；2：清单/输入无效
- --json 输出结构化报告，适合本地脚本或 CI
- asset_status：ok、missing、changed、outside_root、unreadable
- blocked：被阻塞镜头及原因
- runnable_layers：健康镜头的依赖层级
- cycle_or_downstream：循环成员及其下游，不是精确循环路径
- impacted_shots：手动指定或哈希变化所影响的全部下游镜头
- unused_assets：清单中未被镜头引用的素材；若缺失也会退出 1

重复 JSON 键、未知字段、重复引用会被拒绝，空项目合法。报告可能包含你自己的路径和 ID，分享前请检查。

## 边界

不渲染、不解码媒体、不评价画面连贯性、不解析剪辑时间线、不记录任务完成状态。Blender、Premiere、Resolve、提示词内部的引用需手动加入清单。哈希只判断字节变化，不能判断视觉差异。不自动更新哈希，不删除资产，不上传内容。

本地测试覆盖 22 项：缺失/未知引用、哈希变化、循环与长链依赖、路径边界、输入结构及 CLI 退出码。CI 在 Linux、Windows、macOS 和 Python 3.10/3.13 上运行；无符号链接创建权限的平台仅跳过该项测试。

[English documentation](README.md) · MIT 许可证
