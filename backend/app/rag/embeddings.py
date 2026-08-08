"""
向量嵌入模型封装模块

封装 BGE 中文嵌入模型，提供统一的向量化接口。

核心功能：
1. 加载 BGE 中文嵌入模型（本地优先，首次自动下载）
2. 支持单条、批量文本向量化
3. 支持查询向量特殊处理（BGE 模型要求查询文本加 "query: " 前缀）
4. 单例模式，避免重复加载模型
5. 网络不可用时降级为 Mock 模式（随机向量，仅用于测试）

模型加载策略（按优先级）：
    1. 本地路径加载：local_path 存在 → 直接加载（不依赖网络）
    2. 自动下载：local_path 不存在 → 下载到 local_path 后加载（首次执行）
    3. Mock 降级：下载失败或不允许下载 → 生成确定性随机向量

设计模式：单例模式（相同参数返回同一实例）
"""

from typing import List
import os
import hashlib
import logging
import numpy as np

logger = logging.getLogger(__name__)

# ======================== 路径配置 ========================
# 项目根目录（backend/）与默认本地模型目录
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_LOCAL_MODEL_DIR = os.path.join(_PROJECT_ROOT, "data", "models")
os.makedirs(DEFAULT_LOCAL_MODEL_DIR, exist_ok=True)


def get_default_local_model_path(model_name: str) -> str:
    """
    根据模型名返回项目内默认的本地模型目录路径。

    例如 "BAAI/bge-small-zh-v1.5" → "backend/data/models/bge-small-zh-v1.5"
    """
    return os.path.join(DEFAULT_LOCAL_MODEL_DIR, model_name.split('/')[-1])


