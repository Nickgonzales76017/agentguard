from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


def read(path: str) -> str:
    return (root / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (root / path).write_text(text, encoding="utf-8")


execution_path = "agentguard/traces/execution.py"
text = read(execution_path)
if "def _validate_json_nesting(" not in text:
    marker = "\ndef load_execution_trace(path: Path) -> ExecutionTrace:\n"
    helper = '''

def _validate_json_nesting(line: str) -> None:
    """Reject excessive JSON nesting before parser recursion varies by Python."""
    depth = 0
    in_string = False
    escaped = False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            # _validate_bounds() treats the parsed root as depth zero, so the
            # lexical form may contain the root plus MAX_TRACE_NESTING nested
            # containers without narrowing the existing accepted boundary.
            if depth > MAX_TRACE_NESTING + 1:
                raise ValueError(
                    f"Trace JSON exceeds the {MAX_TRACE_NESTING}-level nesting limit."
                )
        elif char in "]}" and depth:
            depth -= 1
'''
    if marker not in text:
        raise SystemExit("load_execution_trace marker not found")
    text = text.replace(marker, helper + marker, 1)

old = '''                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, RecursionError) as error:
                    raise ValueError(
                        f"Invalid trace JSON on line {line_number}: {error}"
                    ) from error
'''
new = '''                try:
                    _validate_json_nesting(line)
                    record = json.loads(line)
                except (json.JSONDecodeError, RecursionError, ValueError) as error:
                    raise ValueError(
                        f"Invalid trace JSON on line {line_number}: {error}"
                    ) from error
'''
if old in text:
    text = text.replace(old, new, 1)
elif "_validate_json_nesting(line)" not in text:
    raise SystemExit("json.loads block not found")
write(execution_path, text)

# The newer route-specific test module already truthfully covers invalid UTF-8
# and wrong-shape through every public command. Remove those two vacuous cases
# from the older broad no-disclosure matrix rather than keeping false coverage.
old_tests_path = "tests/unit/test_execution_trace.py"
old_text = read(old_tests_path)
old_text = old_text.replace(
    '_HOSTILE_KINDS = ("invalid_utf8", "malformed_json", "deep_json", "wrong_shape")',
    '_HOSTILE_KINDS = ("malformed_json", "deep_json")',
    1,
)
start = old_text.find('    if kind == "invalid_utf8":\n', old_text.find("def _hostile_trace_file("))
malformed = old_text.find('    elif kind == "malformed_json":\n', start)
if start == -1 or malformed == -1:
    raise SystemExit("old invalid_utf8 branch not found")
old_text = (
    old_text[:start]
    + '    if kind == "malformed_json":\n'
    + old_text[malformed + len('    elif kind == "malformed_json":\n'):]
)
wrong = old_text.find('    elif kind == "wrong_shape":\n', old_text.find("def _hostile_trace_file("))
otherwise = old_text.find(
    '    else:  # pragma: no cover - guards the parametrisation itself\n', wrong
)
if wrong == -1 or otherwise == -1:
    raise SystemExit("old wrong_shape branch not found")
old_text = old_text[:wrong] + old_text[otherwise:]
write(old_tests_path, old_text)

route_path = "tests/unit/test_execution_trace_rejection_paths.py"
route_text = read(route_path)
if "test_json_nesting_preflight_ignores_delimiters_inside_strings" not in route_text:
    route_text += '''


def test_json_nesting_preflight_ignores_delimiters_inside_strings() -> None:
    payload = '{"marker":"' + "[" * 1000 + "}" * 1000 + '\\\"still-string"}'
    trace_module._validate_json_nesting(payload)


def test_json_nesting_preflight_accepts_exact_existing_boundary() -> None:
    depth = trace_module.MAX_TRACE_NESTING + 1
    trace_module._validate_json_nesting("[" * depth + "]" * depth)


def test_json_nesting_preflight_rejects_one_above_existing_boundary() -> None:
    depth = trace_module.MAX_TRACE_NESTING + 2
    with pytest.raises(ValueError, match="nesting limit"):
        trace_module._validate_json_nesting("[" * depth + "]" * depth)
'''
write(route_path, route_text)
