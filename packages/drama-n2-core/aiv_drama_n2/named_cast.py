"""O5-N named-cast scan + O1 auto-register helpers (BRIEF-AIV-017a / 020).

Rule-first extraction: dialogue speaker prefixes and high-confidence action
proper names. B-class (系统音 / 半截台词 / 动词短语 / 脏前缀) never opens CHAR.
Does not invent CHAR-* without writing cast. Isolated from koubo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Iterable

NAMED_CAST_PREFIX = "named_cast_"
NAMED_CAST_MISSING = "named_cast_missing"
NAMED_CAST_ROW_GAP = "named_cast_row_gap"
NAMED_CAST_UNREFERENCED = "named_cast_unreferenced"
NAMED_CAST_HEURISTIC = "named_cast_heuristic"
NAMED_CAST_AUTO_MERGED = "named_cast_auto_merged"
NAMED_CAST_SIDECAR_ADDED = "named_cast_sidecar_added"
NAMED_CAST_GATE = "named_cast_gate"

INFORMATIONAL_NAMED_CAST = frozenset({NAMED_CAST_AUTO_MERGED, NAMED_CAST_SIDECAR_ADDED})

NAMED_CAST_CHECK_MODES = ("off", "warn", "error")
DEFAULT_NAMED_CAST_CHECK = "warn"

AUTO_MERGE_ONE_LINE = "具名配角·自动挂表"
SIDECAR_ONE_LINE = "具名配角·侧车挂表"

CAST_CHANGED_HINT = {
    "code": "cast_changed",
    "message": "角色表已更新；G1b 仍锁定，大纲正文未改。请核对分镜 char_ids。",
}

G2_BLOCK_MESSAGE = "还有未入表的具名角色，无法通过分镜门审。"

SYSTEM_SPEAKERS = frozenset(
    {
        "系统音",
        "旁白",
        "广播",
        "弹窗字",
        "弹窗",
        "通缉令",
        "系统",
        "VO",
        "vo",
        "UI",
        "字幕",
        "画外音",
        "内心独白",
        "内心",
        "OS",
        "os",
    }
)

# Substring tags that mark a B-class speaker even when glued to a brand/token.
SYSTEM_CONTAINS_MARKERS = (
    "【系统音】",
    "[系统音]",
    "系统音",
    "画外音",
    "内心独白",
    "通缉令",
)
SYSTEM_PREFIX_MARKERS = ("旁白", "广播", "弹窗", "字幕")

GENERIC_REFS = frozenset(
    {
        "他",
        "她",
        "它",
        "他们",
        "她们",
        "两人",
        "二人",
        "众人",
        "大家",
        "有人",
        "某人",
        "路人",
        "群演",
        "群众",
        "我",
        "你",
        "您",
        "咱",
        "我们",
        "你们",
        "自己",
        "对方",
        "此人",
        "那人",
        "这人",
    }
)

TITLES = ("王子", "公主", "女王", "国王", "将军", "大人", "小姐", "少爷", "殿下")

BARE_TITLES = frozenset(
    {
        *TITLES,
        "老师",
        "老板",
    }
)


def _quantity_title_labels() -> frozenset[str]:
    """Collection labels for any title (两位将军 / 将军们). No episode proper names."""
    quantity = ("两位", "俩", "两名", "两", "两个", "双", "两大", "两侧", "两边", "双方", "两端")
    located = ("幕里", "幕外", "门外", "屏幕里", "画面里", "镜头里", "弹幕里", "双窗")
    labels: set[str] = set()
    for title in TITLES:
        labels.add(f"{title}们")
        for qty in quantity:
            labels.add(f"{qty}{title}")
        for loc in located:
            labels.add(f"{loc}两位{title}")
            labels.add(f"{loc}两{title}")
            labels.add(f"{loc}{title}")
    return frozenset(labels)


GROUP_LABELS = _quantity_title_labels()

# Unnamed title alone never opens CHAR; fold only onto an attached full name.
BARE_PRINCE_LABELS = frozenset(
    set(BARE_TITLES)
    | {f"那位{t}" for t in TITLES}
    | {f"这个{t}" for t in TITLES}
    | {f"那个{t}" for t in TITLES}
)

# Generic chrome / slogan stems. NAME slot only. Not one episode's proper names.
B_TAG_TITLE_PREFIXES = frozenset(
    {
        "弹窗",
        "双屏",
        "窗口",
        "爽点",
    }
)
# NAME slot only. Prose in one_line/outline is not classified.
B_TAG_EXACT = frozenset(
    {
        "默认助手",
        "爽点爆发",
        "神秘ID",
        "神秘ID消息",
    }
)
B_FRAG_EXACT = frozenset(
    {
        "倒计时开始",
    }
)
B_ACT_INFIX = ("吐槽", "端水", "争宠", "调侃", "嘲讽", "拆穿", "追杀")
B_TAG_EXACT_FOLDED = frozenset(item.casefold().replace(" ", "") for item in B_TAG_EXACT)
B_FRAG_EXACT_FOLDED = frozenset(item.casefold().replace(" ", "") for item in B_FRAG_EXACT)

VERB_LEADERS = (
    "指出",
    "看着",
    "走向",
    "走向了",
    "喊出",
    "拿出",
    "举起",
    "打开",
    "点击",
    "进入",
    "离开",
    "追向",
    "指向",
    "望向",
    "示意",
    "拦住",
    "抓住",
    "拉住",
    "推开",
    "吐槽",
    "端水",
    "争宠",
    "调侃",
    "嘲讽",
    "吐槽了",
    "拆穿",
    "追杀",
)

# Cut from questions/narration: 「你被双将军…？」 / 「不是追杀，而是两将军同时…」
HALF_LINE_STARTERS = (
    "你被",
    "我被",
    "他被",
    "她被",
    "而是",
    "不是",
    "但是",
    "只是",
    "就是",
    "还是",
    "因为",
    "所以",
    "如果",
    "虽然",
    "当众",
)
# Grammar/function chars that never start a real proper name before 王子/公主.
FRAGMENT_PREFIX_MARKERS = frozenset("被是而你我他她它咱这那把让给吗呢吧啊不没无的地得侧")

# Vague collection / compound-title prefixes (大纲「两大AI王国王子」抽词).
GENERIC_TITLE_PREFIXES = frozenset(
    {
        "王国",
        "ai",
        "双",
        "两",
        "两大",
        "人类",
        "机器",
        "虚拟",
        "数字",
        "所有",
        "各位",
        "一群",
        "一对",
        "两个",
        "两位",
        "两名",
        "俩",
        "两侧",
        "两边",
        "双方",
        "两端",
        "弹窗",
        "双屏",
        "窗口",
        "幕里",
        "幕外",
        "门外",
        "屏幕里",
        "画面里",
        "镜头里",
        "弹幕里",
        "双窗",
        "IDE里",
    }
)
GENERIC_LATIN_PREFIXES = frozenset({"ai", "npc", "ui", "os", "vo", "a.i", "a.i."})
GENERIC_TITLE_STARTS = (
    "两侧",
    "两边",
    "双方",
    "两端",
    "两个",
    "两位",
    "两名",
    "两大",
    "两",
    "双",
    "俩",
    "闭源",
    "开源",
    "幕里",
    "幕外",
    "门外",
    "屏幕里",
    "画面里",
    "镜头里",
    "弹幕里",
    "双窗",
    "IDE里",
    "弹窗",
    "双屏",
    "窗口",
    "王国",
)

# Speaker prefix: "预挂甲：" / "预挂乙:" (fullwidth or halfwidth colon).
SPEAKER_RE = re.compile(r"(?:^|[\n；;。！？!?])\s*([^：:\n]{1,32})[：:]")

# High-confidence titled proper names. CJK prefix capped at 4 so clause
# fragments never full-match as a CHAR name.
PROPER_NAME_RE = re.compile(
    r"(?:"
    r"[A-Za-z][A-Za-z0-9._-]*(?:\([^)]{1,32}\))?"
    r"|(?:(?![与和或把被让给在对从向到并的地得])[\u4e00-\u9fff])[\u4e00-\u9fff]{1,3}"
    r")"
    r"(?:王子|公主|女王|国王|将军|大人|小姐|少爷|殿下)"
)

_TITLE_ALT = "(?:王子|公主|女王|国王|将军|大人|小姐|少爷|殿下)"
GROUP_RE = re.compile("|".join(sorted((re.escape(g) for g in GROUP_LABELS), key=len, reverse=True)))
# Quantity + title (两位将军 / 两侧大人), never a CHAR slot.
GROUP_GENERIC_RE = re.compile(
    r"(?:幕里|幕外|门外|屏幕里|画面里|镜头里|弹幕里|双窗|IDE里)?"
    r"(?:两侧|两边|双方|两端|两位|两名|两个|两大|两|双|俩)(?:AI|王国)*"
    + _TITLE_ALT
)
# Located collection (屏幕里两位将军).
GROUP_LOCATED_RE = re.compile(
    r"(?:幕里|幕外|门外|屏幕里|画面里|镜头里|弹幕里|双窗|IDE里).{0,8}" + _TITLE_ALT
)

DIRTY_PREFIX_RE = re.compile(r"^[\s/\\|#@*>\-–—·•、,，.。;；'\"“”‘’\[\]【】()（）]+")
HALF_LINE_PUNCT_RE = re.compile(r"[,，。！？!?、;；…]|已启动|已冻结|倒计时|目标")
CLAUSE_MARKERS = (
    "当众",
    "拆穿",
    "反制",
    "同时",
    "伸出手",
)
CLAUSE_VERBS = (
    "拆穿",
    "反制",
    "当众",
    "指出",
    "看着",
    "走向",
    "挡住",
    "挡在",
    "站在",
    "出现",
    "现身",
    "追来",
    "怒吼",
    "破屏",
    "伸出",
    "打开",
    "进入",
    "离开",
    "吐槽",
    "端水",
    "争宠",
    "调侃",
    "嘲讽",
    "拆穿",
    "追杀",
)
CLAUSE_INFIX = frozenset("的地得和与或把被让给在对从向到并")

# No episode-riveted A-class recoveries. Fold only onto this episode's attached names.
PAREN_WRAP_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9._-]*)\s*[\(（]\s*([^)）]{1,40})\s*[\)）]"
    r"(?:(?P<title>王子|公主|女王|国王|将军|大人|小姐|少爷|殿下))?"
)
SYSTEM_SPAN_RE = re.compile(
    r"[/\\]?\s*[【\[]系统音[】\]][^。！？!?\n]*|系统音：[^\n。！？!?]*"
)
CONFRONTATION_MARKERS = ("对峙", "退兵", "嘴炮", "现身", "并肩", "破屏")

NONE_ID = "NONE"


def parse_named_cast_check(value: str | None) -> str:
    mode = (value or DEFAULT_NAMED_CAST_CHECK).strip().lower()
    return mode if mode in NAMED_CAST_CHECK_MODES else DEFAULT_NAMED_CAST_CHECK


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip())
    return " ".join(text.split())


def attached_names_from_rows(rows: Iterable[dict[str, Any]] | None) -> list[str]:
    """Fold targets: library-backed rows and clean existing names. Not B-class leftovers."""
    names: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = normalize_name(str(row.get("name") or ""))
        if not key:
            continue
        if row.get("library_ref"):
            if key not in names:
                names.append(key)
            continue
        if classify_char_banlist(key) != "ALLOW" or is_b_class(key):
            continue
        if key not in names:
            names.append(key)
    return names


def attached_names_from_cast(cast: dict[str, Any] | None) -> list[str]:
    if not isinstance(cast, dict):
        return []
    return attached_names_from_rows(cast.get("characters"))


def fold_to_attached_name(name: str, attached_names: Iterable[str] | None) -> str | None:
    """Fold generated name onto an attached full name.

    Match only: exact attached name, or that full name plus a prefix or a suffix.
    Do not force-fold unrelated names.
    """
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return None
    ordered = sorted(
        {normalize_name(n) for n in (attached_names or ()) if normalize_name(n)},
        key=len,
        reverse=True,
    )
    for full in ordered:
        if len(full) < 2:
            continue
        if key == full:
            return full
        if len(key) > len(full) and (key.startswith(full) or key.endswith(full)):
            return full
    return None


def is_attached_character_name(name: str, attached_names: Iterable[str] | None = None) -> bool:
    return fold_to_attached_name(name, attached_names) is not None


def strip_dirty_prefix(name: str) -> str:
    text = normalize_name(name)
    while True:
        stripped = DIRTY_PREFIX_RE.sub("", text).strip()
        if stripped == text:
            return stripped
        text = stripped


def _split_title(name: str) -> tuple[str, str] | None:
    key = strip_dirty_prefix(normalize_name(name))
    for title in TITLES:
        if key.endswith(title) and len(key) > len(title):
            return key[: -len(title)], title
    return None


def is_dialogue_fragment(name: str) -> bool:
    """Half-slice of a question/narration, not a registerable proper name."""
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return True
    if any(key.startswith(starter) for starter in HALF_LINE_STARTERS):
        return True
    split = _split_title(key)
    if not split:
        return False
    prefix, _title = split
    if any(prefix.startswith(starter) for starter in HALF_LINE_STARTERS):
        return True
    if any(ch in FRAGMENT_PREFIX_MARKERS for ch in prefix):
        return True
    return False


def is_generic_title(name: str) -> bool:
    """Vague collection / compound title (王国王子 / 两侧将军), not a true A-class slot."""
    key = strip_dirty_prefix(normalize_name(name))
    split = _split_title(key)
    if not split:
        return False
    prefix, _title = split
    folded = prefix.casefold().replace(" ", "")
    if folded in GENERIC_TITLE_PREFIXES or folded in GENERIC_LATIN_PREFIXES:
        return True
    if prefix in TITLES or prefix in BARE_TITLES:
        return True
    if any(prefix.startswith(p) or folded.startswith(p.casefold()) for p in GENERIC_TITLE_STARTS):
        return True
    return False


def _cjk_len(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def is_clause_fragment(name: str) -> bool:
    """Sentence / outline-continuation slice, not a registerable character name."""
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return True
    if any(marker in key for marker in CLAUSE_MARKERS):
        return True
    if any(verb in key for verb in CLAUSE_VERBS):
        return True
    split = _split_title(key)
    body = split[0] if split else key
    if any(ch in CLAUSE_INFIX for ch in body):
        return True
    if split and _cjk_len(body) > 4 and not re.search(r"[A-Za-z]", body):
        return True
    if not split and _cjk_len(key) > 6:
        return True
    return False


def is_half_line(name: str) -> bool:
    key = normalize_name(name)
    if not key:
        return True
    if is_dialogue_fragment(key) or is_clause_fragment(key):
        return True
    cleaned = strip_dirty_prefix(key)
    if (
        PROPER_NAME_RE.fullmatch(cleaned)
        and not is_generic_title(cleaned)
        and not is_dialogue_fragment(cleaned)
        and not is_clause_fragment(cleaned)
    ):
        return False
    if len(key) > 16:
        return True
    return bool(HALF_LINE_PUNCT_RE.search(key))


def is_verb_phrase(name: str) -> bool:
    key = strip_dirty_prefix(normalize_name(name))
    return any(key.startswith(v) for v in VERB_LEADERS)


def is_system_speaker(name: str) -> bool:
    key = normalize_name(name)
    if not key:
        return True
    if key in SYSTEM_SPEAKERS:
        return True
    lowered = key.lower()
    if lowered in {s.lower() for s in SYSTEM_SPEAKERS}:
        return True
    stripped = strip_dirty_prefix(key)
    if stripped in SYSTEM_SPEAKERS or stripped.lower() in {s.lower() for s in SYSTEM_SPEAKERS}:
        return True
    haystack = key.replace(" ", "")
    if any(marker in haystack for marker in SYSTEM_CONTAINS_MARKERS):
        return True
    if any(stripped.startswith(marker) or key.startswith(marker) for marker in SYSTEM_PREFIX_MARKERS):
        return True
    return False


def is_generic_ref(name: str) -> bool:
    return normalize_name(name) in GENERIC_REFS or strip_dirty_prefix(name) in GENERIC_REFS


def is_group_label(name: str) -> bool:
    key = normalize_name(name)
    stripped = strip_dirty_prefix(key)
    if key in GROUP_LABELS or stripped in GROUP_LABELS:
        return True
    if GROUP_GENERIC_RE.fullmatch(key) or GROUP_GENERIC_RE.fullmatch(stripped):
        return True
    if GROUP_LOCATED_RE.fullmatch(key) or GROUP_LOCATED_RE.fullmatch(stripped):
        return True
    return False


def is_protected_lead(name: str, attached_names: Iterable[str] | None = None) -> bool:
    """True only when name folds onto this episode's attached character card."""
    return is_attached_character_name(name, attached_names)


