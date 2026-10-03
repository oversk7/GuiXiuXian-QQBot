import ast
import asyncio
import importlib.util
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game"
SPEC = importlib.util.spec_from_file_location("image_dimensions_under_test", ROOT / "image_dimensions.py")
dimensions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dimensions)
BASE = "https://raw.giteeusercontent.com/ling-gtq/guixiuxian_imgs/raw/master/"
OLD = BASE + "items/old.png"


@pytest.mark.parametrize("host", ["raw.giteeusercontent.com", "gitee.com"])
@pytest.mark.parametrize("filename", ["item__1200x800.png", "%E7%89%A9%E5%93%81%28a%29__1200x800.JPG", "item%5F%5F1200%78800.webp"])
def test_parse_official_paths_and_query(host, filename):
    url = BASE.replace("raw.giteeusercontent.com", host) + "items/" + filename + "?download=1&name=__0x0.png"
    assert dimensions.parse_image_dimensions(url) == (1200, 800)
    assert dimensions.parse_image_dimensions(url.replace("/items/", "/titles/")) == (1200, 800)


@pytest.mark.parametrize("extension", ["png", "jpeg", "jpg", "gif", "webp", "bmp", "tiff", "ico", "avif", "apng", "jp2", "ppm", "tga", "psd", "dds"])
def test_common_image_extensions(extension):
    assert dimensions.parse_image_dimensions(BASE + "titles/0123456789abcdef__360x113." + extension) == (360, 113)


@pytest.mark.parametrize("url", [
    OLD,
    BASE + "items/a__0x1.png",
    BASE + "items/a__1x0.png",
    BASE + "items/a__-1x2.png",
    BASE + "items/a__1x2.svg",
    BASE + "items/a__1x2.png/extra",
    BASE + "items/nested/a__1x2.png",
    BASE + "items/nested%2Fa__1x2.png",
    BASE + "items/a.png?name=__1x2.png",
    BASE.replace("https:", "http:") + "items/a__1x2.png",
    BASE.replace("raw.giteeusercontent.com", "raw.giteeusercontent.com.evil.test") + "items/a__1x2.png",
    BASE.replace("raw.giteeusercontent.com", "evil.test") + "items/a__1x2.png",
    BASE.replace("raw.giteeusercontent.com", "user@raw.giteeusercontent.com") + "items/a__1x2.png",
    BASE.replace("raw.giteeusercontent.com", "raw.giteeusercontent.com:8443") + "items/a__1x2.png",
    BASE.replace("guixiuxian_imgs", "other_repo") + "items/a__1x2.png",
    BASE.replace("ling-gtq", "another_owner") + "items/a__1x2.png",
    BASE.replace("raw/master", "blob/master") + "items/a__1x2.png",
    BASE.replace("raw/master", "raw/main") + "items/a__1x2.png",
    BASE + "other/a__1x2.png",
    BASE + "Items/a__1x2.png",
    "https://[broken/items/a__1x2.png",
])
def test_untrusted_or_missing_dimensions_rejected(url):
    assert dimensions.parse_image_dimensions(url) is None


@pytest.mark.parametrize("args, expected", [
    ((1200, 800, 300, 300), (300, 200)),
    ((800, 1200, 300, 300), (200, 300)),
    ((100, 2000, 360), (100, 2000)),
    ((720, 4000, 360), (360, 2000)),
    ((20, 10, 300, 300), (20, 10)),
    ((10000, 1, 300, 300), (300, 1)),
])
def test_proportional_limits_and_no_enlargement(args, expected):
    assert dimensions.scale_image_dimensions(*args) == expected


SOURCES = {
    "catalog": ("item/catalog.py", ["_get_image_dimensions_with_cache"]),
    "title": ("player/title_image.py", ["get_title_image", "_prefetch_image_dimensions"]),
    "item": ("item/item_image_admin.py", ["_prefetch_image_dimensions"]),
}


