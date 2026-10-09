"""知识库RAG — 商品知识向量检索

轻量级实现，不依赖外部向量数据库：
1. 用LLM生成商品描述的embedding（或用TF-IDF作为fallback）
2. 内存存储，支持增量更新
3. 检索时返回最相关的商品/FAQ/政策

生产环境可替换为Milvus/Qdrant/pgvector。
"""

import logging
import json
import os
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeItem:
    """知识条目"""
    id: str                     # 唯一ID
    category: str               # product / faq / policy / script
    title: str
    content: str                # 完整文本内容
    metadata: dict = field(default_factory=dict)  # 额外信息
    embedding: Optional[List[float]] = None
    updated_at: str = ""


class KnowledgeBase:
    """知识库 — 支持商品/FAQ/政策/话术的存储和检索"""

    def __init__(self, data_dir: str = "knowledge_base"):
        self.data_dir = data_dir
        self._items: Dict[str, KnowledgeItem] = {}
        self._index_dirty = True
        os.makedirs(data_dir, exist_ok=True)

    def add_item(self, item: KnowledgeItem):
        """添加知识条目"""
        self._items[item.id] = item
        self._index_dirty = True
        logger.debug(f"添加知识条目: {item.id} ({item.category})")

    def remove_item(self, item_id: str):
        """删除知识条目"""
        self._items.pop(item_id, None)
        self._index_dirty = True

    def search(self, query: str, category: str = None, top_k: int = 5) -> List[Tuple[KnowledgeItem, float]]:
        """搜索最相关的知识条目
        
        使用BM25-like关键词匹配（轻量级，无需embedding模型）。
        支持中文：将查询拆分为2-gram子串以提高中文匹配率。
        生产环境可替换为向量检索。
        """
        results = []
        query_lower = query.lower()
        query_terms = set(query_lower.split())
        # 中文2-gram: "耳机多少钱" → {"耳机", "钱多", "少钱", ...}
        for i in range(len(query_lower) - 1):
            bigram = query_lower[i:i+2]
            if bigram.strip():
                query_terms.add(bigram)

        for item in self._items.values():
            if category and item.category != category:
                continue

            score = self._compute_score(query_terms, query_lower, item)
            if score > 0:
                results.append((item, score))

        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    def _compute_score(self, query_terms: set, query_raw: str, item: KnowledgeItem) -> float:
        """计算查询与条目的相关性分数"""
        text = f"{item.title} {item.content}".lower()
        score = 0.0

        # 精确匹配（标题权重更高）
        title_lower = item.title.lower()
        if query_raw in title_lower:
            score += 3.0
        if query_raw in text:
            score += 1.5

        # 术语匹配（分词 + 子串）
        for term in query_terms:
            if term in text:
                score += 1.0
            if term in title_lower:
                score += 2.0

        # 类别加权
        if item.category == "product":
            score *= 1.2  # 商品优先
        elif item.category == "faq":
            score *= 1.1

        return score

    def get_context(self, query: str, category: str = None, top_k: int = 3) -> str:
        """获取检索结果的文本上下文（用于注入LLM prompt）"""
        results = self.search(query, category=category, top_k=top_k)
        if not results:
            return ""

        context_parts = []
        for item, score in results:
            if item.category == "product":
                context_parts.append(f"[商品] {item.title}\n{item.content}")
            elif item.category == "faq":
                context_parts.append(f"[FAQ] {item.title}\n{item.content}")
            elif item.category == "policy":
                context_parts.append(f"[政策] {item.title}\n{item.content}")
            else:
                context_parts.append(f"[{item.category}] {item.title}\n{item.content}")

        return "\n\n---\n\n".join(context_parts)

    # ========== 批量导入 ==========

    def load_from_mock_data(self):
        """从Mock数据加载商品知识"""
        from app.services.mock_data import MOCK_PRODUCTS

        for pid, product in MOCK_PRODUCTS.items():
            skus_text = "\n".join(
                f"  - {s['spec']}: ¥{s['price']:.2f} (库存{s['stock']})"
                for s in product.get("skus", [])
            )
            content = (
                f"价格: ¥{product['price']:.2f} (原价¥{product['original_price']:.2f})\n"
                f"库存: {product['stock']}件\n"
                f"已售: {product['sales']}件\n"
                f"类目: {product['category']}\n"
                f"描述: {product['description']}\n"
                f"规格:\n{skus_text}"
            )
            self.add_item(KnowledgeItem(
                id=f"product_{pid}",
                category="product",
                title=product["title"],
                content=content,
                metadata={"product_id": pid, "price": product["price"]},
            ))

        # FAQ知识
        faqs = [
            ("发货时间", "下单后48小时内发货，偏远地区可能延迟1-2天。"),
            ("退换货政策", "支持7天无理由退换货退款，商品需保持原包装完好。质量问题由卖家承担运费。退款流程：申请退款→卖家审核→退款到账（1-3个工作日）。"),
            ("发票", "支持开具电子发票，在订单详情页申请。"),
            ("优惠券", "店铺不定期发放优惠券，关注店铺可第一时间获取。"),
            ("质保", "数码产品享受1年质保，非人为损坏免费维修。"),
        ]
        for title, content in faqs:
            self.add_item(KnowledgeItem(
                id=f"faq_{hashlib.md5(title.encode()).hexdigest()[:8]}",
                category="faq",
                title=title,
                content=content,
            ))

        # 常用话术
        scripts = [
            ("开场问候", "亲，欢迎光临！有什么可以帮到您的吗？😊"),
            ("催付", "亲，看到您的订单还没付款呢，现在下单还能享受优惠哦～"),
            ("好评引导", "亲，收到商品满意的话麻烦给个五星好评哦，您的支持是我们最大的动力！"),
            ("道歉话术", "非常抱歉给您带来不好的体验，我们会尽快为您处理，请您放心！"),
        ]
        for title, content in scripts:
            self.add_item(KnowledgeItem(
                id=f"script_{hashlib.md5(title.encode()).hexdigest()[:8]}",
                category="script",
                title=title,
                content=content,
            ))

        logger.info(f"从Mock数据加载知识库: {len(self._items)}条")
        return len(self._items)

    def save_to_disk(self):
        """持久化到磁盘"""
        data = {
            item_id: {
                "id": item.id,
                "category": item.category,
                "title": item.title,
                "content": item.content,
                "metadata": item.metadata,
                "updated_at": item.updated_at,
            }
            for item_id, item in self._items.items()
        }
        path = os.path.join(self.data_dir, "knowledge_base.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"知识库已保存: {path} ({len(data)}条)")

    def load_from_disk(self):
        """从磁盘加载"""
        path = os.path.join(self.data_dir, "knowledge_base.json")
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item_id, item_data in data.items():
            self._items[item_id] = KnowledgeItem(**item_data)
        logger.info(f"知识库已加载: {len(self._items)}条")
        return True


# 全局实例
_kb: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    """获取全局知识库实例"""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
        # 先尝试从磁盘加载
        if not _kb.load_from_disk():
            # 没有持久化数据，从Mock加载
            _kb.load_from_mock_data()
            _kb.save_to_disk()
    return _kb
