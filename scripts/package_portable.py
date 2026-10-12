"""Package an existing Windows build, optionally with an offline NLLB model."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json", "shared_vocabulary.txt",
               "sentencepiece.bpe.model", "tokenizer_config.json", "special_tokens_map.json",
               "README.md", "LICENSE", "LICENSE.txt")


def package(build, destination, model=None):
    build, destination = Path(build), Path(destination)
    if not (build / "LocalTranslate.exe").is_file() or not (build / "_internal").is_dir():
        raise ValueError("Build the complete dist/LocalTranslate folder first.")
    if model:
        model = Path(model)
        for name in ("model.bin", "config.json", "tokenizer.json"):
            if not (model / name).is_file():
                raise ValueError(f"Missing model file: {name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.tmp")
    instructions = ("轻译 · Windows x64 便携包\n\n"
                    "1. 请先完整解压；不要在压缩包里直接双击 exe。\n"
                    "2. 打开 LocalTranslate 文件夹，双击 LocalTranslate.exe。\n"
                    "3. 首次使用默认 CPU + int8，无需 Python 或 NVIDIA 显卡。\n"
                    + ("4. 本包包含 NLLB-600M，首次启动自动识别 models 中的模型。\n" if model else
                       "4. 本包不含翻译模型，请在设置中选择 CTranslate2 格式的 NLLB 模型文件夹。\n")
                    + "5. F1 翻译 / F2 命名 / F3 字典 / F4 阅读模式开关。程序常驻系统托盘。\n"
                    "6. 已有配置会保留；如果模型路径或 CUDA 不适合当前电脑，请从托盘设置中调整。\n"
                    "7. 请保留 exe 旁的 _internal 文件夹，不要只复制 exe。\n"
                    "8. 本包不包含任何用户设置、日志或翻译历史。\n"
                    + ("9. 随包模型的说明及授权见 models 内的 README。\n" if model else ""))
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(build.rglob("*")):
            if path.is_file():
                archive.write(path, "LocalTranslate/" + path.relative_to(build).as_posix())
        if model:
            for name in MODEL_FILES:
                if (model / name).is_file():
                    archive.write(model / name, "LocalTranslate/models/NLLB-600M/" + name)
        archive.writestr("LocalTranslate/开始使用.txt", instructions)
    temporary.replace(destination)
    with destination.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Include this local CTranslate2 NLLB model")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    name = "LocalTranslate-Windows-x64" + ("-with-NLLB-600M" if args.model else "") + ".zip"
    result = package(ROOT / "dist" / "LocalTranslate", args.output or ROOT / "release" / name, args.model)
    print(f"Ready: {result} ({result.stat().st_size / 1048576:.1f} MiB)")
