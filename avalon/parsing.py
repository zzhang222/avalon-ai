"""解析模型回复。模型输出格式不总是规整（Markdown 加粗、半角冒号、多余说明），这里尽量宽容。"""
import re

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.I)
_DECOR_RE = re.compile(r"[*_`#>]+")
_NAME_SPLIT_RE = re.compile(r"[、,，;；/|\s]+|和|与")


def strip_think(text):
    """去掉 Qwen 等本地模型的 <think>…</think> 思考块。"""
    return _THINK_RE.sub("", text or "").strip()


def _clean(line):
    line = _DECOR_RE.sub("", line).strip()
    return re.sub(r"^[-•·]\s*", "", line)


def find_field(text, *labels):
    """找到形如「标签：值」的行并返回值（兼容全角/半角冒号与 Markdown 装饰）。"""
    for raw in (text or "").splitlines():
        line = _clean(raw)
        for label in labels:
            m = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.*)$", line)
            if m:
                return m.group(1).strip()
    return None


def remove_field_lines(text, *labels):
    keep = []
    for raw in (text or "").splitlines():
        line = _clean(raw)
        if any(re.match(rf"^{re.escape(lb)}\s*[：:]", line) for lb in labels):
            continue
        keep.append(raw)
    return "\n".join(keep).strip()


def parse_names(value, players):
    """从「玩家A、玩家B」这样的字符串里取出合法玩家名（去重、保序）。"""
    if not value:
        return []
    found = []
    tokens = [t.strip("「」『』\"'()（）[]【】。.") for t in _NAME_SPLIT_RE.split(value)]
    for t in tokens:
        if t in players and t not in found:
            found.append(t)
    if found:
        return found
    # 名字之间没有分隔符时，按出现位置匹配；长名字优先，避免「AI1」误匹配「AI10」
    spans = []
    for p in sorted(players, key=len, reverse=True):
        for m in re.finditer(re.escape(p), value):
            if not any(s <= m.start() < e for s, e, _ in spans):
                spans.append((m.start(), m.end(), p))
    for _, _, p in sorted(spans):
        if p not in found:
            found.append(p)
    return found


def parse_binary(text, label, yes, no):
    """解析「标签：yes/no」。返回 True / False，无法判断时返回 None。"""
    def decide(s, first_wins=False):
        s = s.replace("不" + yes, no)  # 「不同意」「不成功」视为否定
        iy, ino = s.find(yes), s.find(no)
        if iy >= 0 and ino < 0:
            return True
        if ino >= 0 and iy < 0:
            return False
        if first_wins and iy >= 0 and ino >= 0:
            return iy < ino  # 「出牌：成功（这轮不能失败）」以先出现的为准
        return None

    value = find_field(text, label)
    if value is not None:
        v = decide(value, first_wins=True)
        if v is not None:
            return v
    # 没有标签行时，看最后一行有效内容（结论通常写在最后）
    lines = [ln for ln in (_clean(x) for x in (text or "").splitlines()) if ln]
    return decide(lines[-1]) if lines else None


def clean_speech(text, player):
    """去掉模型自己加的「名字：」「发言：」之类前缀和包裹引号。"""
    text = strip_think(text)
    for prefix in (f"{player}：", f"{player}:", "发言：", "发言:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    if len(text) >= 2 and text[0] in "「“\"" and text[-1] in "」”\"":
        text = text[1:-1].strip()
    return text
