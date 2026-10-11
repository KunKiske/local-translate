"""Offline naming suggestions: English meaning plus conservative keyword rules.

NLLB supplies English words, not instruction-following or code generation.
Candidates are deterministic alternatives and always valid ASCII identifiers.
"""
import re
import unicodedata


STYLES = (
    ("字段 / 变量 · camelCase", "camel"),
    ("类 / 类型 · PascalCase", "pascal"),
    ("私有字段 · _camelCase", "private"),
    ("下划线 · snake_case", "snake"),
    ("常量 · UPPER_SNAKE_CASE", "constant"),
)
STOP = set("a an the of for to in on at by with from that which this these those "
           "it its my your our their i we you me please would like want need "
           "is are was were be been being used as and or whether".split())
VERBS = set("store stores storing save saves saving record records recording "
            "represent represents representing indicate indicates indicating "
            "control controls controlling manage manages managing track tracks "
            "contain contains containing hold holds holding".split())
SHORT = {"movement": "move", "moving": "move", "maximum": "max", "minimum": "min",
         "quantity": "count", "number": "count", "configuration": "config",
         "information": "info", "identifier": "id", "position": "pos",
         "rotation": "rot", "destination": "target", "velocity": "speed"}
LONG = {v: k for k, v in SHORT.items() if k in ("maximum", "minimum", "configuration", "information", "identifier", "position", "rotation")}
# Common development terms avoid known general-domain mistranslations (for
# example, 重试 must mean retry, not "heavy test"). Unknown phrases still use NLLB.
GLOSSARY = {
    "玩家": "player", "用户": "user", "角色": "character", "敌人": "enemy", "目标": "target",
    "移动": "movement", "速度": "speed", "生命值": "health", "血量": "health", "生命": "life",
    "最大": "maximum", "最小": "minimum", "当前": "current", "默认": "default", "初始": "initial",
    "重试": "retry", "次数": "count", "数量": "count", "总数": "total count", "总计": "total",
    "订单": "order", "缓存": "cache", "管理器": "manager", "控制器": "controller",
    "处理器": "handler", "服务": "service", "工厂": "factory", "配置": "configuration",
    "设置": "settings", "信息": "information", "数据": "data", "列表": "list", "集合": "collection",
    "字典": "dictionary", "队列": "queue", "索引": "index", "编号": "identifier", "标识": "identifier",
    "名称": "name", "名字": "name", "类型": "type", "状态": "state", "位置": "position",
    "旋转": "rotation", "角度": "angle", "方向": "direction", "距离": "distance", "范围": "range",
    "时间": "time", "时长": "duration", "间隔": "interval", "冷却": "cooldown", "延迟": "delay",
    "超时": "timeout", "开始": "start", "结束": "end", "创建": "create", "更新": "update",
    "删除": "delete", "加载": "load", "下载": "download", "上传": "upload", "请求": "request",
    "响应": "response", "连接": "connection", "登录": "login", "退出": "exit", "密码": "password",
    "权限": "permission", "地址": "address", "端口": "port", "路径": "path", "文件": "file",
    "目录": "directory", "图片": "image", "图标": "icon", "文本": "text", "消息": "message",
    "输入": "input", "输出": "output", "窗口": "window", "面板": "panel", "按钮": "button",
    "事件": "event", "回调": "callback", "任务": "task", "线程": "thread", "进度": "progress",
    "动画": "animation", "音量": "volume", "音效": "sound", "伤害": "damage", "攻击": "attack",
    "防御": "defense", "等级": "level", "经验": "experience", "物品": "item", "背包": "inventory",
    "分数": "score", "金币": "coin", "价格": "price", "金额": "amount", "余额": "balance",
    "死亡": "dead", "存活": "alive", "启用": "enabled", "禁用": "disabled", "可见": "visible",
    "隐藏": "hidden", "完成": "completed", "成功": "success", "失败": "failure", "有效": "valid",
    "无效": "invalid", "只读": "read only", "是否": "", "能否": "can", "不": "not", "未": "not",
    "管理": "manage", "控制": "control", "记录": "record", "保存": "save", "存储": "store",
    "用于": "", "用来": "", "用以": "", "的": "", "一个": "", "以及": "and", "和": "and",
}
GLOSSARY_KEYS = sorted(GLOSSARY, key=len, reverse=True)


def glossary_meaning(description):
    parts, offset = [], 0
    while offset < len(description):
        rest = description[offset:]
        english = re.match(r"[A-Za-z0-9_]+", rest)
        if english:
            parts.append(english.group())
            offset += len(english.group())
            continue
        if rest[0].isspace() or rest[0] in "，。！？、,.;:!?()（）":
            offset += 1
            continue
        term = next((term for term in GLOSSARY_KEYS if rest.startswith(term)), None)
        if term is None:
            return None
        parts.append(GLOSSARY[term])
        offset += len(term)
    parts = [part for part in parts if part]
    if parts and parts[0] == "manage":
        parts = parts[1:] + ["manager"]
    return " ".join(parts)
RESERVED = set("abstract as assert async await base bool boolean break byte case catch char "
               "class const continue decimal default def del delegate do double elif else enum "
               "event except explicit export extends extern false False final finally fixed float "
               "for foreach from function global goto if implements implicit import in int interface "
               "internal is lambda let lock long namespace native new None nonlocal not null object "
               "operator or out override package params pass private protected public raise readonly "
               "ref return sbyte sealed short sizeof stackalloc static string struct super switch "
               "synchronized this throw throws transient true True try typeof uint ulong unchecked "
               "unsafe ushort using var virtual void volatile while with yield".split())


