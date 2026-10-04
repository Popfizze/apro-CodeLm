import argparse
import base64
import datetime as dt
import json
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
SRC = APP / "src"

STYLE_LINK_RE = re.compile(r'<link rel="stylesheet" href="(styles/[\w-]+\.css)"\s*/?>')
MODULE_TAG_RE = re.compile(r'<script type="module" src="(js/[\w/-]+\.js)"></script>')
DATA_TAG = '<script id="nova-data" type="application/json"></script>'
IMPORT_RE = re.compile(r'^import\s*(\{[^}]*\}|\*\s+as\s+\w+)\s*from\s*"([^"]+)";[ \t]*\n?', re.M)
EXPORT_RE = re.compile(r"^export\s+(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)", re.M)


def parse_args():
    parser = argparse.ArgumentParser(description="Build the self-contained NOVA page.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "out")
    parser.add_argument("--corpus", type=Path, default=ROOT / "data" / "corpus")
    parser.add_argument("--dist", type=Path, default=APP / "dist" / "index.html")
    return parser.parse_args()


def read_jsonl(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_output(path):
    if path.suffix == ".jsonl":
        return read_jsonl(path)
    return json.loads(path.read_text(encoding="utf-8"))


def hex_binary(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("vectors"), str):
        return payload
    converted = dict(payload, binary="hex")
    for key in ("vectors", "scales"):
        if isinstance(payload.get(key), str):
            converted[key] = base64.b64decode(payload[key]).hex()
    return converted


def read_outputs(out_dir):
    files = {}
    for path in sorted(out_dir.glob("*.json*")):
        if path.suffix in (".json", ".jsonl"):
            files[path.name] = hex_binary(read_output(path))
    return files


def corpus_root(corpus):
    readmes = sorted(corpus.rglob("README.txt"))
    return readmes[0].parent if readmes else corpus


def encode_images(root):
    images = {}
    for png in sorted(root.rglob("*.png")):
        key = png.relative_to(root).as_posix()
        images[key] = {"type": "image/png", "hex": png.read_bytes().hex()}
    return images


def read_readme(root):
    readme = root / "README.txt"
    return readme.read_text(encoding="utf-8") if readme.exists() else ""


def build_payload(args):
    root = corpus_root(args.corpus)
    return {
        "files": read_outputs(args.out_dir),
        "images": encode_images(root),
        "readme": read_readme(root),
        "builtAt": dt.datetime.now().astimezone().isoformat(timespec="minutes"),
    }


def module_name(path):
    relative = path.relative_to(SRC / "js").with_suffix("").as_posix()
    return "module_" + re.sub(r"\W", "_", relative)


def resolve_import(importer, specifier):
    return (importer.parent / specifier).resolve()


def collect_modules(path, ordered, seen):
    if path in seen:
        return
    seen.add(path)
    source = path.read_text(encoding="utf-8")
    for match in IMPORT_RE.finditer(source):
        collect_modules(resolve_import(path, match.group(2)), ordered, seen)
    ordered.append(path)


def import_binding(clause, target):
    if clause.startswith("*"):
        return "const " + clause.split()[-1] + " = " + target + ";\n"
    names = clause.strip("{} \n")
    bindings = [part.strip().replace(" as ", ": ") for part in names.split(",") if part.strip()]
    return "const { " + ", ".join(bindings) + " } = " + target + ";\n"


def transform_module(path):
    source = path.read_text(encoding="utf-8")
    exports = EXPORT_RE.findall(source)

    def replace_import(match):
        return import_binding(match.group(1), module_name(resolve_import(path, match.group(2))))

    body = IMPORT_RE.sub(replace_import, source)
    body = re.sub(r"^export\s+", "", body, flags=re.M)
    exported = "return { " + ", ".join(exports) + " };" if exports else ""
    return f"const {module_name(path)} = (() => {{\n{body}\n{exported}\n}})();\n"


def bundle(entry):
    ordered = []
    collect_modules(entry.resolve(), ordered, set())
    return "".join(transform_module(path) for path in ordered)


def inline_styles(page):
    def replace(match):
        css = (SRC / match.group(1)).read_text(encoding="utf-8")
        return "<style>\n" + css + "</style>"

    return STYLE_LINK_RE.sub(replace, page)


def inline_script(page):
    def replace(match):
        code = bundle(SRC / match.group(1)).replace("</script", "<\\/script")
        return '<script type="module">\n' + code + "</script>"

    return MODULE_TAG_RE.sub(replace, page)


def inline_data(page, payload):
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    if page.count(DATA_TAG) != 1:
        sys.exit("index.html must contain the data tag exactly once")
    return page.replace(DATA_TAG, DATA_TAG.replace("></script>", ">" + blob + "</script>"))


def summarize(payload, dist):
    files = ", ".join(sorted(payload["files"]))
    size = dist.stat().st_size / 1024
    print(f"[build] {dist} ({size:.0f} KiB)")
    print(f"[build] outputs: {files}; images: {len(payload['images'])}")


def main():
    args = parse_args()
    payload = build_payload(args)
    page = (SRC / "index.html").read_text(encoding="utf-8")
    page = inline_data(inline_script(inline_styles(page)), payload)
    args.dist.parent.mkdir(parents=True, exist_ok=True)
    args.dist.write_text(page, encoding="utf-8")
    summarize(payload, args.dist)


if __name__ == "__main__":
    main()
