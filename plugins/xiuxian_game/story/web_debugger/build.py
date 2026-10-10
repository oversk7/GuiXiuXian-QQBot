"""将网页源文件打包为可双击打开的单文件 HTML（仅依赖标准库）。"""
from pathlib import Path


def build() -> Path:
    source = Path(__file__).resolve().parent
    html = (source / "index.html").read_text(encoding="utf-8")
    for marker, filename in (("CSS", "style.css"), ("RUNTIME", "runtime.js"), ("APP", "app.js")):
        content = (source / filename).read_text(encoding="utf-8")
        if marker != "CSS":
            content = content.replace("</script", r"<\/script")
        html = html.replace(f"/* BUILD:{marker} */", content)
    destination = source.parent / "story_debugger.html"
    destination.write_text(html, encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(build())
