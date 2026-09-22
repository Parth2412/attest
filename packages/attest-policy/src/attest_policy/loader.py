"""Pure bounded policy loading governed by BRD-F09 §5.1."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Final, TypeGuard, cast

import yaml  # type: ignore[import-untyped]  # REQ-F09-090: pinned PyYAML lacks typing metadata
from pydantic import ValidationError
from yaml.loader import (  # type: ignore[import-untyped]  # REQ-F09-090: PyYAML lacks stubs
    BaseLoader,
    SafeLoader,
)
from yaml.nodes import (  # type: ignore[import-untyped]  # REQ-F09-090: PyYAML lacks stubs
    MappingNode,
    Node,
    ScalarNode,
    SequenceNode,
)
from yaml.tokens import (  # type: ignore[import-untyped]  # REQ-F09-090: PyYAML lacks stubs
    AliasToken,
    AnchorToken,
    DirectiveToken,
    TagToken,
)

from attest_policy.errors import PolicyError, policy_error
from attest_policy.models import LoadedPolicy, PolicyDocument, PolicySource

MAX_POLICY_BYTES: Final[int] = 1_048_576
MAX_COLLECTION_DEPTH: Final[int] = 32
ABSENT_POLICY_NOTICE: Final[str] = "No policy configured; reporting only."
EMPTY_POLICY_NOTICE: Final[str] = "Policy contains no rules; reporting only."
_DECIMAL_INTEGER: Final[re.Pattern[str]] = re.compile(r"^(?:0|-[1-9][0-9]*|[1-9][0-9]*)$")
_UNSAFE_TOKENS = (AliasToken, AnchorToken, DirectiveToken, TagToken)
_NO_DOCUMENT: Final[object] = object()
_YAML_BOOL = "tag:yaml.org,2002:bool"
_YAML_NULL = "tag:yaml.org,2002:null"
_YAML_FLOAT = "tag:yaml.org,2002:float"
_YAML_TIMESTAMP = "tag:yaml.org,2002:timestamp"


def _reject_policy_input() -> None:
    raise policy_error("ERR-POLICY-601")


def _default_plain_tag(value: str) -> str:
    first = value[0] if value else ""
    resolvers = [
        *SafeLoader.yaml_implicit_resolvers.get(first, ()),
        *SafeLoader.yaml_implicit_resolvers.get(None, ()),
    ]
    for tag, expression in resolvers:
        if expression.match(value):
            return cast(str, tag)
    return "tag:yaml.org,2002:str"


def _scalar(node: ScalarNode) -> str | int | bool | None:
    value = cast(str, node.value)
    if node.style is not None:
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    if _DECIMAL_INTEGER.fullmatch(value) is not None:
        return int(value)
    if _default_plain_tag(value) in {_YAML_BOOL, _YAML_NULL, _YAML_FLOAT, _YAML_TIMESTAMP}:
        raise policy_error("ERR-POLICY-601")
    return value


def _construct(node: Node, collection_depth: int) -> object:
    if isinstance(node, ScalarNode):
        return _scalar(node)
    if collection_depth > MAX_COLLECTION_DEPTH:
        raise policy_error("ERR-POLICY-601")
    if isinstance(node, SequenceNode):
        return [
            _construct(child, collection_depth + int(not isinstance(child, ScalarNode)))
            for child in node.value
        ]
    if isinstance(node, MappingNode):
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node, ScalarNode):
                raise policy_error("ERR-POLICY-601")
            key = _scalar(key_node)
            if not isinstance(key, str) or key == "<<" or key in result:
                raise policy_error("ERR-POLICY-601")
            result[key] = _construct(
                value_node,
                collection_depth + int(not isinstance(value_node, ScalarNode)),
            )
        return result
    raise policy_error("ERR-POLICY-601")


def _parse_yaml_document(raw: object) -> object:
    """Construct the restricted YAML value without aliases or custom tags (REQ-F09-090)."""
    if not isinstance(raw, bytes) or len(raw) > MAX_POLICY_BYTES:
        raise policy_error("ERR-POLICY-601")
    try:
        text = raw.decode("utf-8", errors="strict")
        if any(isinstance(token, _UNSAFE_TOKENS) for token in yaml.scan(text, Loader=BaseLoader)):
            _reject_policy_input()
        documents = list(yaml.compose_all(text, Loader=BaseLoader))
        if not documents:
            return _NO_DOCUMENT
        if len(documents) != 1 or documents[0] is None:
            _reject_policy_input()
        return _construct(documents[0], 1)
    except PolicyError:
        raise
    except Exception:
        raise policy_error("ERR-POLICY-601") from None


def load_policy(raw: bytes | None, path: str | None = None) -> LoadedPolicy:
    """Load exact policy bytes without opening the display path (REQ-F09-010/090/100/120)."""
    if not _valid_display_path(path):
        raise policy_error("ERR-POLICY-601")
    if raw is None:
        if path is not None:
            raise policy_error("ERR-POLICY-603")
        return LoadedPolicy(
            document=None,
            source=PolicySource(path=None, sha256=None),
            reporting_only_notice=ABSENT_POLICY_NOTICE,
        )
    if not _is_bytes(raw):
        raise policy_error("ERR-POLICY-601")

    source = PolicySource(path=path, sha256=sha256(raw).hexdigest())
    value = _parse_yaml_document(raw)
    if value is _NO_DOCUMENT:
        return LoadedPolicy(
            document=None,
            source=source,
            reporting_only_notice=EMPTY_POLICY_NOTICE,
        )
    if not isinstance(value, dict) or "version" not in value:
        raise policy_error("ERR-POLICY-601")
    version = value["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise policy_error("ERR-POLICY-601")
    if version != 1:
        raise policy_error("ERR-POLICY-602")
    try:
        document = PolicyDocument.model_validate(value)
    except ValidationError:
        raise policy_error("ERR-POLICY-601") from None
    return LoadedPolicy(
        document=document,
        source=source,
        reporting_only_notice=EMPTY_POLICY_NOTICE if not document.policies else None,
    )


def _valid_display_path(path: object) -> bool:
    return path is None or (isinstance(path, str) and bool(path))


def _is_bytes(value: object) -> TypeGuard[bytes]:
    return isinstance(value, bytes)
