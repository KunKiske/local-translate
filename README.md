# 轻译 · Windows 本地翻译

中英互译，使用本机 NLLB 模型运行。已默认配置 `G:\Models\NLLB-600M`，运行时无需联网，不上传文本。

## 启动

双击 `启动翻译工具.vbs`，或运行 `dist\LocalTranslate\LocalTranslate.exe`。启动后常驻系统托盘，图标为蓝底「译」；模型就绪后会有提示。托盘图标可能收在 Windows 的隐藏图标区域。重复启动会提示程序已在运行。

## 使用

- **F1**：打开统一翻译框。有选中文字时自动填入并翻译；没有选中文字时显示空白输入框，直接输入即可。自动填入的内容也可以自由修改。中文自动译成英文，英文自动译成中文，停止输入约半秒后开始翻译。
- 取词通过 Ctrl+C 获取可复制的选中内容，并在获取后恢复原剪贴板；没有取到文字时不会误用剪贴板中的旧内容。图片中的文字暂不支持取词，可自行输入。F2 不再被程序占用。
- **Enter**：译文完成后自动复制，关闭窗口，并尝试粘贴回触发快捷键时的窗口。翻译尚未完成时按 Enter 会等待完成后执行。
- **Shift+Enter**：输入多行文字。中文输入法正在组词时，Enter 保留给输入法。
- **点击窗口外 / Esc / ×**：关闭弹窗，将当前已完成译文放入剪贴板，可 Ctrl+V 粘贴。若仍在翻译或发生错误，关闭会取消这次请求并保留原剪贴板，不会在稍后覆盖剪贴板。
- 修改原文或翻译方向会立即清除旧译文，过期的后台结果不会显示或复制。
- 可用方向下拉框强制中译英或英译中；自动模式在检测到汉字时视为中文，否则视为英文。
- 右键托盘图标选择「退出轻译」彻底退出；关闭翻译窗口不会退出程序。

## 配置模型和快捷键

右键托盘图标 →「模型与快捷键设置」，或点击弹窗中的「设置」。可更换模型文件夹、CPU / CUDA、计算精度及统一的唤起快捷键（默认 F1）。旧版的模型设置及取词快捷键会自动沿用。

本版支持 **CTranslate2 格式的 NLLB 系列模型**（如 distilled-600M、1.3B），文件夹至少应含 `model.bin`、`config.json`、`tokenizer.json`。不是通用 GGUF / Ollama 模型加载器，原始 Hugging Face 的 safetensors / pytorch_model.bin 权重需要先转换为 CTranslate2 格式。当前提供的 G 盘模型已经是可直接使用的格式。

默认 CPU + int8，不需要显卡。CUDA 模式需自行安装匹配 CTranslate2 的 CUDA / cuBLAS 等运行库；不满足条件时会显示加载错误，可切回 CPU。首次翻译包含模型加载耗时，之后复用已加载模型。

快捷键支持 F1–F11 或 Ctrl+Alt+T 等组合。设置冲突会明确提示；字母 / 数字不能单独作为全局快捷键。默认仅占用 F1，退出轻译后恢复。

配置保存在 `%LOCALAPPDATA%\LocalTranslate\settings.json`；错误日志在同目录 `app.log`。

## 实际边界

- 自动粘贴要求原窗口仍存在且能取得焦点。如果切换到其他窗口，程序会停止自动粘贴并保留译文供手动粘贴。
- 普通权限程序不能向更高权限的管理员窗口发送模拟按键。这种场景可手动 Ctrl+V。
- 一次最多 6000 字符。长段按 token 分块翻译，不截断原文，但跨块上下文可能影响语义；句段翻译效果更稳定。
- NLLB 的输出质量取决于模型，专业术语、人名和长篇内容建议核对。模型授权以模型目录的 README 为准。

## 源码运行 / 打包

Windows x64、Python 3.11：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pip install pytest pyinstaller
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

分发时复制整个 `dist\LocalTranslate` 文件夹，不能只复制 exe。模型独立存放，不打入程序，换电脑后在设置中重新选择模型目录。

实现参考：[CTranslate2 的 NLLB 用法](https://opennmt.net/CTranslate2/guides/transformers.html#nllb)、[NLLB 分词约定](https://huggingface.co/docs/transformers/model_doc/nllb)、[Windows 全局快捷键](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)、[Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)。
