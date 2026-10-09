"""配置加载模块：读取项目根目录 config.yaml。"""
import os
import yaml

# 项目根目录（backend 的上一级）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
DATA_DIR = os.path.join(ROOT_DIR, "data")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
DB_PATH = os.path.join(DATA_DIR, "stockpilot.db")

os.makedirs(DATA_DIR, exist_ok=True)

_DEFAULT = {
    "ai": {"api_key": "", "base_url": "https://api.deepseek.com",
           "model": "deepseek-chat", "enabled": True},
    "server": {"host": "127.0.0.1", "port": 8000},
    "cache": {"quote_ttl": 3, "kline_ttl": 30, "news_ttl": 30},
    "discipline": {"chase_high_pct": 10, "stop_loss_pct": 8},
}


def load_config() -> dict:
    """加载配置，缺项用默认值补齐。环境变量优先于 config.yaml。"""
    cfg = dict(_DEFAULT)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            for k, v in user_cfg.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    merged = dict(cfg[k])
                    merged.update(v)
                    cfg[k] = merged
                else:
                    cfg[k] = v
        except Exception as e:  # noqa
            print(f"[config] 读取 config.yaml 失败，使用默认配置: {e}")
    # 环境变量覆盖（敏感信息推荐走环境变量，不落盘）
    ai = cfg.setdefault("ai", {})
    if os.environ.get("STOCKPILOT_AI_KEY"):
        ai["api_key"] = os.environ["STOCKPILOT_AI_KEY"]
    if os.environ.get("STOCKPILOT_AI_BASE_URL"):
        ai["base_url"] = os.environ["STOCKPILOT_AI_BASE_URL"]
    if os.environ.get("STOCKPILOT_AI_MODEL"):
        ai["model"] = os.environ["STOCKPILOT_AI_MODEL"]
    return cfg


CONFIG = load_config()


def _patch_yaml_ai(ai: dict):
    """只更新 config.yaml 中 ai 段的目标字段行，保留其余内容与注释。"""
    if not os.path.exists(CONFIG_PATH):
        # 文件不存在则整体写一份默认
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            import yaml as _y
            _y.safe_dump({"ai": ai}, f, allow_unicode=True, sort_keys=False)
        return
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    in_ai = False
    ai_indent = 0
    fields = {
        "api_key": str(ai.get("api_key", "")).replace('"', '\\"'),
        "base_url": str(ai.get("base_url", "")).replace('"', '\\"'),
        "model": str(ai.get("model", "")).replace('"', '\\"'),
        "enabled": "true" if ai.get("enabled", True) else "false",
    }
    target_keys = set(fields.keys())
    handled = set()
    for line in lines:
        stripped = line.strip()
        # 进入 ai 块：行首无缩进（或仅空白）且以 "ai:" 开头
        if (not in_ai) and stripped == "ai:":
            in_ai = True
            ai_indent = len(line) - len(line.lstrip())
            out.append(line)
            continue
        if in_ai:
            cur_indent = len(line) - len(line.lstrip())
            # 遇到下一顶层键（缩进 <= ai 行缩进）则退出 ai 块
            if stripped and cur_indent <= ai_indent and not stripped.startswith("-"):
                in_ai = False
            else:
                # 检查是否是目标字段行
                for k in target_keys:
                    if stripped.startswith(k + ":") and k not in handled:
                        indent = line[:cur_indent]
                        if k == "enabled":
                            out.append(f"{indent}{k}: {fields[k]}\n")
                        else:
                            out.append(f'{indent}{k}: "{fields[k]}"\n')
                        handled.add(k)
                        break
                else:
                    out.append(line)
                continue
        out.append(line)
    # 若 ai 块内某些字段缺失，补到 ai 段末尾
    if in_ai:
        for k in target_keys:
            if k not in handled:
                if k == "enabled":
                    out.append(f"  {k}: {fields[k]}\n")
                else:
                    out.append(f'  {k}: "{fields[k]}"\n')
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.writelines(out)


def save_ai_config(partial: dict) -> dict:
    """局部更新 ai 配置（内存 + 文件），返回最新 CONFIG。
    仅接受 ai 段字段：api_key / base_url / model / enabled。"""
    global CONFIG
    ai = CONFIG.setdefault("ai", {})
    for k in ("api_key", "base_url", "model", "enabled"):
        if k in partial:
            v = partial[k]
            if k == "enabled":
                v = bool(v)
            ai[k] = v
    _patch_yaml_ai(ai)
    return CONFIG


def get_ai_config_masked() -> dict:
    """返回 ai 配置，api_key 做掩码处理避免明文暴露。"""
    ai = CONFIG.get("ai", {})
    key = (ai.get("api_key") or "").strip()
    return {
        "api_key": ("****" + key[-4:]) if len(key) >= 4 else ("已设置" if key else ""),
        "api_key_set": bool(key),
        "base_url": ai.get("base_url", ""),
        "model": ai.get("model", ""),
        "enabled": ai.get("enabled", True),
    }