def load_functions(kind):
    path, names = SOURCES[kind]
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    namespace = {
        "parse_image_dimensions": dimensions.parse_image_dimensions,
        "scale_image_dimensions": dimensions.scale_image_dimensions,
        "BANNER_MAX_WIDTH": 360,
        "aiohttp": SimpleNamespace(ClientSession=Mock(side_effect=AssertionError("Unexpected HTTP")), ClientTimeout=aiohttp.ClientTimeout, ClientError=aiohttp.ClientError),
        "asyncio": asyncio, "Image": Image, "BytesIO": BytesIO,
        "_load_image_dimensions_cache": Mock(return_value={}),
        "_save_image_dimensions_cache": Mock(return_value=True),
        "_load_dimensions_cache": Mock(return_value={}),
        "_save_dimensions_cache": Mock(return_value=True),
        "_load_title_images": Mock(return_value={}),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROOT / path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("filename, expected", [("a__1200x800.png", (300, 200)), ("a__10x20.png", (10, 20)), ("a__1x99999.png", (1, 300))])
def test_actual_catalog_bypasses_cache_and_http(filename, expected):
    ns = load_functions("catalog")
    ns["_load_image_dimensions_cache"].side_effect = AssertionError("Unexpected cache read")
    result = asyncio.run(ns["_get_image_dimensions_with_cache"]("item", BASE + "items/" + filename))
    assert result == tuple(map(str, expected))
    ns["aiohttp"].ClientSession.assert_not_called()
    ns["_save_image_dimensions_cache"].assert_not_called()


@pytest.mark.parametrize("size, expected", [("100x2000", (100, 2000)), ("720x4000", (360, 2000)), ("20x10", (20, 10))])
def test_actual_title_getter_needs_no_dimension_cache(size, expected):
    ns = load_functions("title")
    url = BASE + "titles/a(b)__" + size + ".png?download=1"
    ns["_load_title_images"].return_value = {"title": url}
    ns["_load_dimensions_cache"].side_effect = AssertionError("Unexpected cache read")
    assert ns["get_title_image"]("title") == (url.replace("(", "%28").replace(")", "%29"), *expected)
    ns["aiohttp"].ClientSession.assert_not_called()


@pytest.mark.parametrize("kind, url, expected", [
    ("title", BASE + "titles/a__100x2000.gif", (100, 2000)),
    ("title", BASE + "titles/a__720x4000.png", (360, 2000)),
    ("item", BASE + "items/a__1200x800.jpeg", (300, 200)),
    ("item", BASE + "items/a__1x99999.webp", (1, 300)),
])
@pytest.mark.parametrize("save_result", [True, False])
def test_actual_prefetch_caches_without_http(kind, url, expected, save_result):
    ns = load_functions(kind)
    loader = "_load_dimensions_cache" if kind == "title" else "_load_image_dimensions_cache"
    saver = "_save_dimensions_cache" if kind == "title" else "_save_image_dimensions_cache"
    ns[loader].return_value = {"existing": {"url": "untouched"}}
    ns[saver].return_value = save_result
    assert asyncio.run(ns["_prefetch_image_dimensions"]("key", url)) == (True, "")
    ns[saver].assert_called_once_with({"existing": {"url": "untouched"}, "key": {"url": url, "width": expected[0], "height": expected[1]}})
    ns["aiohttp"].ClientSession.assert_not_called()


def mock_download(ns, status=200):
    data = BytesIO()
    Image.new("RGB", (1200, 800)).save(data, format="PNG")
    response = SimpleNamespace(status=status, read=AsyncMock(return_value=data.getvalue()))
    response_context = AsyncMock()
    response_context.__aenter__.return_value = response
    session = SimpleNamespace(get=Mock(return_value=response_context))
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    ns["aiohttp"].ClientSession = Mock(return_value=session_context)
    return session


def test_old_catalog_cache_is_still_used():
    ns = load_functions("catalog")
    ns["_load_image_dimensions_cache"].return_value = {"key": {"url": OLD, "width": 123, "height": 45}}
    assert asyncio.run(ns["_get_image_dimensions_with_cache"]("key", OLD)) == ("123", "45")
    ns["aiohttp"].ClientSession.assert_not_called()


@pytest.mark.parametrize("kind", ["catalog", "title", "item"])
def test_old_urls_still_download_and_cache(kind):
    ns = load_functions(kind)
    session = mock_download(ns)
    if kind == "catalog":
        result = asyncio.run(ns["_get_image_dimensions_with_cache"]("key", OLD))
        assert result == ("300", "200")
    else:
        assert asyncio.run(ns["_prefetch_image_dimensions"]("key", OLD)) == (True, "")
    saver = "_save_dimensions_cache" if kind == "title" else "_save_image_dimensions_cache"
    expected = (360, 240) if kind == "title" else (300, 200)
    ns[saver].assert_called_once_with({"key": {"url": OLD, "width": expected[0], "height": expected[1]}})
    session.get.assert_called_once_with(OLD)


@pytest.mark.parametrize("kind", ["catalog", "title", "item"])
def test_old_http_failure_retains_fallback(kind):
    ns = load_functions(kind)
    mock_download(ns, status=404)
    if kind == "catalog":
        assert asyncio.run(ns["_get_image_dimensions_with_cache"]("key", OLD)) == ("200", "200")
    else:
        assert asyncio.run(ns["_prefetch_image_dimensions"]("key", OLD)) == (False, "获取图片失败: HTTP 404")


def test_old_title_getter_cache_default_and_missing():
    ns = load_functions("title")
    ns["_load_title_images"].return_value = {"title": OLD}
    ns["_load_dimensions_cache"].return_value = {"title": {"url": OLD, "width": 123, "height": 45}}
    assert ns["get_title_image"]("title") == (OLD, 123, 45)
    ns["_load_dimensions_cache"].return_value = {"title": {"url": "changed", "width": 123, "height": 45}}
    assert ns["get_title_image"]("title") == (OLD, 360, 113)
    assert ns["get_title_image"]("missing") is None
