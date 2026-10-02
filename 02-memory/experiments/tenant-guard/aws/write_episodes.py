# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#2 補充：A、B 各寫 2 段「有明確結尾」的對話，讓 episodic 判定 episode 完成、產出 reflection。

write_events.py 的重複提問一直沒被判定為完成的 episode。每個 event 間隔 2 秒，
避免一次寫太快觸發 LTM_RATE_EXCEEDED（見 README）。
"""
import time
from datetime import datetime, timezone

from common import ACTORS, client, load_state

DIALOG = {
    "A": [("USER", "幫我訂京都祇園附近的日式旅館，十一月中、兩晚、一晚一萬五日圓以內。我的訂房暗號是 ALPHA-7731。"),
          ("ASSISTANT", "找到祇園白川旁的「花見小路庵」，一晚一萬四千日圓，有空房。要用暗號 ALPHA-7731 幫你預訂嗎？"),
          ("USER", "好，訂吧。另外推薦一家湯豆腐，我不吃生魚片。"),
          ("ASSISTANT", "已完成預訂，確認編號 KY-20261115。湯豆腐推薦南禪寺的「順正」，看完楓葉順路。"),
          ("USER", "太好了，謝謝，京都行程就這樣定案。")],
    "B": [("USER", "幫我租冰島的露營車，明年二月、十四天，要能追極光。我的租車暗號是 BRAVO-4402。"),
          ("ASSISTANT", "找到雷克雅維克的 4x4 露營車，十四天約 2,100 歐元，附暖氣。要用暗號 BRAVO-4402 幫你預訂嗎？"),
          ("USER", "好，訂吧。我對海鮮過敏，順便幫我訂藍湖溫泉。"),
          ("ASSISTANT", "露營車已預訂，確認編號 IS-20260210。藍湖溫泉訂在第一天傍晚，餐點已註記海鮮過敏。"),
          ("USER", "完美，謝謝，冰島行程就這樣定案。")],
}

st = load_state()
dp = client("bedrock-agentcore")
for user, actor in ACTORS.items():
    for k in range(2):
        sid = f"wp5-{user.lower()}-done{k}"
        for role, text in DIALOG[user]:
            dp.create_event(memoryId=st["memoryId"], actorId=actor, sessionId=sid, eventTimestamp=datetime.now(timezone.utc),
                            payload=[{"conversational": {"role": role, "content": {"text": text}}}])
            time.sleep(2)
        print(user, sid, "ok", flush=True)
