import json
import time
from typing import Optional


def _emit(status_callback, msg):
    print(msg)
    if status_callback:
        status_callback(msg)


def _try_fixup(base_llm, raw_text, schema, label, status_callback):
    _emit(status_callback, f"[FIXUP] {label} | attempting JSON reformat")
    instruction = (
        "The following text was supposed to be JSON matching this schema:\n"
        f"{json.dumps(schema.model_json_schema())}\n\n"
        "Return ONLY valid JSON matching the schema, no prose:\n"
        f"{raw_text}"
    )
    try:
        result = base_llm.invoke(instruction)
        text = getattr(result, "content", result)
        data = json.loads(text)
        return schema.model_validate(data)
    except Exception as exc:
        _emit(status_callback, f"[FIXUP FAILED] {label} | {exc}")
        return None


def invoke_structured(structured_llm, base_llm, prompt_value, schema, *,
                      max_retries: int = 3, delay_seconds: float = 0.0,
                      label: str = "LLM call", status_callback=None,
                      fixup: bool = True) -> Optional[object]:
    last_raw = None
    for attempt in range(1, max_retries + 1):
        _emit(status_callback, f"[REQUEST] {label} | attempt {attempt}/{max_retries}")
        try:
            result = structured_llm.invoke(prompt_value)
            _emit(status_callback, f"[SUCCESS] {label}")
            return result
        except Exception as exc:
            last_raw = str(exc)
            _emit(status_callback, f"[FAILED] {label} | attempt {attempt} | {exc}")
            if attempt < max_retries and delay_seconds:
                time.sleep(delay_seconds)

    if fixup:
        fixed = _try_fixup(base_llm, last_raw, schema, label, status_callback)
        if fixed is not None:
            _emit(status_callback, f"[FIXUP SUCCESS] {label}")
            return fixed

    _emit(status_callback, f"[SKIPPED] {label} failed after retries + fixup")
    return None
