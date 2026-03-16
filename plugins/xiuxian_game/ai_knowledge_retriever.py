"""
AI知识库BM25检索器 - 从YAML知识块文件中检索相关游戏知识

架构：
  用户问题 → BM25检索器 → top-5 YAML知识块 → 拼接上下文 → AI
"""
import re
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).parent / "data" / "knowledge"


class KnowledgeChunk:
    """单个知识块"""
    __slots__ = ("id", "title", "keywords", "body")

    def __init__(self, id: str, title: str, keywords: List[str], body: str):
        self.id = id
        self.title = title
        self.keywords = keywords
        self.body = body

    def to_context_text(self) -> str:
        """返回注入AI prompt的文本"""
        return f"【{self.title}】\n{self.body.strip()}"


def _tokenize(text: str) -> List[str]:
    """
    中文 unigram + bigram，英文/数字按整词保留（小写）
    示例："修炼突破" → ["修","炼","突","破","修炼","炼突","突破"]
    """
    tokens = []
    # 先提取英文数字整词
    en_tokens = re.findall(r'[a-zA-Z0-9]+', text)
    for tok in en_tokens:
        tokens.append(tok.lower())

    # 再处理中文字符
    chinese_chars = re.sub(r'[a-zA-Z0-9\s\W]', '', text)
    # unigram
    for ch in chinese_chars:
        tokens.append(ch)
    # bigram
    for i in range(len(chinese_chars) - 1):
        tokens.append(chinese_chars[i] + chinese_chars[i + 1])

    return tokens


class KnowledgeRetriever:
    """BM25知识库检索器"""

    def __init__(self):
        self._chunks: List[KnowledgeChunk] = []
        self._bm25 = None
        self._fallback_ids = ["common_001_worldview", "common_003_faq", "guide_001_growth"]

    def load(self, knowledge_dir: Path) -> None:
        """
        加载YAML知识块并构建BM25索引

        Args:
            knowledge_dir: 知识库目录路径
        """
        try:
            import yaml
        except ImportError:
            logger.error("[KnowledgeRetriever] 缺少 PyYAML 依赖，无法加载知识库")
            return

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.error("[KnowledgeRetriever] 缺少 rank-bm25 依赖，请执行: pip install rank-bm25")
            return

        chunks = []
        yaml_files = list(knowledge_dir.glob("*.yaml"))

        if not yaml_files:
            logger.warning(f"[KnowledgeRetriever] 知识库目录中没有找到YAML文件: {knowledge_dir}")
            return

        for yaml_file in sorted(yaml_files):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    logger.warning(f"[KnowledgeRetriever] 跳过格式异常文件: {yaml_file.name}")
                    continue

                chunk_id = data.get("id", yaml_file.stem)
                title = data.get("title", "")
                keywords = data.get("keywords", [])
                body = data.get("body", "")

                if not isinstance(keywords, list):
                    keywords = []

                chunks.append(KnowledgeChunk(
                    id=str(chunk_id),
                    title=str(title),
                    keywords=[str(k) for k in keywords],
                    body=str(body)
                ))
            except Exception as e:
                logger.warning(f"[KnowledgeRetriever] 跳过损坏文件 {yaml_file.name}: {e}")
                continue

        if not chunks:
            logger.warning("[KnowledgeRetriever] 没有成功加载任何知识块")
            return

        # 构建带权重的语料库
        # title×2 + keywords×2 + body×1
        corpus = []
        for chunk in chunks:
            title_tokens = _tokenize(chunk.title) * 2
            keyword_tokens = []
            for kw in chunk.keywords:
                keyword_tokens.extend(_tokenize(kw) * 2)
            body_tokens = _tokenize(chunk.body)
            all_tokens = title_tokens + keyword_tokens + body_tokens
            corpus.append(all_tokens)

        self._chunks = chunks
        self._bm25 = BM25Okapi(corpus)
        logger.success(f"[KnowledgeRetriever] 已加载 {len(chunks)} 个知识块，BM25 索引构建完成")

    def search(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Tuple[KnowledgeChunk, float]]:
        """
        BM25检索

        Args:
            query: 查询文本
            top_k: 返回前K个结果
            min_score: 最低分数阈值

        Returns:
            List of (KnowledgeChunk, score) 按分数降序排列
        """
        if not self._bm25 or not self._chunks:
            logger.warning("[KnowledgeRetriever] BM25索引未初始化，使用兜底策略")
            return self._get_fallback_chunks()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return self._get_fallback_chunks()

        scores = self._bm25.get_scores(query_tokens)

        # 按分数降序排列
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed_scores[:top_k]:
            if score > min_score:
                results.append((self._chunks[idx], float(score)))

        if not results:
            return self._get_fallback_chunks()

        return results

    def _get_fallback_chunks(self) -> List[Tuple[KnowledgeChunk, float]]:
        """兜底：返回世界观/FAQ/新手攻略三个块"""
        result = []
        for chunk in self._chunks:
            if chunk.id in self._fallback_ids:
                result.append((chunk, 0.0))
        return result


# 模块级单例（延迟加载）
knowledge_retriever = KnowledgeRetriever()


def initialize_knowledge_retriever() -> None:
    """初始化知识库检索器（同步函数，在on_startup中直接调用）"""
    knowledge_retriever.load(_KNOWLEDGE_DIR)
