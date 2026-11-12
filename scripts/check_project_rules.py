"""补充检查 PDF 中的行宽、类型注解和禁止隐式字符串拼接规则。"""

import ast
import io
import tokenize
from pathlib import Path


def check_file(path: Path) -> list[str]:
    """返回单个 Python 文件违反项目约束的位置。

    Args:
        path: 待检查文件。

    Returns:
        可读的规则错误列表。
    """
    source = path.read_text(encoding="utf-8")
    errors = []
    for number, line in enumerate(source.splitlines(), start=1):
        if len(line) > 88 or "\t" in line:
            errors.append(f"{path}:{number}: 超出 88 字符或含 Tab")
    if not source.endswith("\n") or source.endswith("\n\n"):
        errors.append(f"{path}: 文件末尾应仅保留一个换行")
    tree = ast.parse(source)
    if not ast.get_docstring(tree):
        errors.append(f"{path}: 缺少模块 docstring")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not ast.get_docstring(node):
                errors.append(f"{path}:{node.lineno}: 缺少函数 docstring")
            arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            if node.returns is None or any(arg.annotation is None for arg in arguments):
                errors.append(f"{path}:{node.lineno}: 缺少类型注解")
        if isinstance(node, ast.ImportFrom) and node.level:
            errors.append(f"{path}:{node.lineno}: 不允许相对导入")
    previous = None
    ignored = {tokenize.NL, tokenize.COMMENT, tokenize.ENCODING}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in ignored:
            continue
        if previous == tokenize.STRING and token.type == tokenize.STRING:
            errors.append(f"{path}:{token.start[0]}: 不允许隐式字符串拼接")
        previous = token.type
    return errors


def main() -> None:
    """检查源码、测试和脚本；有违规时以非零状态退出。"""
    errors = [
        error
        for directory in ["src", "tests", "scripts"]
        for path in Path(directory).rglob("*.py")
        for error in check_file(path)
    ]
    if errors:
        raise SystemExit("\n".join(errors))
    print("PDF-specific coding rules passed.")


if __name__ == "__main__":
    main()