def is_a_tier_prince_name(name: str, attached_names: Iterable[str] | None = None) -> bool:
    """No hardcoded prince allowlist. Attached card names win via fold."""
    return is_attached_character_name(name, attached_names)


def _folded_token(name: str) -> str:
    return strip_dirty_prefix(normalize_name(name)).casefold().replace(" ", "")


def is_bare_prince_label(name: str) -> bool:
    """Unnamed bare title — fold onto attached titled cards, never a new CHAR."""
    return strip_dirty_prefix(normalize_name(name)) in BARE_PRINCE_LABELS or strip_dirty_prefix(
        normalize_name(name)
    ) in BARE_TITLES


def is_short_prince_near_deny(name: str) -> bool:
    return False


def is_b_act(name: str) -> bool:
    """B-ACT: sentence-level action phrase pretending to be a CHAR name."""
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return False
    if is_verb_phrase(key):
        return True
    if any(verb in key for verb in B_ACT_INFIX):
        return True
    return False


def is_b_tag(name: str) -> bool:
    """B-TAG: 爽点/设定 tag. NAME slot only — not one_line/outline prose."""
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return False
    folded = _folded_token(key)
    if folded in B_TAG_EXACT_FOLDED or key in B_TAG_EXACT:
        return True
    split = _split_title(key)
    if not split:
        return False
    prefix, _title = split
    folded_prefix = prefix.casefold().replace(" ", "")
    if folded_prefix in B_TAG_TITLE_PREFIXES or prefix in B_TAG_TITLE_PREFIXES:
        return True
    if any(stem in prefix for stem in B_TAG_TITLE_PREFIXES):
        return True
    return False


