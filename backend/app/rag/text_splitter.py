"""
文本分块器模块
实现Document对象的智能文本分块，保证知识完整性
最后得到Document对象分块后的文本块列表

分块策略：
1. 语义分块（优先）：基于段落、章节进行分割
2. 固定长度分块：按字符数或token数分割
3. 重叠分块：相邻块之间保留一定重叠内容

设计模式：策略模式，支持多种分块策略
"""

from typing import List, Optional, Dict, Any
import re
import logging

# 日志记录器
logger = logging.getLogger(__name__)


class Document:
    """
    文档数据类（与document_loader中的Document保持一致）
    文档内容、类别、元数据
    """

    def __init__(self, id: str, content: str, category: str = "", metadata: Optional[Dict[str, Any]] = None):
        self.id = id
        self.content = content
        self.category = category
        self.metadata = metadata if metadata is not None else {}


class TextSplitter:
    """
    文本分块器
    
    分块策略：
    1. 语义分块（优先）：基于段落、章节进行分割
    2. 固定长度分块：按字符数或token数分割
    3. 重叠分块：相邻块之间保留一定重叠内容
    
    参数：
        chunk_size: 块大小（字符数）
        chunk_overlap: 重叠大小（字符数）
        separator: 分隔符列表（换行、章节标题等）
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50, 
                 separators: Optional[List[str]] = None):
        """
        初始化文本分块器
        
        参数：
            chunk_size: 块大小（字符数），默认500
            chunk_overlap: 重叠大小（字符数），默认50
            separators: 分隔符列表，按优先级排序
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # 默认分隔符列表（按优先级从高到低）
        if separators is None:
            self.separators = [
                "\n\n",      # 段落分隔
                "\n",        # 换行分隔
                "。",        # 中文句号
                "！",        # 中文感叹号
                "？",        # 中文问号
                ".",         # 英文句号
                "!",         # 英文感叹号
                "?",         # 英文问号
                ";",         # 分号
                "；",        # 中文分号
                ",",         # 英文逗号
                "，",        # 中文逗号
                "、",        # 中文顿号
                " ",         # 空格
            ]
        else:
            self.separators = separators

    def split(self, text: str) -> List[str]:
        """
        分割文本为多个块
        
        参数：
            text: 原始文本
        
        返回：块列表
        """
        if not text:
            return []

        chunks = []
        text = text.strip()

        # 使用递归分块
        self._split_recursive(text, chunks)

        logger.info(f"文本分块完成: 原始长度={len(text)}, 块数量={len(chunks)}")
        return chunks

    def split_document(self, doc: Document) -> List[Document]:
        """
        分割文档并保留元数据
        
        参数：
            doc: 原始文档
        
        返回：
            分割后的文档列表
        """
        chunks = self.split(doc.content)

        # 创建分割后的文档列表
        split_docs = []
        for i, chunk in enumerate(chunks):
            split_doc = Document(
                id=f"{doc.id}_{i}",
                content=chunk,
                category=doc.category,
                metadata={
                    **doc.metadata,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "original_id": doc.id
                }
            )
            split_docs.append(split_doc)

        return split_docs

    def _split_recursive(self, text: str, chunks: List[str]) -> None:
        """
        递归分块
        
        参数：
            text: 当前待分割的文本
            chunks: 结果块列表
        """
        # 如果文本长度小于等于块大小，直接添加
        if len(text) <= self.chunk_size:
            if text.strip():
                chunks.append(text.strip())
            return

        # 尝试按分隔符分割
        for separator in self.separators:
            # 查找分割点（在 chunk_size 附近）
            split_point = self._find_split_point(text, separator)
            
            if split_point > 0:
                # 分割文本
                chunk = text[:split_point + len(separator)]
                remaining = text[split_point + len(separator):]
                
                # 添加当前块
                if chunk.strip():
                    chunks.append(chunk.strip())
                
                # 递归处理剩余部分
                self._split_recursive(remaining, chunks)
                return

        # 如果没有找到分隔符，强制按字符数分割
        chunk = text[:self.chunk_size]
        remaining = text[self.chunk_size - self.chunk_overlap:]
        
        if chunk.strip():
            chunks.append(chunk.strip())
        
        self._split_recursive(remaining, chunks)

    def _find_split_point(self, text: str, separator: str) -> int:
        """
        查找合适的分割点
        
        在 chunk_size 附近查找分隔符，优先选择 chunk_size 之前的分隔符
        
        参数：
            text: 待分割文本
            separator: 分隔符
        
        返回：
            分割点位置（分隔符出现的位置），未找到返回-1
        """
        # 在 chunk_size 附近搜索
        search_start = max(0, self.chunk_size - self.chunk_overlap - len(separator))
        search_end = self.chunk_size + self.chunk_overlap
        
        # 在搜索范围内查找分隔符
        index = text.find(separator, search_start, search_end)
        
        if index != -1:
            return index
        
        # 如果没找到，从开头到 chunk_size 范围内查找最后一个分隔符
        last_index = text.rfind(separator, 0, self.chunk_size)
        return last_index

    def split_by_paragraph(self, text: str) -> List[str]:
        """
        按段落分块（简单模式）
        
        参数：
            text: 原始文本
        
        返回：
            段落列表
        """
        # 按双换行符分割段落
        paragraphs = re.split(r'\n\n+', text.strip())
        
        # 过滤空段落
        return [p.strip() for p in paragraphs if p.strip()]


