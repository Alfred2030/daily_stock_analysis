from __future__ import annotations
import json, os, time
import requests

def _post(url, headers, payload, timeout=90):
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException:
        return ("retry", None)          # 网络层错误可重试
    if resp.status_code == 200:
        try:
            return ("ok", resp.json())
        except ValueError:
            return ("retry", None)      # 200但非JSON，视作瞬时异常
    if resp.status_code in (429, 500, 502, 503, 504):
        return ("retry", None)
    return ("fatal", None)              # 4xx等不可重试

def chat(prompt, system=None, max_tokens=2000, temperature=0.4):
    key = os.getenv("GLM_API_KEY")
    if not key:
        return None
    base = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    model = os.getenv("GLM_MODEL", "glm-5.2")
    retry_base = float(os.getenv("SGOD_LLM_RETRY_BASE", "2.0"))
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": msgs,
               "max_tokens": max_tokens, "temperature": temperature}
    headers = {"Authorization": f"Bearer {key}"}
    for i in range(3):
        kind, data = _post(f"{base}/chat/completions", headers, payload)
        if kind == "ok":
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, AttributeError):
                return None
        if kind == "fatal":
            return None
        time.sleep(retry_base * (2 ** i))
    return None