def is_b_gen(name: str) -> bool:
    """B-GEN: collection generics (两位/两侧 + title) and bare titles."""
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return False
    if is_bare_prince_label(key):
        return True
    if is_group_label(key) or is_generic_title(key):
        return True
    if GROUP_LOCATED_RE.search(key) or GROUP_GENERIC_RE.search(key):
        return True
    return False


def is_b_frag(name: str) -> bool:
    """B-FRAG: half-line dialogue / outline continuation / system-vo slice."""
    key = strip_dirty_prefix(normalize_name(name))
    if key in B_FRAG_EXACT or _folded_token(key) in B_FRAG_EXACT_FOLDED:
        return True
    return is_dialogue_fragment(name) or is_clause_fragment(name) or is_half_line(name)


def classify_char_banlist(name: str, attached_names: Iterable[str] | None = None) -> str:
    """ALLOW or B-ACT / B-TAG / B-FRAG / B-GEN.

    Hard scan is the CHAR **name** slot (open / merge / sidecar) only.
    Attached card names (and prefix/suffix wraps) are ALLOW and must not be dropped.
    """
    key = strip_dirty_prefix(normalize_name(name))
    if is_attached_character_name(key, attached_names):
        return "ALLOW"
    if is_b_act(key):
        return "B-ACT"
    if is_b_tag(key):
        return "B-TAG"
    if is_b_gen(key):
        return "B-GEN"
    if is_b_frag(key):
        return "B-FRAG"
    if is_b_class(key, attached_names=attached_names):
        return "B-FRAG"
    return "ALLOW"


