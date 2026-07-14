import json
import re
import time
import typing
from typing import Optional

from pydantic import BaseModel

from comment_agent.logging_config import get_logger, emit_status

logger = get_logger(__name__)


def _emit(status_callback, msg):
    emit_status(logger, status_callback, msg)


# --- raw output extraction -------------------------------------------------

def _raw_text(raw) -> str:
    """Pull the JSON payload out of an include_raw=True response message."""
    if raw is None:
        return ""
    content = getattr(raw, "content", raw)
    if isinstance(content, str) and content.strip():
        return content
    # function_calling method stashes the JSON in tool-call arguments
    kwargs = getattr(raw, "additional_kwargs", {}) or {}
    for call in kwargs.get("tool_calls", []) or []:
        args = call.get("function", {}).get("arguments")
        if args:
            return args
    return str(content)


# --- tier 1: deterministic repair ------------------------------------------

def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    text = re.sub(r",(\s*[}\]])", r"\1", text)          # trailing commas
    text = text.replace("“", '"').replace("”", '"')  # smart quotes
    return text


def _is_list_field(annotation) -> bool:
    return typing.get_origin(annotation) is list


def _is_nested_list_field(annotation) -> bool:
    args = typing.get_args(annotation)
    return (typing.get_origin(annotation) is list
            and bool(args) and typing.get_origin(args[0]) is list)


def _list_item_model(annotation):
    """The BaseModel item type of a List[Model] annotation, else None."""
    args = typing.get_args(annotation)
    if typing.get_origin(annotation) is list and args:
        item = args[0]
        if isinstance(item, type) and issubclass(item, BaseModel):
            return item
    return None


def _normalize_keys(data: dict, schema) -> dict:
    """Case-insensitive key match to schema fields; coerce common shape errors:
    bare str where a list is expected, and flat List[str] where List[List[str]]
    is expected (small models routinely flatten the nesting). Recurses into
    List[Model] fields so nested topic objects get the same treatment."""
    fields = schema.model_fields
    lower_map = {name.lower(): name for name in fields}
    fixed = {lower_map.get(k.lower(), k): v for k, v in data.items()}
    for name, field in fields.items():
        if name not in fixed:
            continue
        value, annotation = fixed[name], field.annotation
        item_model = _list_item_model(annotation)
        if item_model is not None and isinstance(value, list):
            fixed[name] = [
                _normalize_keys(v, item_model) if isinstance(v, dict) else v
                for v in value
            ]
        elif _is_list_field(annotation) and isinstance(value, str):
            fixed[name] = [value]
        elif (_is_nested_list_field(annotation) and isinstance(value, list)
                and value and all(isinstance(v, str) for v in value)):
            fixed[name] = [[v] for v in value]  # one flat entry per topic
    return fixed


def _deterministic_fix(raw_text: str, schema):
    if not raw_text:
        return None
    try:
        data = json.loads(_extract_json(raw_text))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return schema.model_validate(_normalize_keys(data, schema))
    except Exception:
        return None


# --- tier 2: LLM repair (langchain OutputFixingParser, same model) ---------

def _llm_fix(base_llm, raw_text, schema, label, status_callback):
    # deferred import: langchain_classic costs ~0.7s and this error path is rare
    from langchain_classic.output_parsers import OutputFixingParser
    from langchain_core.output_parsers import PydanticOutputParser

    # max_retries>1: small models often miss the nested object shape on the
    # first fix attempt; a couple of retries let it land.
    parser = OutputFixingParser.from_llm(
        parser=PydanticOutputParser(pydantic_object=schema),
        llm=base_llm,
        max_retries=3,
    )
    try:
        return parser.parse(raw_text)
    except Exception as exc:
        _emit(status_callback, f"[FIXUP FAILED] {label} | {exc}")
        return None


# --- orchestration ---------------------------------------------------------

def invoke_structured(structured_llm, base_llm, prompt_value, schema, *,
                      max_retries: int = 3, delay_seconds: float = 0.0,
                      label: str = "LLM call", status_callback=None,
                      fixup: bool = True, config=None) -> Optional[object]:
    """Primary structured call (bound with include_raw=True). On a parse error:
    tier 1 deterministic JSON repair, then tier 2 same-model LLM repair.

    `config` (e.g. {"callbacks": [...]}) is forwarded to the primary invoke so
    callers can attach a usage-metadata callback. ponytail: the tier-2 LLM
    repair path is NOT counted (rare); wire config into _llm_fix if it matters.
    """
    raw_text = None
    for attempt in range(1, max_retries + 1):
        _emit(status_callback, f"[REQUEST] {label} | attempt {attempt}/{max_retries}")
        try:
            result = (structured_llm.invoke(prompt_value, config=config)
                      if config is not None
                      else structured_llm.invoke(prompt_value))
        except Exception as exc:                       # network/API error, not parse
            _emit(status_callback, f"[API ERROR] {label} | attempt {attempt} | {exc}")
            if attempt < max_retries and delay_seconds:
                time.sleep(delay_seconds)
            continue

        if not isinstance(result, dict):               # plain binding, no include_raw
            _emit(status_callback, f"[SUCCESS] {label}")
            return result

        if result.get("parsed") is not None and result.get("parsing_error") is None:
            _emit(status_callback, f"[SUCCESS] {label}")
            return result["parsed"]

        raw_text = _raw_text(result.get("raw"))
        _emit(status_callback, f"[PARSE ERROR] {label} | attempt {attempt} | deterministic fix")
        fixed = _deterministic_fix(raw_text, schema)
        if fixed is not None:
            _emit(status_callback, f"[FIXED] {label} | deterministic")
            return fixed

        # Parse errors are ~deterministic at low temperature: re-invoking the
        # identical prompt yields the same bad output. Skip the remaining
        # invoke retries (they only help transient API errors) and go straight
        # to tier-2 LLM repair, which feeds the error back so output changes.
        break

    if fixup and raw_text:
        _emit(status_callback, f"[FIXUP] {label} | LLM repair (same model)")
        fixed = _llm_fix(base_llm, raw_text, schema, label, status_callback)
        if fixed is not None:
            _emit(status_callback, f"[FIXUP SUCCESS] {label}")
            return fixed

    _emit(status_callback, f"[SKIPPED] {label} | unrecoverable")
    return None
