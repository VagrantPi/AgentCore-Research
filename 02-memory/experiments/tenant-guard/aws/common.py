"""WP5 實測共用設定：東京、tag、使用者 A／B 的 actorId 與測試內容。"""
import json
import pathlib

import boto3

REGION = "ap-northeast-1"
ACCOUNT = "050571774557"
TAGS = {"wp": "WP5", "owner": "kais", "project": "hyfai"}
ACTORS = {"A": "wp5-user-a", "B": "wp5-user-b"}
STATE = pathlib.Path(__file__).with_name("state.json")   # memoryId、strategyId 等執行期的值，不 commit

# 兩人都在聊「旅遊」，但細節不同，用關鍵字判斷有沒有混到對方的內容
TOPICS = {
    "A": ("京都", ["我下個月要去京都看楓葉，想住在祇園附近", "我偏好安靜的日式旅館，不喜歡大型飯店",
                   "我不吃生魚片，請推薦京都的湯豆腐店", "我想去伏見稻荷大社，早上幾點人比較少？",
                   "我預算一晚一萬五日圓以內"]),
    "B": ("冰島", ["我明年二月要去冰島看極光，打算自駕環島", "我喜歡露營車，不想住飯店",
                   "我對海鮮過敏，冰島有什麼素食餐廳？", "藍湖溫泉需要提前多久預約？",
                   "我的預算是兩週二十萬台幣"]),
}

# reflection 會被抽象化（英文、去掉地名），只比地名太弱；用多個專屬特徵詞判斷有沒有混到對方
MARKERS = {
    "A": ["京都", "Kyoto", "祇園", "Gion", "湯豆腐", "tofu", "伏見", "Fushimi", "楓", "maple", "ALPHA-7731"],
    "B": ["冰島", "Iceland", "極光", "aurora", "露營車", "camper", "藍湖", "Blue Lagoon", "海鮮過敏", "BRAVO-4402"],
}


COST3D = pathlib.Path(__file__).with_name("cost3d-resources.json")   # 3 天版的資源 ID，有 commit


def load_state():
    """state.json 的值優先；沒有的鍵（例如換了電腦）從 cost3d-resources.json 補。"""
    base = json.loads(COST3D.read_text()) if COST3D.exists() else {}
    return base | (json.loads(STATE.read_text()) if STATE.exists() else {})


def save_state(**kw):
    s = load_state() | kw
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    return s


def client(name, creds=None):
    if creds:
        return boto3.client(name, region_name=REGION, aws_access_key_id=creds["AccessKeyId"],
                            aws_secret_access_key=creds["SecretAccessKey"], aws_session_token=creds["SessionToken"])
    return boto3.client(name, region_name=REGION)