def is_banlist_name(name: str, attached_names: Iterable[str] | None = None) -> bool:
    """True when named_cast must not open a CHAR row."""
    return classify_char_banlist(name, attached_names) != "ALLOW"


def is_b_class(name: str, attached_names: Iterable[str] | None = None) -> bool:
    """System-vo / popup / VO / half-line / verb leftover.

    CHAR-only. SCENE materialize must call is_scene_b_class.
    A row already attached is never B-class.
    """
    if is_attached_character_name(name, attached_names):
        return False
    if is_system_speaker(name) or is_generic_ref(name):
        return True
    if is_b_act(name) or is_b_tag(name) or is_b_gen(name):
        return True
    if is_group_label(name) or is_generic_title(name):
        return True
    if is_clause_fragment(name) or is_dialogue_fragment(name) or is_verb_phrase(name) or is_half_line(name):
        return True
    stripped = strip_dirty_prefix(name)
    if stripped != normalize_name(name) and (
        is_system_speaker(stripped)
        or is_group_label(stripped)
        or is_generic_title(stripped)
        or is_clause_fragment(stripped)
        or is_dialogue_fragment(stripped)
        or is_verb_phrase(stripped)
        or is_half_line(stripped)
        or is_b_act(stripped)
        or is_b_tag(stripped)
        or is_b_gen(stripped)
    ):
        return True
    return False


# Spatial SCENE short names. Events belong in one_line, not name.
# No episode-riveted aliases; generic 时刻→空间 / 入口→门厅 stems stay below.
SCENE_SPATIAL_ALIASES: dict[str, str] = {}
SCENE_SPATIAL_TOKENS = (
    "门厅",
    "工位",
    "战场",
    "营帐",
    "校场",
    "茶水间",
    "城墙",
    "办公室",
    "空间",
    "审判庭",
    "法庭",
    "大厅",
    "走廊",
    "内廊",
    "外廊",
    "房间",
)

# 弹窗审判庭 family: chrome prefix + place ending. Bare 弹窗 / 弹窗字 stay chrome.
SCENE_PLACE_ENDINGS = (
    "空间",
    "门厅",
    "战场",
    "审判庭",
    "法庭",
    "大厅",
    "走廊",
    "内廊",
    "外廊",
    "房间",
    "营帐",
    "校场",
    "茶水间",
    "办公室",
    "工位",
    "城墙",
    "庭",
    "厅",
    "室",
    "廊",
    "场",
    "间",
)
POPUP_CHROME_TAILS = frozenset({"", "字", "系统", "系统音", "音", "字幕", *TITLES})


def _has_spatial_token(text: str) -> bool:
    lowered = text.casefold()
    for tok in SCENE_SPATIAL_TOKENS:
        if tok.isascii() and tok.casefold() in lowered:
            return True
        if not tok.isascii() and tok in text:
            return True
    return False


def prefer_spatial_scene_name(name: str) -> str:
    """Generate-side spatial short name. Event 时刻→空间, 入口→门厅. No episode aliases."""
    key = normalize_name(name)
    if not key:
        return key
    if key in SCENE_SPATIAL_ALIASES:
        return SCENE_SPATIAL_ALIASES[key]
    if key.endswith("时刻") and _cjk_len(key) >= 4:
        stem = key[: -len("时刻")]
        if _has_spatial_token(stem) or _cjk_len(stem) >= 2:
            return stem if stem.endswith("空间") else f"{stem}空间"
    if key.endswith("入口") and _cjk_len(key) >= 4:
        stem = key[: -len("入口")]
        if not stem:
            return key
        if stem.endswith("门厅") or stem.endswith("厅"):
            return stem
        return f"{stem}门厅"
    return key


def _popup_prefixed_place(key: str) -> bool:
    """弹窗审判庭 is a place. Bare 弹窗 / 弹窗字 / 弹窗+title stay VO/CHAR chrome."""
    if not key.startswith("弹窗"):
        return False
    rest = key[len("弹窗") :]
    if rest in POPUP_CHROME_TAILS or any(rest.endswith(title) for title in TITLES):
        return False
    lowered = rest.casefold()
    for tok in SCENE_SPATIAL_TOKENS:
        if tok.isascii() and tok.casefold() in lowered:
            return True
        if not tok.isascii() and tok in rest:
            return True
    return any(rest.endswith(end) for end in SCENE_PLACE_ENDINGS)


def is_spatial_scene_name(name: str) -> bool:
    key = normalize_name(name)
    if not key:
        return False
    if key in SCENE_SPATIAL_ALIASES or prefer_spatial_scene_name(key) != key:
        return True
    lowered = key.casefold()
    for tok in SCENE_SPATIAL_TOKENS:
        if tok.isascii() and tok.casefold() in lowered:
            return True
        if not tok.isascii() and tok in key:
            return True
    if _popup_prefixed_place(key):
        return True
    return False


def is_scene_b_class(name: str) -> bool:
    """SCENE skip bucket — must not reuse CHAR clause/开源/length punches.

    Spatial place names (…空间 / …门厅 / …战场 / …审判庭 and SCENE_SPATIAL_TOKENS)
    pass through first so a system-speaker substring (弹窗空间 / 弹窗审判庭)
    does not skip the SCENE card. Bare 弹窗 / 系统音 and CHAR dirt still skip.
    """
    key = strip_dirty_prefix(normalize_name(name))
    if not key:
        return True
    if is_spatial_scene_name(key):
        return False
    if is_system_speaker(key) or is_generic_ref(key):
        return True
    if is_group_label(key) or is_banlist_name(key):
        return True
    if HALF_LINE_PUNCT_RE.search(key) and (_cjk_len(key) > 12 or any(t in key for t in TITLES)):
        return True
    if _cjk_len(key) > 16:
        return True
    return False


def _brand_key(name: str) -> str:
    text = strip_dirty_prefix(normalize_name(name)).casefold()
    return re.sub(r"[.\s_-]", "", text)


def is_bare_brand(_name: str) -> bool:
    """No episode brand list. Bare tokens are not force-folded."""
    return False


def brand_family(_name: str) -> frozenset[str] | None:
    return None