# ======================== 自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("文本分块器自测开始")
    print("=" * 60)

    # 创建文本分块器实例
    splitter = TextSplitter(chunk_size=100, chunk_overlap=20)

    # ---------- 测试1：简单文本分块 ----------
    # 用例：短文本不超过chunk_size，不分割
    short_text = "苹果富含维生素C，每天吃一个有益健康。"
    chunks = splitter.split(short_text)
    assert len(chunks) == 1, f"短文本不应被分割: 期望1块, 实际{len(chunks)}块"
    print("[通过] 测试1 - 短文本不分割")

    # ---------- 测试2：长文本分块 ----------
    # 用例：长文本超过chunk_size(100)，正确分割
    long_text = (
        "苹果富含维生素C，每天吃一个有益健康。"
        "香蕉含有丰富的钾元素，有助于维持心脏健康。"
        "橙子含有丰富的水分和维生素C，有助于补充身体所需的营养。"
        "葡萄富含抗氧化物质，有助于延缓衰老。"
        "蓝莓含有花青素，具有良好的抗氧化效果。"
        "西瓜含有大量水分，有助于消暑解渴。"
        "草莓富含维生素K，对骨骼健康有益。"
        "芒果含有丰富的维生素A，有助于维护视力健康。"
    )
    chunks = splitter.split(long_text)
    assert len(chunks) > 1, f"长文本应被分割: 期望>1块, 实际{len(chunks)}块"
    assert all(len(c) <= 100 for c in chunks), f"块大小超过限制: {[len(c) for c in chunks]}"
    print(f"[通过] 测试2 - 长文本分块: {len(chunks)}块")

    # ---------- 测试3：按段落分块 ----------
    # 用例：有多段落的文本，按段落分割
    paragraph_text = """苹果富含维生素C，每天吃一个有益健康。

香蕉含有丰富的钾元素，有助于维持心脏健康。

橙子含有丰富的水分和维生素C，有助于补充身体所需的营养。"""
    paragraphs = splitter.split_by_paragraph(paragraph_text)
    assert len(paragraphs) == 3, f"按段落分割错误: 期望3段, 实际{len(paragraphs)}段"
    print("[通过] 测试3 - 按段落分块")

    # ---------- 测试4：重叠分块验证 ----------
    # 用例：验证相邻块之间有重叠内容
    overlap_text = "".join(["A" * 50, "B" * 50, "C" * 50])
    chunks = splitter.split(overlap_text)
    
    # 检查重叠：第一个块末尾和第二个块开头应该有重叠
    if len(chunks) >= 2:
        chunk1_end = chunks[0][-20:] if len(chunks[0]) >= 20 else chunks[0]
        chunk2_start = chunks[1][:20] if len(chunks[1]) >= 20 else chunks[1]
        overlap_found = any(chunk1_end[i:i+5] == chunk2_start[:5] for i in range(len(chunk1_end)-4))
        assert overlap_found, "相邻块之间没有重叠"
    print("[通过] 测试4 - 重叠分块验证")

    # ---------- 测试5：文档分块保留元数据 ----------
    # 用例：分割文档后保留原始元数据
    doc = Document(id="doc1", content=long_text, category="营养学", metadata={"source": "test"})
    split_docs = splitter.split_document(doc)
    
    assert len(split_docs) > 1, f"文档应被分割: 期望>1块, 实际{len(split_docs)}块"
    for i, sd in enumerate(split_docs):
        assert sd.id == f"doc1_{i}", f"文档ID错误: {sd.id}"
        assert sd.category == "营养学", "类别丢失"
        assert sd.metadata["source"] == "test", "元数据丢失"
        assert sd.metadata["chunk_index"] == i, "chunk_index错误"
        assert sd.metadata["total_chunks"] == len(split_docs), "total_chunks错误"
    print(f"[通过] 测试5 - 文档分块保留元数据: {len(split_docs)}块")

    # ---------- 测试6：空文本处理 ----------
    # 用例：空文本返回空列表
    chunks = splitter.split("")
    assert chunks == [], "空文本应返回空列表"
    chunks = splitter.split("   \n\n   ")
    assert chunks == [], "空白文本应返回空列表"
    print("[通过] 测试6 - 空文本处理")

    print("=" * 60)
    print("文本分块器自测全部通过（6/6）")
    print("=" * 60)