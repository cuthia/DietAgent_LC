"""
天气工具 —— 高德地图 Web 服务 API（第四点改进）

功能：
1. 查询指定地区实时天气
2. 根据温度/湿度/天气现象生成膳食风格提示
3. 带进程内 TTL 缓存（同地区 30 分钟内不重复请求）
4. 完整降级策略（未配 Key / API 失败 → ok=false + fallback_reason，不阻塞主链路）

用法：
- @tool 装饰后，可被 chain.ainvoke() 显式调用
- 也可被 LLM 自主调用（bind_tools 模式）
- 前端可通过 /api/agent/weather/current 端点独立获取天气数据
"""

import logging
import time
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool as _lc_tool

logger = logging.getLogger(__name__)

# 进程内内存缓存：key=adcode|region_name, value=(expire_ts, result_dict)
_WEATHER_CACHE: Dict[str, tuple] = {}


# ========== 高德城市 adcode 精简映射表 ==========
# 免掉一次高德地理编码 API 调用（省配额 + 加速）
_ADCODE_MAP: Dict[str, str] = {
    # 直辖市
    "北京": "110000", "北京市": "110000", "上海": "310000", "上海市": "310000",
    "天津": "120000", "天津市": "120000", "重庆": "500000", "重庆市": "500000",
    # 华东
    "杭州": "330100", "杭州市": "330100", "南京": "320100", "南京市": "320100",
    "苏州": "320500", "无锡市": "320200", "宁波": "330200",
    "温州": "330300", "合肥": "340100", "福州市": "350100", "厦门": "350200",
    "济南": "370100", "青岛": "370200", "南昌": "360100",
    # 华南
    "广州": "440100", "广州市": "440100", "深圳": "440300", "深圳市": "440300",
    "东莞": "441900", "佛山": "440600", "珠海": "440400", "南宁": "450100",
    "海口": "460100", "三亚": "460200",
    # 华北/东北
    "石家庄": "130100", "太原": "140100", "呼和浩特": "150100",
    "沈阳": "210100", "大连": "210200", "长春": "220100", "哈尔滨": "230100",
    # 华中
    "郑州": "410100", "武汉": "420100", "长沙市": "430100", "长沙": "430100",
    # 西南/西北
    "成都": "510100", "成都市": "510100", "贵阳": "520100", "昆明": "530100",
    "拉萨": "540100", "西安": "610100", "西安市": "610100",
    "兰州": "620100", "西宁": "630100", "银川": "640100", "乌鲁木齐": "650100",
}


def _adcode_lookup(region_name: str) -> Optional[str]:
    """从中文名查 adcode，支持精确匹配 + 前后缀模糊匹配 + 前缀 2-3 字匹配"""
    if not region_name:
        return None
    region_name = region_name.strip()
    if region_name in _ADCODE_MAP:
        return _ADCODE_MAP[region_name]
    # 模糊：去"市/省/区/县"后缀
    for suf in ("市辖区", "特别行政区", "自治区", "省", "市", "区", "县"):
        if region_name.endswith(suf) and region_name[:-len(suf)] in _ADCODE_MAP:
            return _ADCODE_MAP[region_name[:-len(suf)]]
    # 模糊：取前缀 2~3 字匹配
    for k, v in _ADCODE_MAP.items():
        if region_name.startswith(k) or k.startswith(region_name):
            return v
    return None


def _gen_diet_hints(temperature: float, weather: str, humidity_pct: int) -> List[str]:
    """
    纯规则：根据气候参数生成膳食风格提示（确定性，不让 LLM 瞎想）。
    """
    hints: List[str] = []
    # 温度
    if temperature >= 32:
        hints.append("气温炎热，推荐凉拌菜、冷食、凉面、清汤类菜品，减少重油重炖与火锅烧烤")
        hints.append("可增加清热消暑食材：绿豆、苦瓜、黄瓜、冬瓜、西瓜、荷叶、莲子")
    elif 28 <= temperature < 32:
        hints.append("气温较高，烹饪方式偏清淡，建议多用清炒、蒸、白灼，减少红烧油炸")
        hints.append("可推荐消暑汤品：绿豆汤、酸梅汤、银耳莲子羹")
    elif 18 <= temperature < 28:
        hints.append("气温舒适，烹饪方式可多样化，兼顾清爽与暖胃的搭配")
    elif 10 <= temperature < 18:
        hints.append("气温偏凉，推荐热汤、炖煮、煲仔类菜品，注意保证能量摄入")
        hints.append("可增加温补食材：羊肉、鸡肉、生姜、红枣、桂圆")
    else:
        hints.append("天气寒冷，优先推荐炖煮、红烧、煲汤类暖身菜品，可适当提高健康脂肪比例")
        hints.append("可推荐驱寒食材：生姜、大葱、蒜、胡椒、羊肉、牛肉、核桃")
    # 降雨/湿度
    wet_keywords = ("雨", "雷", "阵雨", "暴雨", "小雨", "中雨", "大雨", "雪")
    if any(k in weather for k in wet_keywords) or humidity_pct >= 80:
        hints.append("湿度高或有降雨，可推荐祛湿食材：薏米、赤小豆、山药、冬瓜、茯苓、白扁豆")
    # 强日晒
    if "晴" in weather and temperature >= 28:
        hints.append("紫外线较强，建议增加富含 VC 和番茄红素的抗氧化食材：番茄、橙子、西兰花、猕猴桃、蓝莓")
    return hints