def is_registerable_name(name: str, attached_names: Iterable[str] | None = None) -> bool:
    key = strip_dirty_prefix(name)
    if not key or len(key) < 2:
        return False
    if is_attached_character_name(key, attached_names):
        return True
    if is_banlist_name(key, attached_names) or is_b_class(name, attached_names) or is_b_class(key, attached_names):
        return False
    if key in BARE_TITLES:
        return False
    if key.upper() in {NONE_ID, "CHAR", "SCENE"}:
        return False
    if key.startswith("CHAR-") or key.startswith("SCENE-"):
        return False
    return True


def fold_brand_to_canonical(_name: str) -> str | None:
    """Removed: no canonical episode prince/brand slot."""
    return None


def prefer_paren_entity(outer: str, inner: str, trailing_title: str | None = None) -> str:
    """One entity from A（B） / A(B)title — never two CHAR rows."""
    outer_n = normalize_name(outer)
    inner_n = normalize_name(inner)
    title = trailing_title or ""
    if title:
        composed = f"{outer_n}({inner_n}){title}"
        if is_registerable_name(composed):
            return composed
        inner_titled = inner_n if any(inner_n.endswith(t) for t in TITLES) else f"{inner_n}{title}"
        if is_registerable_name(inner_titled):
            return inner_titled
    if is_registerable_name(inner_n):
        return inner_n
    if is_registerable_name(outer_n):
        return outer_n
    if title and outer_n:
        return f"{outer_n}({inner_n}){title}"
    return inner_n or outer_n


def _is_brand_or_titled_wrap(outer: str, inner: str, trailing_title: str | None) -> bool:
    if trailing_title:
        return True
    inner_n = normalize_name(inner)
    outer_n = normalize_name(outer)
    return is_registerable_name(inner_n) or is_registerable_name(outer_n)


def glue_paren_name(name: str) -> str:
    """Speaker/hit `甲（乙将军）` → one titled name."""
    text = normalize_name(name)
    if not text:
        return text
    match = PAREN_WRAP_RE.search(text)
    if not match or match.start() != 0:
        return text
    if text[match.end() :].strip():
        return text
    if not _is_brand_or_titled_wrap(match.group(1), match.group(2), match.group("title")):
        return text
    return prefer_paren_entity(match.group(1), match.group(2), match.group("title")) or text


