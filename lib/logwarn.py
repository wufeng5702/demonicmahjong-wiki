"""解析失败汇总 —— 替代裸 except pass, 由 flush_warns 统一打印。

用法:
    from logwarn import warn, flush_warns

    except Exception as e:
        warn(str(e))          # 收集, 不打断流程, 自动带上 文件名:行号

    flush_warns("relic icons")  # 函数结束时打印; 无失败则静默

构建/提取脚本里禁止 `except Exception: pass` 直接吞错:
缺口会一直潜伏到用户浏览时才被发现。收集后统一输出, 打印上限 CAP 条。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

_WARN: list[str] = []
CAP = 20


def warn(msg: str | None = None) -> None:
    """收集一条解析失败 (自动附调用处 文件名:行号)。

    msg 省略且正处于 except 块时, 自动带上异常类型与内容。
    """
    frame = inspect.currentframe().f_back
    loc = f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno}"
    if msg is None:
        exc = sys.exc_info()[1]
        if exc is not None:
            detail = f"{type(exc).__name__}: {exc}"
            msg = f"解析失败 ({detail[:120]})"
        else:
            msg = "解析失败"
    _WARN.append(f"{loc} {msg}")


def flush_warns(context: str = "") -> None:
    """打印并清空已收集的警告。无警告时无输出。"""
    if not _WARN:
        return
    tag = f" ({context})" if context else ""
    print(f"  [WARN] {len(_WARN)} 处解析失败{tag}")
    for w in _WARN[:CAP]:
        print(f"    {w}")
    if len(_WARN) > CAP:
        print(f"    ... 另有 {len(_WARN) - CAP} 处")
    _WARN.clear()


def warn_count() -> int:
    return len(_WARN)
