import configparser
import re
import json
import math
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from bangumi_api import BangumiAPIClient

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def format_file_size(size_bytes: int) -> str:
    '''将字节大小格式化为更易读的字符串表示
    size_bytes: 文件大小，单位为字节
    返回格式化后的字符串，例如 "1.23 GB"
    '''
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def clean_filename(filename: str) -> str:
    '''清理文件名，移除非法字符并规范化空格'''
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', filename)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned

class MediaManager:
    '''用于管理和处理媒体文件的类'''
    def __init__(self, config_path: str = 'config.ini'):
        '''初始化 MediaManager 实例，加载配置和正则表达式模式'''
        self.config = self._load_config(config_path)
        self.patterns = self._load_patterns(self.config['Settings']['regex_file'])
        self.api_client = BangumiAPIClient()
        self._api_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        # 用于中文数字转换
        self.cn_num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        '''加载配置文件'''
        config_file = Path(config_path)
        if not config_file.exists():
            logging.error(f"配置文件 '{config_path}' 不存在。")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        config = configparser.ConfigParser()
        config.read(config_file, encoding='utf-8')
        return config

    def _load_patterns(self, regex_path: str) -> Dict[str, Any]:
        '''加载正则表达式模式文件'''
        try:
            with open(regex_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"加载正则表达式文件 '{regex_path}' 失败: {e}")
            raise

    ### 重点改动: 完全重构 parse_filename 函数 ###
    def parse_filename(self, filename: str) -> Dict[str, Any]:
        """
        使用更智能的策略解析文件名。
        1. 优先提取括号内的元数据。
        2. 专门处理标题和季数组合的复杂情况。
        3. 最后清理剩余部分作为标题。
        """
        info = {'字幕组': None, '标题': None, '季数': None, '集数': None, '分辨率': None, '视频编码': None, '音频编码': None, '字幕': None, '备注': []}
        work_str = filename

        # 预先提取所有括号内容，方便后续处理
        bracket_content = re.findall(r'[\[【](.*?)[\]】]', work_str)
        
        # 步骤 1: 优先解析最关键的 "标题+季数" 组合, e.g., "[Spy x Family Season 3]"
        # 这个模式通常包含了最准确的标题和季数信息
        title_season_match = re.search(r'\[([^\]]*?)\s*[Ss]eason\s*(\d+)\]', work_str, re.IGNORECASE)
        if title_season_match:
            info['标题'] = title_season_match.group(1).strip()
            info['季数'] = title_season_match.group(2).strip()
            # 从工作字符串中移除已解析的部分，防止干扰
            work_str = work_str.replace(title_season_match.group(0), '', 1)

        # 步骤 2: 解析括号内的其他元数据
        tech_keys = {'resolution': '分辨率', 'source': '备注', 'video_codec': '视频编码', 'audio_codec': '音频编码', 'subtitle': '字幕', 'group': '字幕组'}
        
        temp_work_str = work_str
        for content_block in re.finditer(r'[\[【](.*?)[\]】]', work_str):
            content = content_block.group(1)
            matched = False
            for key, field in tech_keys.items():
                pattern = self.patterns.get(key)
                if not pattern: continue
                
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = (match.group(1) or match.group(0)).strip()
                    if key == 'source': info['备注'].append(value)
                    elif info[field] is None: # 避免覆盖
                        info[field] = value
                    
                    matched = True
                    break
            if matched:
                temp_work_str = temp_work_str.replace(content_block.group(0), '', 1)
        work_str = temp_work_str
        
        # 步骤 3: 从剩余的字符串中解析集数和季数 (如果之前没找到)
        if info['集数'] is None:
            se_match = re.search(self.patterns.get('season_episode', ''), work_str, re.IGNORECASE)
            if se_match:
                if info['季数'] is None: info['季数'] = str(int(se_match.group(1)))
                info['集数'] = f"{int(se_match.group(2)):02d}"
                work_str = work_str.replace(se_match.group(0), '', 1)
            else:
                ep_match = re.search(self.patterns.get('episode', ''), work_str, re.IGNORECASE)
                if ep_match:
                    info['集数'] = f"{int(ep_match.group(1)):02d}"
                    work_str = work_str.replace(ep_match.group(0), '', 1)

        # 步骤 4: 清理并确定最终标题
        if info['标题'] is None:
            title = re.sub(r'[\[【].*?[】\]]', '', work_str).strip()
            title = re.sub(r'[\s._-]+', ' ', title).strip()
            info['标题'] = title if title else "Unknown Title"
        
        # 步骤 5: 设置默认值和格式化
        if info['季数'] is None: info['季数'] = '1'
        info['备注'] = ', '.join(info['备注']) or None
        
        return info

    def _get_bangumi_details(self, title: str, season: Optional[str]) -> Optional[Dict[str, Any]]:
        '''使用标题和季数从 Bangumi API 获取详细信息，带缓存
        title: 解析出的标题
        season: 解析出的季数
        返回包含番剧详细信息的字典，或 None 如果未找到
        '''
        api_query = f"{title} Season {season}" if season and season != '1' else title
        if api_query in self._api_cache:
            logging.info(f"命中缓存: '{api_query}'")
            return self._api_cache[api_query]
        details = self.api_client.get_details_for_scraping(api_query)
        self._api_cache[api_query] = details
        return details

    def create_hard_link(self, source_path: Path, media_info: Dict[str, Any]):
        '''创建硬链接到指定目录，使用配置的命名模板
        source_path: 原始文件路径
        media_info: 解析出的媒体信息字典
        '''
        cfg = self.config['HardLink']
        dest_dir = Path(cfg['destination_directory'])
        template = cfg['filename_template']
        
        title = media_info.get('标题') or 'Unknown Title'
        season = media_info.get('季数') or '1'

        template_data = {
            'title': title,
            'season': season,
            'episode': media_info.get('集数') or '00',
            'resolution': media_info.get('分辨率') or '',
            'group': media_info.get('字幕组') or '',
            'source': media_info.get('备注') or '',
            'ext': source_path.suffix.lstrip('.'),
            'bangumi_eps': media_info.get('bangumi_eps') or ''
        }
        
        try:
            new_filename = clean_filename(template.format(**template_data))
            link_dir = dest_dir / clean_filename(title) / f'Season {season}'
            link_dir.mkdir(parents=True, exist_ok=True)
            dest_path = link_dir / new_filename

            if dest_path.exists():
                logging.warning(f"  > 文件已存在，跳过: {dest_path.name}")
                return
            
            os.link(source_path, dest_path)
            logging.info(f"  > 成功创建硬链接: {dest_path.name}")

        except KeyError as e:
            logging.error(f"  > 模板格式化错误: 配置文件中的模板使用了未知的占位符 {e}")
        except OSError as e:
             logging.error(f"  > 创建硬链接失败: {e}")

    ### 升级主处理流程 ###
    def process_directory(self):
        cfg = self.config['Settings']
        scan_dir = Path(cfg['directory_to_scan'])
        formats = tuple(f.strip() for f in cfg['supported_formats'].split(','))
        link_enabled = self.config['HardLink'].getboolean('enabled')

        if not scan_dir.is_dir():
            logging.error(f"配置目录不存在: {scan_dir}")
            return
            
        logging.info(f"开始扫描目录: {scan_dir}")
        media_files = (p for p in scan_dir.rglob('*') if p.name.lower().endswith(formats))
        
        total_files = 0
        for file_path in media_files:
            total_files += 1
            logging.info("-" * 50)
            logging.info(f"处理: {file_path.name}")
            media_info = self.parse_filename(file_path.stem)
            
            if media_info.get('标题') and media_info['标题'] != 'Unknown Title':
                # 使用解析出的信息进行API查询
                bangumi_details = self._get_bangumi_details(media_info['标题'], media_info.get('季数'))
                
                if bangumi_details:
                    api_title = bangumi_details.get('name_cn', media_info['标题'])
                    
                    # --- 智能季数修正逻辑 ---
                    # 如果解析出的季数是默认的'1'，尝试从API标题中获取更准确的季数
                    if media_info.get('季数') == '1':
                        season_match = re.search(r'第([一二三四五六七八九十])季', api_title)
                        if season_match:
                            cn_season = season_match.group(1)
                            if cn_season in self.cn_num_map:
                                media_info['季数'] = str(self.cn_num_map[cn_season])
                                logging.info(f"  > 根据API标题修正季数为: Season {media_info['季数']}")

                    # 清理API标题中的季数信息，得到干净的剧集名
                    clean_title = re.sub(r'\s*第[一二三四五六七八九十]季', '', api_title).strip()
                    media_info['标题'] = clean_title
                    media_info['bangumi_eps'] = bangumi_details.get('total_episodes', '??')

            if link_enabled:
                self.create_hard_link(file_path, media_info)

        logging.info("=" * 50)
        logging.info(f"处理完成！共找到 {total_files} 个媒体文件。")

def main():
    try:
        MediaManager().process_directory()
    except Exception:
        logging.critical("程序遇到致命错误崩溃:", exc_info=True)

if __name__ == "__main__":
    main()