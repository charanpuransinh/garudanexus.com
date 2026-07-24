"""
strategy_sandbox.py
--------------------
Dashboard पर "Custom Strategy" बॉक्स में यूज़र जो Python code पेस्ट करता है,
उसे यहीं से थोड़ा restricted तरीके से चलाया जाता है, फिर backtest_core.py को
वही boolean entry-signal दिया जाता है जो checkbox वाली strategies को मिलता है।

⚠️ ईमानदार चेतावनी (ज़रूर पढ़ना):
यह असली "जेल" (sandbox container) नहीं है। असली भरोसेमंद isolation के लिए
production में इसे Docker container में चलाना चाहिए (network बंद, filesystem
read-only, CPU/RAM cgroup limit के साथ) — यह फाइल सिर्फ पहली दीवार बनाती है:

  1. Static check (AST पढ़कर) — खतरनाक imports/patterns कोड चलने से *पहले* रोकता है
     (os, sys, subprocess, socket, requests, open, eval, exec, __import__, आदि)
  2. अलग process में चलाना — मुख्य API server कभी crash/hang नहीं होगा, चाहे
     यूज़र का code कितना भी खराब क्यों ना हो
  3. Timeout — कोई infinite loop पूरे server को अटका नहीं सकता
  4. Restricted builtins — सिर्फ ज़रूरी चीज़ें (len, range, sum, आदि) उपलब्ध हैं

इतना काफ़ी है अगर सिर्फ आप (या भरोसेमंद लोग) इस्तेमाल कर रहे हैं। अगर कभी यह
box अनजान public लोगों के लिए खोलना हो, तो पहले मुझे बताना — तब हमें असली
Docker-level sandbox जोड़ना पड़ेगा, यह अकेला काफ़ी नहीं होगा।
"""

import ast
import builtins as _builtins
import multiprocessing as mp

import numpy as np
import pandas as pd

import indicators as ind


ALLOWED_IMPORT_MODULES = {"pandas", "numpy", "indicators", "math"}

BLOCKED_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "exit", "quit", "help", "memoryview", "object",
}

SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len",
    "list", "max", "min", "print", "range", "round", "set", "sorted", "str",
    "sum", "tuple", "zip", "True", "False", "None", "isinstance", "type",
]


class SandboxError(Exception):
    """यूज़र-कोड reject होने या fail होने पर यही उठता है — caller इसे साफ़ हिंदी
    error message के साथ HTTP 400 में बदल देता है, server कभी crash नहीं होता।"""


def _static_check(source: str) -> None:
    """Code चलाने से पहले ही AST पढ़कर खतरनाक patterns पकड़ लेता है।"""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise SandboxError(f"Code में syntax error है: {e}")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                mod_names = [(node.module or "").split(".")[0]]
            else:
                mod_names = [n.name.split(".")[0] for n in node.names]
            for m in mod_names:
                if m not in ALLOWED_IMPORT_MODULES:
                    raise SandboxError(
                        f"'{m}' import की इजाज़त नहीं — यहाँ सिर्फ pandas, numpy, "
                        f"indicators (ind से पहले से मौजूद है) और math चल सकते हैं"
                    )
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise SandboxError(f"'{node.id}' इस्तेमाल करने की इजाज़त नहीं")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            raise SandboxError(f"'{node.attr}' जैसे dunder attributes की इजाज़त नहीं")


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    """BUG FIX (2026-07-24): _static_check() explicitly allows `import
    pandas`/numpy/indicators/math (its own error message says exactly
    this), but _safe_builtins() previously omitted __import__ entirely
    from the exec'd code's builtins — and Python's `import` STATEMENT
    always calls __builtins__.__import__() under the hood, regardless of
    which module. So ANY import statement (even of an allowed module)
    crashed with "ImportError: __import__ not found", confirmed live via
    /api/custom_backtest. __import__ itself stays in BLOCKED_NAMES for
    the AST Name-node check (so user code can't call __import__(...)
    directly as a function to sidestep this allowlist) - this is the
    real, restricted implementation the `import` statement itself needs,
    scoped to exactly the same ALLOWED_IMPORT_MODULES the static check
    already enforces, so both checks agree instead of contradicting."""
    top_level = name.split(".")[0]
    if top_level not in ALLOWED_IMPORT_MODULES:
        raise ImportError(
            f"'{top_level}' import की इजाज़त नहीं — सिर्फ pandas, numpy, indicators, math चल सकते हैं"
        )
    return _builtins.__import__(name, globals, locals, fromlist, level)


def _safe_builtins() -> dict:
    safe = {name: getattr(_builtins, name) for name in SAFE_BUILTIN_NAMES if hasattr(_builtins, name)}
    safe["__import__"] = _restricted_import
    return safe


def _worker(source: str, func_name: str, df: pd.DataFrame, queue: "mp.Queue") -> None:
    try:
        _static_check(source)
        safe_globals = {"__builtins__": _safe_builtins(), "pd": pd, "np": np, "ind": ind}
        exec(compile(source, "<custom_strategy>", "exec"), safe_globals)

        if func_name not in safe_globals or not callable(safe_globals[func_name]):
            queue.put({
                "ok": False,
                "error": f"'{func_name}' नाम का function कोड में नहीं मिला — "
                         f"जैसे: def {func_name}(df): ... इस पैटर्न में लिखो और अंत में एक boolean Series return करो",
            })
            return

        result = safe_globals[func_name](df)
        if not isinstance(result, pd.Series):
            queue.put({
                "ok": False,
                "error": "Function को pandas Series (True/False की सीरीज़) लौटानी चाहिए — जैसे: return rsi < 30",
            })
            return

        queue.put({"ok": True, "signal": result.reindex(df.index).fillna(False).astype(bool).tolist()})
    except SandboxError as e:
        queue.put({"ok": False, "error": str(e)})
    except Exception as e:
        queue.put({"ok": False, "error": f"Strategy चलाते वक़्त error: {type(e).__name__}: {e}"})


def run_user_strategy(source: str, df: pd.DataFrame, func_name: str = "my_strategy",
                       timeout_sec: int = 20) -> pd.Series:
    """User code को अलग process में, timeout के साथ चलाता है।
    सफल होने पर boolean entry-signal (pd.Series, df जितनी लंबी) लौटाता है।
    कुछ भी गलत हो — syntax, blocked import, missing function, wrong return type,
    crash, या timeout — तो हमेशा SandboxError उठाता है, कभी server क्रैश नहीं करता।"""
    if len(source) > 20000:
        raise SandboxError("Code बहुत बड़ा है (20,000 अक्षर की सीमा है)")

    ctx = mp.get_context("spawn")
    queue: "mp.Queue" = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(source, func_name, df, queue))
    proc.start()
    proc.join(timeout_sec)

    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise SandboxError(
            f"Code {timeout_sec} सेकंड में पूरा नहीं हुआ — शायद कोई infinite loop है या calculation बहुत भारी है"
        )

    if queue.empty():
        raise SandboxError("Strategy process अचानक बंद हो गया (जैसे बहुत ज़्यादा memory इस्तेमाल करने से)")

    result = queue.get()
    if not result["ok"]:
        raise SandboxError(result["error"])

    return pd.Series(result["signal"], index=df.index)
