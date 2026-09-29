"""위키 엔진들: 모두 같은 모양(Engine)으로 다룬다.

    from engines import get, ENGINES
    e = get("opennamu", kit_root)
    for page in e.pages(): ...
    e.put(Page("제목", "본문(엔진 문법)"))

엔진 문법(syntax)은 wikiconv 의 형식 이름과 같다. 문서 제목의 이름공간은 공통('분류:', '틀:')으로 주고받는다.
"""
from .base import Engine, Page  # noqa: F401

ENGINES = ("opennamu", "markdown", "dokuwiki", "mediawiki")
NAMES = {"opennamu": "openNAMU", "markdown": "Markdown (내장)", "dokuwiki": "DokuWiki", "mediawiki": "MediaWiki"}


def get(name, root):
    if name == "opennamu":
        from .opennamu import OpenNamu as E
    elif name == "markdown":
        from .markdown import MarkdownEngine as E
    elif name == "dokuwiki":
        from .dokuwiki import DokuWiki as E
    elif name == "mediawiki":
        from .mediawiki import MediaWiki as E
    else:
        raise ValueError(f"알 수 없는 엔진: {name}")
    return E(root)
