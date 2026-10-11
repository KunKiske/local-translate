# 轻译 · Windows 本地翻译

中英互译、代码命名与离线字典，使用本机 NLLB 模型、本地命名规则和 ECDICT 词典运行。已默认配置 `G:\Models\NLLB-600M`，运行时无需联网，不上传文本。

## 启动

双击 `启动翻译工具.vbs`，或运行 `dist\LocalTranslate\LocalTranslate.exe`。启动后常驻系统托盘，图标为蓝底「译」；模型就绪后会有提示。托盘图标可能收在 Windows 的隐藏图标区域。重复启动会提示程序已在运行。

## 使用

- **F1**：打开统一翻译框。有选中文字时自动填入并翻译；没有选中文字时显示空白输入框，直接输入即可。自动填入的内容也可以自由修改。中文自动译成英文，英文自动译成中文，停止输入约半秒后开始翻译。
- **F2**：打开代码命名框。支持同样的取词 / 空白输入方式；一次描述一个需求，停止输入后生成多个候选名称，单击某个候选即复制、粘贴回原输入位置并关闭窗口。
- **F3**：打开字典框。同样支持取词、空白输入及修改原文；英文查询显示多个中文释义及词性，中文查询显示多个英文候选及对应释义。单击某项即可输出，Enter 输出选中项。
- **F4**：开启 / 关闭阅读模式。开启后，在其他软件中鼠标拖选文字或双击选词，松开鼠标即自动翻译，在选区附近显示简洁标签。标签不抢焦点、不自动粘贴；下一次点击、滚动或切换窗口时收起。再次按快捷键会停止监听并关闭标签，旧结果不会重新弹出。也可通过托盘菜单开关；每次启动默认关闭。
- **输入框内划词**：在轻译自己的输入框里选中文字并松开鼠标，旁边显示单词翻译提示，无需开启 F4。提示不修改输入和整句译文，也不使用剪贴板。取消选择、修改文字或关闭主窗口时收起。
- 再按当前模式的快捷键会关闭窗口，并复制已经完成的结果；按其他模式的快捷键则保留输入并切换模式。自定义组合快捷键也遵循同样规则。
- 三种模式取词均通过 Ctrl+C 获取可复制的选中内容，并在获取后恢复原剪贴板；没有取到文字时不会误用剪贴板中的旧内容。图片中的文字暂不支持取词，可自行输入。
- **Enter**：译文完成后自动复制，关闭窗口，并尝试粘贴回触发快捷键时的窗口。翻译尚未完成时按 Enter 会等待完成后执行。
- **Shift+Enter**：输入多行文字。中文输入法正在组词时，Enter 保留给输入法。
- **点击窗口外 / Esc / ×**：关闭弹窗，将当前已完成译文放入剪贴板，可 Ctrl+V 粘贴。若仍在翻译或发生错误，关闭会取消这次请求并保留原剪贴板，不会在稍后覆盖剪贴板。
- 修改原文或翻译方向会立即清除旧译文，过期的后台结果不会显示或复制。
- 可用方向下拉框强制中译英或英译中；自动模式在检测到汉字时视为中文，否则视为英文。
- 右键托盘图标选择「退出轻译」彻底退出；关闭翻译窗口不会退出程序。

## F2 代码命名

例如输入“玩家移动速度”，可得到 `playerMoveSpeed`、`playerMovementSpeed`、`moveSpeed`、`playerSpeed`。输入“用于管理订单缓存的类”，切换类名格式后可得到 `OrderCacheManager` 等候选。

右上角支持五种命名格式：

| 格式 | 示例 |
| --- | --- |
| 字段 / 变量（camelCase） | `playerMoveSpeed` |
| 类 / 类型（PascalCase） | `PlayerMoveSpeed` |
| 私有字段（_camelCase） | `_playerMoveSpeed` |
| 下划线（snake_case） | `player_move_speed` |
| 常量（UPPER_SNAKE_CASE） | `PLAYER_MOVE_SPEED` |

不同项目的规范可能不同，可自行选择；例如 C# 常量通常也用 PascalCase。所有候选都不含空格，并处理数字开头和常见语言保留字。

- **鼠标单击**候选：输出点击的那一个名字，不包含旁边的说明标签。
- **↑ / ↓**：选择候选；**Enter**：输出选中候选。生成尚未完成时按 Enter，会等待并输出首个候选。
- **点击窗口外 / Esc**：关闭并复制当前选中候选；没有完成的候选时保持剪贴板原样。
- 改动描述或格式会清除旧候选；弹窗打开时按 F1 / F2 / F3 可以保留输入内容并切换模式。
- 一次一个需求（最多 300 字符），建议使用简短用途描述。较长候选可水平滚动查看。

当前命名采用开发术语词表、NLLB 中译英和关键词精简规则。NLLB 本身是翻译模型，不是通用指令模型，因此不会像大语言模型一样理解任意复杂需求；“简短表达”等候选可能省去上下文信息，需要结合代码用途选择。可在 `translator/naming.py` 中扩充项目专用术语。