def extract_paren_entities(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for match in PAREN_WRAP_RE.finditer(text or ""):
        if not _is_brand_or_titled_wrap(match.group(1), match.group(2), match.group("title")):
            continue
        entity = prefer_paren_entity(match.group(1), match.group(2), match.group("title"))
        if entity and entity not in seen:
            seen.add(entity)
            hits.append(entity)
    return hits


def strip_system_spans(text: str) -> str:
    return SYSTEM_SPAN_RE.sub(" ", text or "")


def extract_bare_brands(_text: str) -> list[str]:
    """No episode brand tokens."""
    return []


def fold_brand_to_pool(name: str, pool: Iterable[str]) -> str | None:
    """Fold onto an attached/pool full name plus prefix or suffix only."""
    return fold_to_attached_name(name, pool)


def extract_speakers(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for match in SPEAKER_RE.finditer(text or ""):
        name = glue_paren_name(normalize_name(match.group(1)))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    return hits


def extract_proper_names(text: str) -> list[str]:
    body = text or ""
    hits: list[str] = []
    seen: set[str] = set()
    covered: list[tuple[int, int]] = []

    def _add(name: str) -> None:
        key = glue_paren_name(normalize_name(name))
        if key and key not in seen and is_registerable_name(key):
            seen.add(key)
            hits.append(key)

    for match in PAREN_WRAP_RE.finditer(body):
        if not _is_brand_or_titled_wrap(match.group(1), match.group(2), match.group("title")):
            continue
        covered.append((match.start(), match.end()))
        _add(prefer_paren_entity(match.group(1), match.group(2), match.group("title")))

    for match in PROPER_NAME_RE.finditer(body):
        start, end = match.start(), match.end()
        if any(start < e and end > s for s, e in covered):
            continue
        name = normalize_name(match.group(0))
        if not name or name in seen:
            continue
        if not is_registerable_name(name):
            continue
        seen.add(name)
        hits.append(name)
    return hits


def extract_group_labels(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    body = text or ""
    for match in GROUP_RE.finditer(body):
        name = normalize_name(match.group(0))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    for match in GROUP_GENERIC_RE.finditer(body):
        name = normalize_name(match.group(0))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    for match in GROUP_LOCATED_RE.finditer(body):
        name = normalize_name(match.group(0))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    return hits


def names_mentioned(text: str, pool: Iterable[str]) -> list[str]:
    """Longest-first substring hits so a full attached name wins over a bare title."""
    body = text or ""
    if not body:
        return []
    ordered = sorted({normalize_name(n) for n in pool if normalize_name(n)}, key=len, reverse=True)
    covered: list[tuple[int, int]] = []
    hits: list[str] = []
    for name in ordered:
        start = 0
        while True:
            idx = body.find(name, start)
            if idx < 0:
                break
            end = idx + len(name)
            if any(idx >= s and end <= e for s, e in covered):
                start = idx + 1
                continue
            covered.append((idx, end))
            if name not in hits:
                hits.append(name)
            start = end
    return hits


def expand_group(label: str, individual_names: Iterable[str]) -> list[str]:
    key = normalize_name(label)
    members: list[str] = []
    needle = next((title for title in TITLES if title in key), None)
    if not needle:
        return []
    attached = list(individual_names)
    for name in attached:
        norm = normalize_name(name)
        if not is_registerable_name(norm, attached):
            continue
        if needle in norm and not is_group_label(norm):
            if norm not in members:
                members.append(norm)
    return members


def _title_core(name: str) -> str:
    text = strip_dirty_prefix(normalize_name(name))
    text = re.sub(r"[【】\[\]/]", "", text)
    for title in TITLES:
        if text.endswith(title):
            text = text[: -len(title)]
            break
    text = re.sub(r"[()（）.\s_-]", "", text)
    return text.casefold()


def names_are_aliases(left: str, right: str) -> bool:
    """True only when one name is the other, or the other plus a prefix/suffix."""
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return fold_to_attached_name(a, [b]) is not None or fold_to_attached_name(b, [a]) is not None


def prefer_name(left: str, right: str) -> str:
    a = normalize_name(left)
    b = normalize_name(right)
    a_titled = any(a.endswith(t) for t in TITLES)
    b_titled = any(b.endswith(t) for t in TITLES)
    if a_titled and not b_titled:
        return a
    if b_titled and not a_titled:
        return b
    if a_titled and b_titled:
        return a
    if ("(" in a or "（" in a) and "(" not in b and "（" not in b:
        return a
    if ("(" in b or "（" in b) and "(" not in a and "（" not in a:
        return b
    return a if len(a) >= len(b) else b


def fold_needed(names: Iterable[str]) -> list[str]:
    out: list[str] = []
    for raw in names:
        name = normalize_name(raw)
        if not is_registerable_name(name):
            continue
        replaced = False
        for idx, existing in enumerate(out):
            if names_are_aliases(name, existing):
                out[idx] = prefer_name(existing, name)
                replaced = True
                break
        if not replaced:
            out.append(name)
    return out


def resolve_to_pool_name(name: str, pool: Iterable[str]) -> str | None:
    key = glue_paren_name(normalize_name(name))
    cleaned = glue_paren_name(strip_dirty_prefix(key))
    ordered = [normalize_name(p) for p in pool if normalize_name(p)]
    if key in ordered:
        return key
    if cleaned in ordered:
        return cleaned
    folded = fold_to_attached_name(cleaned, ordered) or fold_to_attached_name(key, ordered)
    if folded:
        return folded
    if is_bare_prince_label(cleaned) or is_bare_prince_label(key):
        members = expand_group(cleaned or key, ordered)
        return members[0] if len(members) == 1 else None
    if is_b_class(key, ordered) and not is_group_label(key):
        return None
    if not is_registerable_name(key, ordered) and cleaned not in ordered:
        return None
    if is_registerable_name(cleaned, ordered):
        return cleaned
    return None


def _corpus_from_rows(rows: list[dict[str, Any]], outline_body: str | None) -> str:
    parts = [outline_body or ""]
    for row in rows:
        action, dialogue, _ = _row_prose(row)
        parts.append(action)
        parts.append(dialogue)
    return "\n".join(parts)


def infer_a_class_names(
    rows: list[dict[str, Any]],
    *,
    outline_body: str | None = None,
    attached_names: Iterable[str] | None = None,
) -> list[str]:
    """Proper names from outline + shots. Fold onto attached cards only."""
    outline_names = extract_proper_names(outline_body or "")
    shot_text = "\n".join(_row_prose(row)[2] for row in rows)
    shot_names = extract_proper_names(shot_text)
    names = fold_needed([*outline_names, *shot_names])
    attached = list(attached_names or ())
    folded: list[str] = []
    for name in names:
        hit = fold_to_attached_name(name, attached) or name
        if hit not in folded:
            folded.append(hit)
    return folded


def _cast_name_index(cast: dict[str, Any] | None) -> tuple[dict[str, str], dict[str, str]]:
    """Return (norm_name→id, id→norm_name) for characters."""
    by_name: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for row in (cast or {}).get("characters") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        cid = str(row["id"])
        name = normalize_name(str(row.get("name") or ""))
        if name and name not in by_name:
            by_name[name] = cid
        by_id[cid] = name
    return by_name, by_id


def _row_prose(row: dict[str, Any]) -> tuple[str, str, str]:
    action = str(row.get("action") or "")
    dialogue = str(row.get("dialogue") or "")
    return action, dialogue, f"{action}\n{dialogue}"


def collect_named_hits(
    rows: list[dict[str, Any]],
    *,
    cast: dict[str, Any] | None = None,
    outline_body: str | None = None,
) -> list[dict[str, Any]]:
    """High-confidence A-tier named on-screen roles per shot.

    Each hit: {name, shot_id, fields, kind: speaker|action|group, registerable: bool}
    """
    by_name, _ = _cast_name_index(cast)
    attached = attached_names_from_cast(cast)
    pool: set[str] = set(by_name)
    pool.update(infer_a_class_names(rows, outline_body=outline_body, attached_names=attached))

    for row in rows:
        action, dialogue, _ = _row_prose(row)
        for name in extract_speakers(dialogue) + extract_speakers(action):
            if is_b_class(name, attached) and not is_attached_character_name(name, attached):
                continue
            if is_registerable_name(name, attached):
                folded = fold_to_attached_name(name, attached)
                pool.add(folded or strip_dirty_prefix(name) or name)
            else:
                folded = fold_to_attached_name(name, attached) or fold_to_attached_name(name, pool)
                if folded:
                    pool.add(folded)
        pool.update(extract_proper_names(action))
        pool.update(extract_proper_names(dialogue))

    hits: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        shot_id = row.get("shot_id") or f"S{idx + 1:02d}"
        action, dialogue, combined = _row_prose(row)
        fields: set[str] = set()
        names: dict[str, str] = {}

        for name in extract_speakers(dialogue):
            if is_system_speaker(name) or is_generic_ref(name):
                continue
            if is_b_class(name, attached) and not is_group_label(name) and not is_attached_character_name(name, attached):
                continue
            cleaned = glue_paren_name(strip_dirty_prefix(name) or name)
            names[cleaned] = "group" if is_group_label(cleaned) else "speaker"
            fields.add("dialogue")
        for name in extract_speakers(action):
            if is_system_speaker(name) or is_generic_ref(name):
                continue
            if is_b_class(name, attached) and not is_group_label(name) and not is_attached_character_name(name, attached):
                continue
            cleaned = glue_paren_name(strip_dirty_prefix(name) or name)
            names.setdefault(cleaned, "group" if is_group_label(cleaned) else "speaker")
            fields.add("action")

        for name in names_mentioned(combined, pool):
            if is_b_class(name, attached) and not is_group_label(name) and not is_attached_character_name(name, attached):
                continue
            if name in names:
                continue
            names[name] = "group" if is_group_label(name) else "action"
            if name in action:
                fields.add("action")
            if name in dialogue:
                fields.add("dialogue")

        for name in extract_group_labels(combined):
            names.setdefault(name, "group")
            if name in action:
                fields.add("action")
            if name in dialogue:
                fields.add("dialogue")

        field_list = sorted(fields) or ["action"]
        for name, kind in names.items():
            hits.append(
                {
                    "name": name,
                    "shot_id": shot_id,
                    "fields": field_list,
                    "kind": kind,
                    "registerable": is_registerable_name(name, attached),
                }
            )
    return hits


def resolve_hit_names(name: str, individual_pool: Iterable[str]) -> list[str]:
    glued = glue_paren_name(name)
    pool = list(individual_pool)
    if is_bare_prince_label(glued) or is_group_label(glued) or is_generic_title(glued):
        return expand_group(glued, pool)
    target = resolve_to_pool_name(glued, pool)
    if target:
        return [target]
    if is_registerable_name(glued, pool):
        return [strip_dirty_prefix(glued) or normalize_name(glued)]
    folded = fold_to_attached_name(glued, pool)
    if folded:
        return [folded]
    return []


def blocking_named_cast_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in issues:
        code = str(item.get("code") or "")
        if not code.startswith(NAMED_CAST_PREFIX):
            continue
        if code in INFORMATIONAL_NAMED_CAST:
            continue
        out.append(item)
    return out


def named_cast_issue_severity(mode: str) -> str:
    return "error" if mode == "error" else "warn"


def observational_named_cast_issues(
    hint: dict[str, Any] | None,
    *,
    issue_fn: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist-visible warn for sidecar / auto-merge (F3; generate/GET/validate)."""
    if not hint:
        return []
    source = str(hint.get("source") or "auto_merge")
    if source == "sidecar":
        code = NAMED_CAST_SIDECAR_ADDED
        message = "sidecar added named cast; G1b still locked; outline unchanged"
    else:
        code = NAMED_CAST_AUTO_MERGED
        message = "named on-screen roles auto-registered into cast"
    return [
        issue_fn(
            "warn",
            code,
            message,
            added=list(hint.get("added") or []),
            source=source,
            cast_version=hint.get("cast_version"),
            cast_version_old=hint.get("cast_version_old"),
            cast_version_new=hint.get("cast_version_new"),
            g1b_still_locked=True,
            outline_unchanged=True,
        )
    ]


def collect_named_cast_issues(
    rows: list[dict[str, Any]],
    *,
    cast: dict[str, Any] | None,
    outline_body: str | None = None,
    named_cast_check: str | None = None,
    issue_fn: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    mode = parse_named_cast_check(named_cast_check)
    if mode == "off":
        return []
    severity = named_cast_issue_severity(mode)
    by_name, _ = _cast_name_index(cast)
    attached = attached_names_from_cast(cast)
    hits = collect_named_hits(rows, cast=cast, outline_body=outline_body)
    a_class = infer_a_class_names(rows, outline_body=outline_body, attached_names=attached)
    individual_pool = set(by_name) | {h["name"] for h in hits if h.get("registerable")} | set(a_class)

    issues: list[dict[str, Any]] = []
    referenced_ids: set[str] = set()
    seen_missing: set[tuple[str, str]] = set()
    seen_gap: set[tuple[str, str]] = set()
    mentioned_unresolved: dict[str, list[str]] = {}

    for row in rows:
        for cid in row.get("char_ids") or []:
            if cid and cid != NONE_ID:
                referenced_ids.add(str(cid))

    for hit in hits:
        resolved = resolve_hit_names(hit["name"], individual_pool)
        shot_id = hit["shot_id"]
        row = next((r for r in rows if r.get("shot_id") == shot_id), None)
        char_ids = [str(c) for c in ((row or {}).get("char_ids") or []) if str(c) != NONE_ID]

        if not resolved:
            if is_b_class(hit["name"], attached) or is_group_label(hit["name"]):
                continue
            key = (shot_id, hit["name"])
            if key not in seen_missing:
                seen_missing.add(key)
                issues.append(
                    issue_fn(
                        severity,
                        NAMED_CAST_MISSING,
                        "named on-screen role is not in cast",
                        shot_id=shot_id,
                        field="dialogue" if "dialogue" in hit["fields"] else "action",
                        role_name=hit["name"],
                        source_fields=hit["fields"],
                        tier="A",
                    )
                )
            continue

        for name in resolved:
            cid = by_name.get(name)
            if not cid:
                key = (shot_id, name)
                if key not in seen_missing:
                    seen_missing.add(key)
                    issues.append(
                        issue_fn(
                            severity,
                            NAMED_CAST_MISSING,
                            "named on-screen role is not in cast",
                            shot_id=shot_id,
                            field="dialogue" if "dialogue" in hit["fields"] else "action",
                            role_name=name,
                            source_fields=hit["fields"],
                            tier="A",
                        )
                    )
                mentioned_unresolved.setdefault(name, []).append(shot_id)
                continue
            if cid not in char_ids:
                key = (shot_id, cid)
                if key not in seen_gap:
                    seen_gap.add(key)
                    issues.append(
                        issue_fn(
                            severity,
                            NAMED_CAST_ROW_GAP,
                            "named on-screen role is in cast but missing from this shot char_ids",
                            shot_id=shot_id,
                            field="char_ids",
                            role_name=name,
                            matched_cast_id=cid,
                            source_fields=hit["fields"],
                            tier="A",
                        )
                    )
            mentioned_unresolved.setdefault(name, []).append(shot_id)

    seen_unref: set[str] = set()
    for name, shot_ids in mentioned_unresolved.items():
        cid = by_name.get(name)
        if not cid or cid in referenced_ids:
            continue
        if cid in seen_unref:
            continue
        seen_unref.add(cid)
        issues.append(
            issue_fn(
                severity,
                NAMED_CAST_UNREFERENCED,
                "named on-screen role is in cast but never referenced in char_ids",
                field="char_ids",
                role_name=name,
                matched_cast_id=cid,
                shot_ids=list(dict.fromkeys(shot_ids)),
                tier="A",
            )
        )
    return issues


def apply_char_id_wiring(rows: list[dict[str, Any]], name_to_id: dict[str, str]) -> list[dict[str, Any]]:
    """Add CHAR ids onto shots where the name speaks/appears. Drops NONE when named."""
    if not name_to_id:
        return rows
    pool = list(name_to_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        action, dialogue, combined = _row_prose(row)
        mentioned: set[str] = set()
        cleaned = strip_system_spans(combined)
        for name in names_mentioned(combined, pool):
            target = resolve_to_pool_name(name, pool)
            if target:
                mentioned.add(target)
        for name in extract_speakers(dialogue) + extract_speakers(action):
            if is_group_label(name) or is_generic_title(name):
                mentioned.update(expand_group(name, pool))
                continue
            if is_b_class(name, pool) and not is_attached_character_name(name, pool):
                continue
            target = resolve_to_pool_name(name, pool)
            if target:
                mentioned.add(target)
        for name in extract_proper_names(combined):
            target = resolve_to_pool_name(name, pool)
            if target:
                mentioned.add(target)
        for token in extract_bare_brands(cleaned):
            target = resolve_to_pool_name(token, pool)
            if target:
                mentioned.add(target)
        for label in extract_group_labels(combined):
            mentioned.update(expand_group(label, pool))
        add_ids = [name_to_id[n] for n in mentioned if n in name_to_id]
        if not add_ids:
            out.append(updated)
            continue
        current = [str(c) for c in (updated.get("char_ids") or [])]
        current = [c for c in current if c and c != NONE_ID]
        for cid in add_ids:
            if cid not in current:
                current.append(cid)
        updated["char_ids"] = current or [NONE_ID]
        out.append(updated)
    return out


def _is_dirty_cast_name(name: str, attached_names: Iterable[str] | None = None) -> bool:
    if is_attached_character_name(name, attached_names):
        return False
    return (
        is_banlist_name(name, attached_names)
        or is_dialogue_fragment(name)
        or is_clause_fragment(name)
        or is_generic_title(name)
        or is_group_label(name)
        or is_system_speaker(name)
        or is_verb_phrase(name)
    )


def _is_titled_cast_name(name: str) -> bool:
    key = normalize_name(name)
    if not is_registerable_name(key):
        return False
    return any(key.endswith(title) for title in TITLES)


def prune_dirty_cast_characters(cast: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Merge-time reject: drop B-class CHAR rows. Never drop attached/library rows."""
    if not isinstance(cast, dict):
        return []
    chars = list(cast.get("characters") or [])
    attached = attached_names_from_rows(chars)
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for row in chars:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if (
            row.get("library_ref")
            or is_attached_character_name(name, attached)
            or is_registerable_name(name, attached)
        ):
            kept.append(row)
            continue
        removed.append({"id": row.get("id"), "name": name})
    if removed:
        cast["characters"] = kept
        cast["version"] = (cast.get("version") or 0) + 1
    return removed


def _shot_group_signal(row: dict[str, Any]) -> bool:
    """True when a shot mentions a collection label or confrontation after stripping VO."""
    _action, _dialogue, combined = _row_prose(row)
    cleaned = strip_system_spans(combined)
    if not cleaned.strip():
        return False
    if extract_group_labels(cleaned):
        return True
    if any(marker in cleaned for marker in CONFRONTATION_MARKERS):
        return True
    return False


def hang_orphan_princes(
    rows: list[dict[str, Any]],
    cast: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Unused attached/titled cast rows hang onto group-label shots."""
    by_name, _ = _cast_name_index(cast)
    attached = attached_names_from_cast(cast)
    titled_ids = [
        cid
        for name, cid in by_name.items()
        if _is_titled_cast_name(name) or is_attached_character_name(name, attached)
    ]
    if not titled_ids:
        return rows
    appearance = {cid: 0 for cid in titled_ids}
    for row in rows:
        for cid in row.get("char_ids") or []:
            ident = str(cid)
            if ident in appearance:
                appearance[ident] += 1
    orphans = [cid for cid, count in appearance.items() if count == 0]
    if not orphans:
        return rows
    signal_idxs = [idx for idx, row in enumerate(rows) if _shot_group_signal(row)]
    if not signal_idxs:
        return rows
    out = [dict(row) for row in rows]
    for idx in signal_idxs:
        current = [str(c) for c in (out[idx].get("char_ids") or []) if c and str(c) != NONE_ID]
        for cid in orphans:
            if cid not in current:
                current.append(cid)
        out[idx]["char_ids"] = current or [NONE_ID]
    return out


def prune_dirty_char_ids(rows: list[dict[str, Any]], cast: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Drop half-line / generic-title ids from shots. Keep attached rows."""
    attached = attached_names_from_cast(cast)
    by_id = {
        str(row["id"]): str(row.get("name") or "")
        for row in ((cast or {}).get("characters") or [])
        if isinstance(row, dict) and row.get("id")
    }
    lib_ids = {
        str(row["id"])
        for row in ((cast or {}).get("characters") or [])
        if isinstance(row, dict) and row.get("id") and row.get("library_ref")
    }
    out: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        kept: list[str] = []
        for cid in updated.get("char_ids") or []:
            ident = str(cid)
            if not ident or ident == NONE_ID:
                continue
            name = by_id.get(ident) or ident
            if ident in lib_ids or is_attached_character_name(name, attached):
                if ident not in kept:
                    kept.append(ident)
                continue
            if _is_dirty_cast_name(name, attached) or _is_dirty_cast_name(ident, attached):
                continue
            if ident not in kept:
                kept.append(ident)
        updated["char_ids"] = kept or [NONE_ID]
        out.append(updated)
    return out


def _existing_canonical(by_name: dict[str, str]) -> dict[str, str]:
    """canonical core → existing cast name."""
    out: dict[str, str] = {}
    for name in by_name:
        out.setdefault(_title_core(name) or normalize_name(name).casefold(), name)
    return out


def auto_merge_named_cast(
    rec: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    alloc_char: Callable[[dict[str, Any]], str],
    one_line: str = AUTO_MERGE_ONE_LINE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """O1=A: register missing high-confidence names; wire char_ids.

    Mutates rec['cast']['characters'] and bumps cast.version when rows are added.
    Never touches outline body / G1b lock flags.
    """
    cast = rec.get("cast")
    if not isinstance(cast, dict):
        return rows, []
    prune_dirty_cast_characters(cast)
    outline_body = (rec.get("outline") or {}).get("body_md")
    attached = attached_names_from_cast(cast)
    hits = collect_named_hits(rows, cast=cast, outline_body=outline_body)
    by_name, _ = _cast_name_index(cast)
    a_class = infer_a_class_names(rows, outline_body=outline_body, attached_names=attached)
    individual_pool = set(by_name) | {h["name"] for h in hits if h.get("registerable")} | set(a_class)

    needed: list[str] = []
    for name in a_class:
        target = resolve_to_pool_name(name, individual_pool) or fold_to_attached_name(name, attached)
        if target is None:
            target = name
        if fold_to_attached_name(target, attached):
            continue
        if target not in by_name and target not in needed and is_registerable_name(target, attached):
            needed.append(target)
    for hit in hits:
        for name in resolve_hit_names(hit["name"], individual_pool):
            target = resolve_to_pool_name(name, individual_pool) or fold_to_attached_name(name, attached)
            if target is None:
                target = name
            if fold_to_attached_name(target, attached):
                continue
            if target not in by_name and target not in needed and is_registerable_name(target, attached):
                needed.append(target)
    needed = fold_needed(needed)

    filtered: list[str] = []
    for name in needed:
        if fold_to_attached_name(name, attached) or fold_to_attached_name(name, by_name):
            continue
        filtered.append(name)
    needed = filtered

    added: list[dict[str, Any]] = []
    for name in needed:
        ident = alloc_char(rec)
        row = {
            "id": ident,
            "name": name,
            "one_line": one_line,
            "library_ref": None,
        }
        cast.setdefault("characters", []).append(row)
        by_name[name] = ident
        added.append({"id": ident, "name": name})

    if added:
        cast["version"] = (cast.get("version") or 0) + 1

    wired = apply_char_id_wiring(rows, by_name)
    wired = prune_dirty_char_ids(wired, cast)
    wired = hang_orphan_princes(wired, cast)
    return wired, added
