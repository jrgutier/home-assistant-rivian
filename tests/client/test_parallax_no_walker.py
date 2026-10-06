"""No decoder reads the wire by hand.

Until s49 every decoder walked varints itself, so each one carried its own copy
of a message's field numbers and wire types, and the `.proto` files beside them
were documentation that could drift. The decoders now parse with classes
generated from those schemas.

The walker still exists, in `parallax/_wire.py`, as a tool for looking inside a
frame that has no schema yet. This test is what stops it creeping back into a
decoder: one decoder that walks bytes is one message whose layout lives in two
places again.
"""

from __future__ import annotations

import ast
import pathlib

from custom_components.rivian.rivian_client import parallax

PACKAGE = pathlib.Path(parallax.__file__).parent
WALKER = {"_decode_protobuf_fields", "_decode_varint"}
# __init__ re-exports the walker for the tests and scripts that import it from
# the package; _wire defines it.
MAY_NAME_IT = {"__init__.py", "_wire.py"}


def _modules() -> list[pathlib.Path]:
    return sorted(
        path
        for path in PACKAGE.glob("*.py")
        if path.name not in MAY_NAME_IT and not path.name.endswith("_pb2.py")
    )


def test_there_are_decoder_modules_to_check() -> None:
    assert len(_modules()) >= 16


def test_no_decoder_module_names_the_walker() -> None:
    offenders = []
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text())):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name
                if isinstance(node, ast.alias)
                else None
            )
            if name in WALKER:
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, offenders


def test_no_decoder_module_imports_the_wire_module() -> None:
    offenders = []
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                "_wire"
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, offenders


def test_no_decoder_module_decodes_base64_itself() -> None:
    """Payload handling lives in the registry's wrapper, once."""
    offenders = [
        path.name
        for path in _modules()
        if path.name not in {"core.py", "commands.py"} and "base64" in path.read_text()
    ]
    assert not offenders, offenders