命名格式参考：[C# 标识符与命名规范](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/coding-style/identifier-names)。模型能力参考：[NLLB 模型说明](https://huggingface.co/facebook/nllb-200-distilled-600M)。

## 配置模型和快捷键

右键托盘图标 →「模型与快捷键设置」，或点击弹窗中的「设置」。可更换模型文件夹、CPU / CUDA、计算精度、输入后等待时间及四个模式的快捷键（默认 F1 / F2 / F3 / F4）。旧版模型设置及快捷键会自动沿用；升级不会覆盖当前配置，未设置过的阅读快捷键默认采用 F4。

**快捷键点击录制**：点击当前快捷键按钮，然后按下单键或组合键，例如 F1 或 Ctrl+Alt+T，无需输入文字。再次点击按钮或按 Esc 取消；切换到其他控件、关闭设置或切到别的窗口也会取消录制。按「保存并应用」后生效。设置窗口打开期间暂停全局快捷键，关闭后恢复，避免录制 F1 时误打开翻译框。

本版支持 **CTranslate2 格式的 NLLB 系列模型**（如 distilled-600M、1.3B），文件夹至少应含 `model.bin`、`config.json`、`tokenizer.json`。不是通用 GGUF / Ollama 模型加载器，原始 Hugging Face 的 safetensors / pytorch_model.bin 权重需要先转换为 CTranslate2 格式。当前提供的 G 盘模型已经是可直接使用的格式。

默认 CPU + int8，不需要显卡。CUDA 模式需自行安装匹配 CTranslate2 的 CUDA / cuBLAS 等运行库；不满足条件时会显示加载错误，可切回 CPU。首次翻译包含模型加载耗时，之后复用已加载模型。

快捷键支持 F1–F11，或 Ctrl / Alt / Shift / Win 搭配字母、数字、功能键、方向键等。四个功能不能重复；其他程序已占用的组合会提示冲突，并保留原来的设置。字母 / 数字不能单独作为全局快捷键；系统保留组合可能无法录制或注册。默认占用 F1 / F2 / F3 / F4，退出轻译后恢复。

CPU 通过中央处理器计算，兼容性好，推荐 int8。CUDA 通过 NVIDIA 显卡计算，适合加速模型推理，需显卡驱动和兼容运行库；支持的精度取决于硬件。当前电脑 RTX 5090 D v2 已实测使用 CUDA + float16：同样三条短句，预热后 CPU + int8 合计约 0.52 秒，CUDA + float16 约 0.16 秒；此数字不含输入等待和首次加载，不代表所有文本。当前用户配置已设为 CUDA + float16、输入等待 250 ms。当前 CUDA 12.4 环境中的 int8_float16 出现过 cuBLAS 兼容错误，不建议在此机器使用该组合。字典直接查询索引，不使用 GPU。

## F3 离线字典

内置约 76.9 万条 [ECDICT](https://github.com/skywind3000/ECDICT) 词条，英文查中文多义项，中文通过释义反查英文。词性以原词典为准，显示名词、动词、形容词等；未标注的条目显示「词性未标注」。候选按照匹配和词频排序，最多展示 40 项。悬停可查看完整释义与音标；单击只输出词义或英文词，不带词性标签。

例如 `bank` 可选择“银行”“堤”“岸”；输入“速度”可查看 `rate`、`speed`、`pace` 等候选及其含义。↑↓ 选择、Enter 输出、关闭复制选中项与命名模式一致。输入后约 200 ms 查询，取词立即查询。英文未精确命中时展示并标明前缀匹配项；完全无匹配时提示未收录，不生成虚构释义。字典适用于不超过 80 字的词或短语，长句请使用 F1 翻译。

词典来源与固定版本见 `data/README.md`，MIT 许可证随程序附带。首次从源码构建需要下载一次词典；日常查询无需联网。

配置保存在 `%LOCALAPPDATA%\LocalTranslate\settings.json`；错误日志在同目录 `app.log`。

## 实际边界

- 自动粘贴要求原窗口仍存在且能取得焦点。如果切换到其他窗口，程序会停止自动粘贴并保留译文供手动粘贴。
- 普通权限程序不能向更高权限的管理员窗口发送模拟按键。这种场景可手动 Ctrl+V。
- 阅读模式通过鼠标选区手势和 Ctrl+C 获取可复制文字，取词后恢复原剪贴板；不支持图片文字 OCR。翻译、设置窗口打开期间暂停外部划词，输入框内划词仍可使用。标签较长时简略显示，可悬停查看完整文本。它与整句翻译复用同一模型，模型首次加载或正在处理其他请求时需稍等。
- 一次最多 6000 字符。长段按 token 分块翻译，不截断原文，但跨块上下文可能影响语义；句段翻译效果更稳定。
- NLLB 的输出质量取决于模型，专业术语、人名和长篇内容建议核对。模型授权以模型目录的 README 为准。

## 源码运行 / 打包

Windows x64、Python 3.11：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe scripts/build_dictionary.py
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pip install pytest pyinstaller
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

分发时复制整个 `dist\LocalTranslate` 文件夹，不能只复制 exe。模型独立存放，不打入程序，换电脑后在设置中重新选择模型目录。

实现参考：[CTranslate2 的 NLLB 用法](https://opennmt.net/CTranslate2/guides/transformers.html#nllb)、[NLLB 分词约定](https://huggingface.co/docs/transformers/model_doc/nllb)、[Windows 全局快捷键](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)、[Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)。