def clean_request(text):
    text = " ".join(text.split()).strip()
    if len(text) > 300:
        raise ValueError("命名描述请控制在 300 个字符内，一次描述一个需求。")
    text = re.sub(r"^(?:(?:请|帮我|给我|我想要|我需要|一个|用于|用来|用以|表示|记录|保存|存储)\s*)+", "", text)
    text = re.sub(r"(?:的(?:字段|变量|类名|类|属性|名称|名字)|字段|变量|类名)[。.!！]*$", "", text).strip()
    return text


def words_of(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"['’]s\b", "", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.findall(r"[a-z]+|[0-9]+", text.lower())


def identifier(words, style):
    if style not in {value for _, value in STYLES}:
        raise ValueError("不支持的命名格式。")
    words = list(words)
    if not words:
        raise ValueError("没有可用于命名的英文关键词，请换一个更具体的描述。")
    if words[0][0].isdigit():
        words.insert(0, "value")
    if style == "pascal":
        name = "".join(w.capitalize() for w in words)
    elif style in ("snake", "constant"):
        name = "_".join(words)
        if style == "constant":
            name = name.upper()
    else:
        name = words[0] + "".join(w.capitalize() for w in words[1:])
        if style == "private":
            name = "_" + name
    if name in RESERVED:
        name += "_value" if style == "snake" else "Value"
    return name


def suggest(english, style="camel", original=""):
    english = re.sub(r"^(?:please\s+)?(?:(?:i\s+)?(?:want|need|would like)\s+)?(?:a\s+)?"
                     r"(?:field|variable|class|property|name)\s+(?:used\s+)?(?:that\s+|for\s+|to\s+)",
                     "", english.strip(), flags=re.I)
    english = re.sub(r"^(?:to\s+)?(?:" + "|".join(sorted(VERBS)) + r")\s+", "", english, flags=re.I)
    # Turn English "speed of the player" into identifier order "player speed".
    if len(re.findall(r"\bof\b", english, flags=re.I)) == 1:
        left, right = re.split(r"\bof\b", english, maxsplit=1, flags=re.I)
        qualifiers = re.match(r"^(?:the\s+)?(maximum|minimum|total|current|default|initial)\s+(.+)$", left.strip(), re.I)
        english = (qualifiers[1] + " " + right.strip(" .") + " " + qualifiers[2]) if qualifiers else right.strip(" .") + " " + left.strip()
    words = words_of(english)
    boolean = bool(re.search(r"是否|能否", original) or re.match(r"^(?:is|are|has|have|can|should|whether)\b", english, re.I))
    prefix = next((w for w in words[:2] if w in ("has", "can", "should")), "is")
    content = [w for w in words if w not in STOP and w not in ("has", "have", "can", "should")]
    while len(content) > 1 and content[0] in VERBS:
        content.pop(0)
    while len(content) > 1 and content[-1] in ("field", "variable", "property"):
        content.pop()
    # Remove adjacent duplicates while retaining word order and negation.
    content = [w for i, w in enumerate(content) if i == 0 or w != content[i - 1]]
    if not content:
        # A literal keyword like "class" can still receive a safe identifier.
        content = words
    if not content:
        raise ValueError("没有识别到英文关键词，请输入具体用途，例如“玩家移动速度”。")
    if len(content) > 10:
        raise ValueError("描述较复杂，请缩短为主要用途，例如“玩家移动速度”或“订单缓存管理器”。")
    compact = [SHORT.get(w, w) for w in content]
    expanded = [LONG.get(w, w) for w in content]
    variants = [(compact, "推荐"), (content, "完整表达"), (expanded, "展开缩写")]
    if boolean and len(compact) > 1 and "not" not in compact:
        variants.append((compact[-1:], "简短判断 · 依赖上下文"))
    # Only shorten affirmative noun phrases; do not lose negation or boolean intent.
    if len(compact) >= 3 and not boolean and "not" not in compact:
        variants.extend([(compact[-2:], "简短表达"), ([compact[0], compact[-1]], "保留主体")])
    if len(compact) == 2 and not boolean and "not" not in compact:
        variants.append(([compact[-1]], "极简 · 依赖上下文"))
    if len(compact) == 1:
        variants.extend([(compact + ["type" if style == "pascal" else "value"], "补充用途"),
                         (compact + ["data"], "数据名称")])
    result, seen = [], set()
    for phrase, label in variants:
        if boolean:
            phrase = [prefix] + phrase
        name = identifier(phrase, style)
        if name not in seen:
            seen.add(name)
            result.append({"name": name, "label": label})
    return result[:6]


def generate_names(engine, text, style, settings, cancelled=lambda: False):
    description = clean_request(text)
    if not description:
        raise ValueError("请输入需要命名的具体内容。")
    if cancelled():
        raise InterruptedError("生成已取消")
    chinese = bool(re.search(r"[\u3400-\u9fff\U00020000-\U0002ffff]", description))
    english = glossary_meaning(description) if chinese else description
    if english is None:
        english = engine.translate(description, "zh-en", settings, cancelled)
    if cancelled():
        raise InterruptedError("生成已取消")
    return suggest(english, style, original=text)
