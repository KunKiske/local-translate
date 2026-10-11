"""Offline NLLB inference. A single worker owns the tokenizer and model."""
import os
import re
from pathlib import Path


def language_pair(text, direction="auto"):
    if direction == "zh-en":
        return "zho_Hans", "eng_Latn"
    if direction == "en-zh":
        return "eng_Latn", "zho_Hans"
    # Chinese mixed with English usually represents a Chinese sentence.
    chinese = bool(re.search(r"[\u3400-\u9fff\U00020000-\U0002ffff]", text))
    return ("zho_Hans", "eng_Latn") if chinese else ("eng_Latn", "zho_Hans")


def validate_model(path):
    root = Path(path)
    if not root.is_dir():
        raise ValueError("模型目录不存在，请在设置中选择本地模型文件夹。")
    missing = [name for name in ("model.bin", "config.json", "tokenizer.json") if not (root / name).is_file()]
    if missing:
        raise ValueError("需要 CTranslate2 格式的 NLLB 模型，缺少：" + "、".join(missing))


class TranslationEngine:
    def __init__(self):
        self.key = None
        self.model = None
        self.tokenizer = None

    def load(self, settings):
        key = (settings.model_path, settings.device, settings.compute_type)
        if key == self.key:
            return
        validate_model(settings.model_path)
        from tokenizers import Tokenizer
        import ctranslate2

        tokenizer = Tokenizer.from_file(str(Path(settings.model_path) / "tokenizer.json"))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        for token in ("zho_Hans", "eng_Latn", "</s>"):
            if tokenizer.token_to_id(token) is None:
                raise ValueError("所选分词器不是兼容的 NLLB 分词器：缺少 " + token)
        # Release old weights before loading a different model to bound RAM usage.
        self.key = None
        self.model = None
        model = ctranslate2.Translator(
            settings.model_path, device=settings.device,
            compute_type=settings.compute_type,
            inter_threads=1, intra_threads=min(8, max(1, (os.cpu_count() or 4) // 2)),
        )
        self.model, self.tokenizer, self.key = model, tokenizer, key

    def translate(self, text, direction, settings, cancelled=lambda: False):
        if not text.strip():
            return ""
        if len(text) > 6000:
            raise ValueError("单次最多翻译 6000 个字符，请分段输入。")
        self.load(settings)
        src, dst = language_pair(text, direction)
        result = []
        # Preserve paragraph breaks; tokenize without truncating the user's text.
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                result.append("")
                continue
            pieces = self.tokenizer.encode(paragraph, add_special_tokens=False).tokens
            translated = []
            for offset in range(0, len(pieces), 220):
                if cancelled():
                    raise InterruptedError("翻译已取消")
                source = [src] + pieces[offset:offset + 220] + ["</s>"]
                output = self.model.translate_batch(
                    [source], target_prefix=[[dst]], beam_size=2,
                    max_input_length=512, max_decoding_length=512,
                    repetition_penalty=1.05,
                )[0].hypotheses[0]
                if output and output[0] == dst:
                    output = output[1:]
                if len(output) >= 511:
                    raise ValueError("译文超过单段输出上限，请将原文分成更短的句子后重试。")
                ids = [self.tokenizer.token_to_id(t) for t in output]
                translated.append(self.tokenizer.decode([i for i in ids if i is not None], skip_special_tokens=True))
            result.append((" " if dst == "eng_Latn" else "").join(translated))
        return "\n".join(result).strip()

