"""Offline ECDICT lookup. Definitions and parts of speech come from the dictionary."""
from pathlib import Path
import re
import sqlite3

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "dictionary.sqlite3"
POS = {"n": "名词", "v": "动词", "vt": "及物动词", "vi": "不及物动词",
       "a": "形容词", "adj": "形容词", "ad": "副词", "adv": "副词",
       "pron": "代词", "prep": "介词", "conj": "连词", "interj": "感叹词",
       "int": "感叹词", "num": "数词", "art": "冠词", "aux": "助动词", "abbr": "缩写"}
POS_PATTERN = re.compile(r"^((?:(?:vt|vi|adj|adv|pron|prep|conj|interj|int|num|art|aux|abbr|ad|n|v|a)\.(?:\s*[/&,]\s*)?)+)\s*", re.I)


def search_terms(text):
    """Unigrams support one-character queries; bigrams narrow Chinese phrases."""
    terms = set()
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        terms.update(run)
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return " ".join(sorted(terms))


def senses(translation):
    for line in translation.replace("\\n", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        match = POS_PATTERN.match(line)
        if match:
            codes = re.findall(r"[a-z]+", match[1].lower())
            pos = " / ".join(dict.fromkeys(POS.get(code, code) for code in codes))
            yield pos, line[match.end():].strip()
        else:
            yield "词性未标注", line


def split_gloss(gloss):
    """Split alternatives without breaking parenthesized explanations."""
    depth, start = 0, 0
    for index, char in enumerate(gloss):
        if char in "(（[【":
            depth += 1
        elif char in ")）]】":
            depth = max(0, depth - 1)
        elif char in ";；,，" and not depth:
            yield gloss[start:index].strip()
            start = index + 1
    yield gloss[start:].strip()


def exact_sense(query, gloss):
    return any(re.sub(r"^\[[^]]+\]\s*", "", meaning).strip() == query for meaning in split_gloss(gloss))


class Dictionary:
    def __init__(self, path=DATA_FILE):
        self.path = Path(path)
        self.connection = None

    def lookup(self, text, cancelled=lambda: False):
        query = " ".join(text.strip().split())
        if not query:
            return []
        if len(query) > 80:
            raise ValueError("字典适合查询单词或短语（最多 80 字）；长句请使用翻译模式。")
        if not self.path.is_file():
            raise ValueError("未找到离线词典，请重新运行 scripts/build_dictionary.py 并打包。")
        if self.connection is None:
            self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        db = self.connection
        db.set_progress_handler(lambda: int(cancelled()), 1000)
        chinese = bool(re.search(r"[\u3400-\u9fff]", query))
        prefix = False
        try:
            if cancelled():
                raise InterruptedError("查询已取消")
            if chinese:
                runs = re.findall(r"[\u3400-\u9fff]+", query)
                terms = {run[i:i + 2] for run in runs for i in range(max(1, len(run) - 1))}
                match = " AND ".join('"' + term + '"' for term in sorted(terms))
                rows = db.execute("SELECT word, phonetic, translation FROM entries WHERE id IN "
                                  "(SELECT rowid FROM search WHERE search MATCH ?) "
                                  "AND instr(translation, ?) > 0 ORDER BY rank, length(word), word LIMIT 600",
                                  (match, query)).fetchall()
            else:
                rows = db.execute("SELECT word, phonetic, translation FROM entries WHERE word = ? COLLATE NOCASE",
                                  (query,)).fetchall()
                if not rows:
                    prefix = True
                    low = query.lower()
                    rows = db.execute("SELECT word, phonetic, translation FROM entries "
                                      "WHERE word COLLATE NOCASE >= ? AND word COLLATE NOCASE < ? "
                                      "ORDER BY rank, length(word) LIMIT 12", (low, low + '\uffff')).fetchall()
        except sqlite3.OperationalError:
            if cancelled():
                raise InterruptedError("查询已取消") from None
            raise
        finally:
            db.set_progress_handler(None, 0)
        candidates = []
        seen = set()
        for word, phonetic, translation in rows:
            for pos, gloss in senses(translation):
                if chinese and query not in gloss:
                    continue
                meanings = [gloss] if chinese else split_gloss(gloss)
                for meaning in meanings:
                    meaning = meaning.strip()
                    if not meaning:
                        continue
                    name = word if chinese else meaning
                    identity = (name, pos)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    candidates.append({"name": name, "label": f"{word} · {pos}" + (" · 前缀匹配" if prefix else ""),
                                       "detail": gloss, "phonetic": phonetic})
        # Prefer exact Chinese senses before broader definitions, then common words.
        if chinese:
            candidates.sort(key=lambda c: not exact_sense(query, c["detail"]))
        return candidates[:40]
