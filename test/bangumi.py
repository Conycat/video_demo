import requests
from bs4 import BeautifulSoup
import re
import time
'''
    已停止使用，改为使用 bangumi_api.py 中的 get_bangumi_details_for_scraping 函数
'''
def search_anime_and_get_id(search_term):
    """
    功能一：根据搜索词在 Bangumi 搜索，并获取第一个结果的中文名和 ID。
    
    Args:
        search_term (str): 用户输入的搜索关键词。

    Returns:
        dict: 包含 'chinese_name' 和 'bangumi_id' 的字典，如果找不到则返回 None。
    """
    search_url = f"https://bgm.tv/subject_search/{search_term}?cat=2"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        print(f"\n正在搜索: '{search_term}'...")
        time.sleep(0.5)
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')
        first_result = soup.find('li', class_='item')

        if not first_result:
            print("错误: 未找到任何条目。")
            return None

        # 提取中文名称
        name_tag = first_result.find('a', class_='l')
        chinese_name = name_tag.text.strip() if name_tag else "未知"

        # 提取 Bangumi ID
        bgm_id_raw = first_result.get('id')
        bgm_id = bgm_id_raw.replace('item_', '') if bgm_id_raw else None
        
        if not bgm_id:
            print("错误: 未能解析出 Bangumi ID。")
            return None
        
        print(f"找到 '{chinese_name}', ID: {bgm_id}")
        return {"chinese_name": chinese_name, "bangumi_id": bgm_id}

    except requests.exceptions.RequestException as e:
        print(f"错误: 网络请求失败: {e}")
        return None


def scrape_episode_count(bangumi_id):
    """
    功能二：访问番剧的详情页，并抓取其总话数。

    Args:
        bangumi_id (str): 番剧的 Bangumi ID。

    Returns:
        str: 话数字符串，如果找不到则返回 '未知'。
    """
    if not bangumi_id:
        return "未知"
        
    subject_url = f"https://bgm.tv/subject/{bangumi_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        print(f"({bangumi_id}) 查询详情页...")
        time.sleep(0.5)
        response = requests.get(subject_url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        # 话数信息在 id="infobox" 的 ul 标签内
        infobox = soup.find('ul', id='infobox')
        if not infobox:
            print("未找到信息")
            return "未知"
        
        # 精准查找包含“话数:”文本的 <span> 标签
        # 使用 re.compile 确保能匹配到 '话数:'，忽略前后可能存在的空格
        episode_tip_span = infobox.find('span', class_='tip', string=re.compile(r'^\s*话数:\s*$'))

        if episode_tip_span:
            # 清理
            parent_li_text = episode_tip_span.parent.get_text()

            match = re.search(r'(\d+)', parent_li_text)
            if match:
                print(f"找到话数: {match.group(1)}")
                return match.group(1)

        print("未找到“话数”信息。")
        return "未知"

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        return "未知"


def get_bangumi_details(search_term):
    """
    功能三：调度函数，整合搜索和详情抓取两个步骤。

    Args:
        search_term (str): 番剧的名称。

    Returns:
        str: 返回一个元组，该元组包括以下key : value。
            'chinese_name' = '地。 ―关于地球的运动―'
            'bangumi_id' = '389156'
            'episodes' = '25'
    """
    search_result = search_anime_and_get_id(search_term)
    
    if not search_result:
        return None
    
    bangumi_id = search_result['bangumi_id']
    episode_count = scrape_episode_count(bangumi_id)
    
    search_result['episodes'] = episode_count
    
    return search_result