class EmbeddingModel:
    """
    向量嵌入模型封装类

    BGE 模型使用说明：
        - 查询文本需加前缀 "query: "（由 is_query 参数自动处理）
        - 文档文本不加前缀
        - 使用余弦相似度计算向量相似度

    加载策略：
        1. 优先从 local_path 加载本地模型（不依赖网络）
        2. 本地不存在时，自动下载到 local_path 后加载（首次执行）
        3. 下载失败时，降级为 Mock 模式（随机向量，仅用于测试）

    单例模式：相同参数返回同一实例，避免重复加载模型

    参数：
        model_name:   模型名称（如 BAAI/bge-small-zh-v1.5）
        device:       运行设备（cpu/cuda）
        local_path:   本地模型路径（默认使用项目内 data/models/{model_name}）
        hf_endpoint:  HuggingFace 镜像地址（用于首次下载）
        offline:      是否离线模式（True 时不尝试下载）
    """

    _model_cache = {}  # 单例缓存：{参数组合键: 实例}

    def __new__(cls, model_name: str = "BAAI/bge-small-zh-v1.5",
                device: str = "cpu", local_path: str = "",
                hf_endpoint: str = "https://hf-mirror.com",
                offline: bool = False,
                # 兼容别名：其他模块可能错误地使用 model=... 传参
                model: str = None,
                **_unused_kwargs):
        """
        单例创建：相同参数返回同一实例。

        兼容两种写法：
          - EmbeddingModel(model_name="BAAI/bge-small-zh-v1.5")  # 推荐
          - EmbeddingModel(model="BAAI/bge-small-zh-v1.5")       # 别名兼容
        同时忽略其他未识别关键字参数（而不是抛错），避免第三方库间接口不一致。
        """
        # 别名解析：model 存在时作为 model_name 使用（model_name 显式传的优先级更高）
        if model_name in (None, "", "BAAI/bge-small-zh-v1.5") and model:
            model_name = model
        cache_key = f"{model_name}_{device}_{local_path}_{hf_endpoint}_{offline}"
        if cache_key not in cls._model_cache:
            cls._model_cache[cache_key] = super().__new__(cls)
        instance = cls._model_cache[cache_key]
        # 把解析后的参数存到实例缓存键上，供 __init__ 使用（只在首次创建时有效）
        if not hasattr(instance, '_init_kwargs'):
            instance._init_kwargs = dict(
                model_name=model_name,
                device=device,
                local_path=local_path,
                hf_endpoint=hf_endpoint,
                offline=offline,
            )
        return instance

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5",
                 device: str = "cpu", local_path: str = "",
                 hf_endpoint: str = "https://hf-mirror.com",
                 offline: bool = False,
                 model: str = None,
                 **_unused_kwargs):
        """
        初始化模型配置（仅首次创建实例时执行）。

        参数解析优先级：
          1) 若实例已通过 __new__ 写入 _init_kwargs（含别名解析），使用 _init_kwargs；
          2) 否则回退为显式传入参数（model_name 优先，否则用别名 model）。
        """
        if hasattr(self, '_initialized'):
            return

        kwargs = getattr(self, '_init_kwargs', None)
        if kwargs is None:
            if not model_name and model:
                model_name = model
            kwargs = dict(
                model_name=model_name or "BAAI/bge-small-zh-v1.5",
                device=device,
                local_path=local_path,
                hf_endpoint=hf_endpoint,
                offline=offline,
            )

        self.model_name = kwargs["model_name"] or "BAAI/bge-small-zh-v1.5"
        self.device = kwargs["device"] or "cpu"
        # local_path 优先级：函数参数 > 环境变量 BGE_LOCAL_PATH > 项目默认路径
        self.local_path = (kwargs.get("local_path")
                           or os.environ.get("BGE_LOCAL_PATH")
                           or get_default_local_model_path(self.model_name))
        self.hf_endpoint = kwargs.get("hf_endpoint") or "https://hf-mirror.com"
        self.offline = bool(kwargs.get("offline", False))

        self._initialized = True
        self._model = None          # SentenceTransformer 实例（Mock 模式下为 None）
        self.dim = 512              # 向量维度（加载成功后更新）
        self._last_load_error = ""  # 加载失败原因（供诊断）

        logger.info(f"EmbeddingModel 初始化: model_name={self.model_name}, "
                    f"local_path={self.local_path}, offline={self.offline}")

    def _load_model(self):
        """
        延迟加载模型（懒加载）

        按优先级尝试三种策略，任一成功即返回：
            1. 本地路径加载：local_path 存在 → 直接加载，不依赖网络
            2. 自动下载：local_path 不存在 → 下载到 local_path 后加载（首次执行）
            3. Mock 降级：上述均失败 → 保留 _model=None，使用随机向量
        """
        if self._model is not None:
            return

        # ---------- 策略1：本地路径加载（不依赖网络） ----------
        if os.path.exists(self.local_path):
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"从本地路径加载模型: {self.local_path}")
                self._model = SentenceTransformer(self.local_path, device=self.device)
                self.dim = self._model.get_embedding_dimension()
                self._last_load_error = ""
                logger.info(f"本地模型加载成功，向量维度: {self.dim}")
                return
            except Exception as e:
                err_msg = f"本地模型加载失败: {type(e).__name__}: {e}"
                self._last_load_error = err_msg
                logger.warning(err_msg)
                if self.offline:
                    raise RuntimeError(f"离线模式下本地模型加载失败: {e}")
                logger.info("本地加载失败，尝试重新下载...")

        # ---------- 策略2：自动下载到本地（首次执行） ----------
        if not self.offline:
            try:
                if self.hf_endpoint:
                    os.environ["HF_ENDPOINT"] = self.hf_endpoint
                    logger.info(f"使用 HuggingFace 镜像: {self.hf_endpoint}")

                logger.info(f"首次运行，正在下载模型 {self.model_name} → {self.local_path} ...")
                from huggingface_hub import snapshot_download
                snapshot_download(
                    repo_id=self.model_name,
                    local_dir=self.local_path,
                    local_dir_use_symlinks=False
                )
                logger.info("模型下载完成，开始加载...")

                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.local_path, device=self.device)
                self.dim = self._model.get_embedding_dimension()
                self._last_load_error = ""
                logger.info(f"模型加载完成: {self.model_name}, 维度: {self.dim}")
                return
            except Exception as e:
                err_msg = f"模型下载失败: {type(e).__name__}: {e}"
                self._last_load_error = err_msg
                logger.warning(err_msg)
                logger.info("将使用 Mock 模式（随机向量）进行测试")

        # ---------- 策略3：Mock 降级 ----------
        logger.warning("=" * 50)
        logger.warning("使用 Mock 模式：向量为随机生成，仅用于测试！")
        if self._last_load_error:
            logger.warning(f"失败原因: {self._last_load_error}")
        logger.warning("=" * 50)
        self._model = None
        self.dim = 512

    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        文本向量化（批量）

        参数：
            texts:     待向量化的文本列表
            is_query:  是否为查询文本（True 时自动加 "query: " 前缀）

        返回：
            向量列表，每个向量为 float 数组
        """
        self._load_model()

        if not texts:
            return []

        # Mock 模式：使用确定性随机向量
        if self._model is None:
            return self._mock_embed(texts)

        # 真实模型：BGE 查询文本需加前缀
        processed = [f"query: {t}" for t in texts] if is_query else texts
        embeddings = self._model.encode(
            processed,
            convert_to_numpy=True,
            show_progress_bar=False
        )
        return embeddings.tolist()

    def embed_single(self, text: str, is_query: bool = False) -> List[float]:
        """
        单条文本向量化

        参数：
            text:      待向量化的文本
            is_query:  是否为查询文本

        返回：
            向量（float 数组）
        """
        result = self.embed([text], is_query=is_query)
        return result[0] if result else []

    def _mock_embed(self, texts: List[str]) -> List[List[float]]:
        """
        Mock 向量化：基于文本 MD5 哈希生成确定性随机向量

        使用 MD5（而非 Python 内置 hash）确保跨运行、跨进程的确定性。
        向量经 L2 归一化，可与真实模型向量使用相同的余弦相似度计算逻辑。
        """
        vectors = []
        for text in texts:
            md5_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            seed = int(md5_hash[:8], 16) % (2**31)
            rng = np.random.RandomState(seed)
            vector = rng.randn(self.dim).astype(np.float32)
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm
            vectors.append(vector.tolist())
        return vectors

    @property
    def is_mock_mode(self) -> bool:
        """是否处于 Mock 模式（模型未成功加载）"""
        return self._model is None


# ======================== 自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m rag.embeddings
if __name__ == "__main__":
    import logging as _logging
    # 配置日志，让加载失败的 logger.warning 可见
    _logging.basicConfig(level=_logging.WARNING, format="[%(levelname)s] %(message)s")

    print("=" * 60)
    print("向量嵌入模型自测开始")
    print("=" * 60)

    # 创建模型实例（默认使用国内镜像）
    model = EmbeddingModel(
        model_name="BAAI/bge-small-zh-v1.5",
        device="cpu",
        hf_endpoint="https://hf-mirror.com",
        offline=False
    )

    # 显式触发懒加载，以便准确检查模型加载状态
    # （_load_model 是懒加载，不主动调用时 _model 仍为 None，is_mock_mode 会误报）
    model._load_model()

    if model.is_mock_mode:
        print("[提示] 当前使用 Mock 模式（随机向量）")
        if model._last_load_error:
            print(f"[诊断] 加载失败详情: {model._last_load_error}")
        print("[提示] 如需真实向量，请：")
        print("       1. 检查网络连接 / 更换 HF 镜像地址")
        print("       2. 或设置 local_path 指向本地模型目录")
        print("       3. 或手动下载：huggingface-cli download BAAI/bge-small-zh-v1.5")
    else:
        print("[成功] 模型加载完成")

    # ---------- 测试1：单条文本向量化 ----------
    text = "糖尿病饮食注意事项"
    embedding = model.embed_single(text)
    assert len(embedding) == 512, f"向量维度错误: 期望512, 实际{len(embedding)}"
    print(f"[通过] 测试1 - 单条文本向量化: 向量维度={len(embedding)}")

    # ---------- 测试2：批量文本向量化 ----------
    texts = ["苹果富含维生素C", "香蕉有助于消化", "橙子含有丰富水分"]
    embeddings = model.embed(texts)
    assert len(embeddings) == 3, f"批量向量化数量错误: 期望3, 实际{len(embeddings)}"
    assert all(len(e) == 512 for e in embeddings), "批量向量化维度不一致"
    print(f"[通过] 测试2 - 批量文本向量化: {len(embeddings)}条, 维度均为512")

    # ---------- 测试3：查询向量特殊处理 / Mock确定性 ----------
    if not model.is_mock_mode:
        query_text = "如何控制血糖"
        query_embedding = model.embed_single(query_text, is_query=True)
        normal_embedding = model.embed_single(query_text, is_query=False)
        assert query_embedding != normal_embedding, "查询向量与普通向量相同，前缀处理失效"
        print("[通过] 测试3 - 查询向量特殊处理: 前缀生效")
    else:
        vec1 = model.embed_single("测试文本")
        vec2 = model.embed_single("测试文本")
        assert vec1 == vec2, "Mock模式下相同文本应产生相同向量"
        print("[通过] 测试3 - Mock模式确定性验证: 相同文本->相同向量")

    # ---------- 测试4：单例模式验证 ----------
    model1 = EmbeddingModel("BAAI/bge-small-zh-v1.5", device="cpu",
                             hf_endpoint="https://hf-mirror.com")
    model2 = EmbeddingModel("BAAI/bge-small-zh-v1.5", device="cpu",
                             hf_endpoint="https://hf-mirror.com")
    assert model1 is model2, "单例模式失效: 创建了不同实例"
    print("[通过] 测试4 - 单例模式: 相同参数返回同一实例")

    # ---------- 测试5：空文本处理 ----------
    result = model.embed([])
    assert result == [], "空列表输入未返回空列表"
    print("[通过] 测试5 - 空文本处理: 返回空列表")

    # ---------- 测试6：Mock向量归一化验证 ----------
    if model.is_mock_mode:
        vec = model.embed_single("测试")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.01, f"向量未归一化: 范数={norm}"
        print(f"[通过] 测试6 - Mock向量归一化验证: 范数={norm:.4f}")
    else:
        print("[跳过] 测试6 - 仅Mock模式下测试")

    print("=" * 60)
    print("向量嵌入模型自测全部通过")
    print("=" * 60)
