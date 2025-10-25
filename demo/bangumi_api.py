import requests
import time
import logging
from typing import Dict, Any, List, Optional

# --- 常量定义 ---
API_BASE_URL = "https://api.bgm.tv"
HEADERS = {
    'User-Agent': 'MediaManager/2.0 (https://github.com/your_repo; your_email@example.com)'
}

# --- 自定义异常 ---
class APIError(Exception):
    """表示一般的 API 错误"""
    pass

class NetworkError(APIError):
    """表示网络连接或请求超时错误"""
    pass

class NotFoundError(APIError):
    """表示 API 返回 404，资源未找到"""
    pass

# --- API 客户端类 ---
class BangumiAPIClient:
    """用于与 Bangumi API 交互的客户端"""

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        self._session.headers.update(HEADERS)
        self.log = logging.getLogger(__name__)

    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        发起 GET 请求并处理常见的网络和 HTTP 错误。
        """
        try:
            time.sleep(0.5) # 简单的速率限制
            response = self._session.get(url, params=params, timeout=10) # 添加超时
            if response.status_code == 404:
                raise NotFoundError(f"资源未找到: {url}")
            if response.status_code >= 400:
                 self.log.debug(f"API Error Response: {response.text}") # 记录详细错误信息以便调试
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise APIError(f"API 请求失败, 状态码 {e.response.status_code} at {url}") from e
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"网络连接失败 at {url}: {e}") from e

    def search_subject(self, term: str) -> Optional[Dict[str, Any]]:
        self.log.info(f"正在通过 API 搜索: '{term}'...")
        search_url = f"{API_BASE_URL}/search/subject/{term}"
        params = {'type': 2, 'responseGroup': 'small'} # 使用 small 减少数据量
        try:
            data = self._make_request(search_url, params=params)
            if data and data.get('list'):
                first_result = data['list'][0]
                self.log.info(f"  => 找到 '{first_result.get('name_cn') or first_result.get('name')}', ID: {first_result['id']}")
                return first_result
            self.log.warning(f"  => 未找到关于 '{term}' 的任何结果。")
            return None
        except (NotFoundError, IndexError, KeyError) as e:
            self.log.error(f"解析搜索结果失败: {e}")
            return None

    def get_subject_details(self, subject_id: int) -> Dict[str, Any]:
        self.log.info(f"正在获取番剧详情 (ID: {subject_id})...")
        subject_url = f"{API_BASE_URL}/v0/subjects/{subject_id}"
        return self._make_request(subject_url)

    def get_episodes(self, subject_id: int) -> List[Dict[str, Any]]:
        self.log.info(f"正在获取详细分集信息 (ID: {subject_id})...")
        episodes_url = f"{API_BASE_URL}/v0/episodes"
        params = {'subject_id': subject_id}
        # --- 修复: 之前忘记传递 params ---
        data = self._make_request(episodes_url, params=params)
        return data.get('data', [])

    def get_details_for_scraping(self, search_term: str) -> Optional[Dict[str, Any]]:
        search_result = self.search_subject(search_term)
        if not search_result or 'id' not in search_result:
            return None

        bangumi_id = search_result['id']
        
        try:
            details = self.get_subject_details(bangumi_id)
            all_episodes = self.get_episodes(bangumi_id)

            episodes_list = [
                {
                    "sort": ep.get('sort'),
                    "name_cn": ep.get('name_cn'),
                    "name": ep.get('name'),
                    "airdate": ep.get('airdate'),
                    "desc": ep.get('desc', '')
                }
                for ep in all_episodes if ep.get('type') == 0
            ]
            self.log.info(f"  => 成功获取 {len(episodes_list)} 话本篇剧集的详细信息。")

            return {
                "bangumi_id": bangumi_id,
                "name_cn": details.get('name_cn') or details.get('name', '未知'),
                "name_jp": details.get('name', '未知'),
                "year": (details.get('date') or '未知')[:4],
                "total_episodes": details.get('eps_count') or details.get('eps', 0),
                "episodes": episodes_list,
                "summary": details.get('summary', '未知'),
                "image": details.get('images', {}).get('large', '')
            }
        except APIError as e:
            self.log.error(f"获取番剧 (ID: {bangumi_id}) 详情时出错: {e}")
            return None