@_lc_tool
async def weather_tool(
    region_name: Optional[str] = None,
    adcode: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    查询指定地区的实时天气，返回结构化气候参数 + 膳食建议提示。

    参数：
        region_name: 地区中文名（如"杭州"、"北京市"），不传则从 user_id 档案取
        adcode: 高德 6 位城市编码（优先级高于 region_name）
        user_id: 用户 ID（region_name 和 adcode 都不传时，从档案取地区）

    返回：
        {
            "ok": true/false,
            "region": "杭州市",
            "temperature": 28,
            "weather": "多云",
            "humidity": "71",
            "diet_hints": ["气温较高，推荐凉拌菜...", ...],
            "fallback_reason": ""  # ok=false 时说明原因
        }
    """
    from core.config_handler import get_settings
    settings = get_settings()
    cfg = settings.weather

    # --- 1) 开关 & Key 校验 ---
    if not cfg.enabled or not cfg.api_key or not cfg.api_key.strip():
        return {
            "ok": False,
            "region": region_name or "",
            "temperature": None,
            "weather": "",
            "humidity": "",
            "diet_hints": [],
            "fallback_reason": "天气功能未配置 API Key，已跳过天气适配",
        }

    # --- 2) 解析 region → adcode ---
    if not adcode and region_name:
        adcode = _adcode_lookup(region_name)

    if not adcode and user_id is not None:
        try:
            from agent.tools.user_tool import get_user_info
            prof = await get_user_info(user_id)
            if prof and prof.get("region"):
                adcode = _adcode_lookup(prof["region"])
                region_name = prof["region"]
        except Exception as e:
            logger.debug(f"[weather_tool] 从档案取地区失败: {e}")

    if not adcode:
        return {
            "ok": False,
            "region": region_name or "",
            "temperature": None,
            "weather": "",
            "humidity": "",
            "diet_hints": [],
            "fallback_reason": "未识别到有效地区，跳过天气适配（请在健康档案中填写地区）",
        }

    # --- 3) 缓存命中 ---
    cache_key = f"{adcode}|{region_name or ''}"
    now = time.time()
    if cache_key in _WEATHER_CACHE:
        exp, cached = _WEATHER_CACHE[cache_key]
        if exp > now:
            cached_copy = dict(cached)
            cached_copy["from_cache"] = True
            return cached_copy

    # --- 4) 调用高德 API ---
    import httpx
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.get(
                cfg.base_url,
                params={
                    "key": cfg.api_key.strip(),
                    "city": adcode,
                    "extensions": "base",
                    "output": "JSON",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"[weather_tool] 高德 API 调用失败: {e}")
        return {
            "ok": False,
            "region": region_name or adcode,
            "temperature": None,
            "weather": "",
            "humidity": "",
            "diet_hints": [],
            "fallback_reason": f"天气服务暂时不可用({type(e).__name__})，已跳过天气适配",
        }

    # --- 5) 解析高德响应 ---
    try:
        if str(data.get("status")) != "1":
            raise ValueError(f"status={data.get('status')}, info={data.get('info')}")
        lives = data.get("lives") or []
        if not lives:
            raise ValueError("lives 数组为空")
        live = lives[0]
        temperature = float(live.get("temperature") or 0)
        humidity_pct = int(live.get("humidity") or 0)
        weather_str = live.get("weather") or ""
        result = {
            "ok": True,
            "from_cache": False,
            "region": live.get("city") or region_name or "",
            "city_adcode": live.get("adcode") or adcode,
            "province": live.get("province") or "",
            "temperature": temperature,
            "weather": weather_str,
            "wind_direction": live.get("winddirection") or "",
            "wind_power": live.get("windpower") or "",
            "humidity": live.get("humidity") or "",
            "report_time": live.get("reporttime") or "",
            "diet_hints": _gen_diet_hints(temperature, weather_str, humidity_pct),
            "fallback_reason": "",
        }
    except Exception as e:
        logger.warning(f"[weather_tool] 高德响应解析失败: {e}, raw={data}")
        return {
            "ok": False,
            "region": region_name or adcode,
            "temperature": None,
            "weather": "",
            "humidity": "",
            "diet_hints": [],
            "fallback_reason": f"天气数据解析异常({type(e).__name__})，已跳过天气适配",
        }

    # --- 6) 写缓存并返回 ---
    _WEATHER_CACHE[cache_key] = (now + cfg.cache_ttl_seconds, result)
    return result


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("天气工具自测开始（无 API Key 时会自动降级）")
    print("=" * 60)

    # 测试1：adcode 查找
    assert _adcode_lookup("杭州") == "330100"
    assert _adcode_lookup("杭州市") == "330100"
    assert _adcode_lookup("北京") == "110000"
    assert _adcode_lookup("不存在的城市") is None
    print("[通过] 测试1 - adcode 查找: 精确+模糊匹配正确")

    # 测试2：膳食提示生成
    hints = _gen_diet_hints(35, "晴", 40)
    assert any("炎热" in h for h in hints)
    assert any("清热消暑" in h for h in hints)
    print(f"[通过] 测试2 - 热天提示: {len(hints)} 条")

    hints = _gen_diet_hints(3, "小雪", 85)
    assert any("寒冷" in h for h in hints)
    assert any("祛湿" in h for h in hints)
    print(f"[通过] 测试3 - 冷天+雨提示: {len(hints)} 条")

    # 测试4：无 API Key 降级
    import asyncio
    r = asyncio.run(weather_tool.ainvoke({"region_name": "杭州"}))
    assert r["ok"] is False
    assert "未配置" in r["fallback_reason"]
    print(f"[通过] 测试4 - 无 Key 降级: {r['fallback_reason']}")

    print("=" * 60)
    print("天气工具自测完成（4/4）")
