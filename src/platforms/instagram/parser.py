import json
from pprint import pprint

from parsel import Selector

from src.platforms.core.helpers import get_dict_by_marker_key
from src.platforms.instagram.exceptions import InstagramParserException
from src.platforms.core.schemas import Audio, Post, Video


class InstagramParser:
    SCRIPTS_XPATH = '//script[@type="application/json"]/text()'


    def _get_videos(self, json_data: dict) -> list[Video]:
        videos = []
        for item in json_data["video_versions"]:
            videos.append(
                Video(
                    url=item["url"],
                )
            )
    def parse(self, content: str):
        tree = Selector(content)

        if not tree:
            raise InstagramParserException("Tree not found.")

        scripts = tree.xpath(self.SCRIPTS_XPATH)

        if not scripts:
            raise InstagramParserException("Scripts not found.")

        for script in scripts:
            text = script.get().strip()
            if "video_versions" in text:
                json_data = json.loads(text)
                json_data = get_dict_by_marker_key(obj=json_data, marker_key="video_versions", return_parent_dict=True)
