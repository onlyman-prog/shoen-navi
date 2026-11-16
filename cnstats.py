"""中国版公式ランク戦データ(第五人格游戏数据查询 / web.homeworkkun.top)を取得する。

- マップ別: シーズン合計のハンター勝率・引き分け率・敗北率 (全段位 / 巅峰七阶)
- キャラ別: 勝率・引き分け率・使用率・BAN率 (全段位 / 巅峰七阶)
※ 中国サーバーのデータ。日本サーバーとは環境が少し違うことがある。
"""
import json
import re
import urllib.parse
import urllib.request

BASE = "https://web.homeworkkun.top/" + urllib.parse.quote("胜率数据") + "/"
PAGE = BASE + "map.html"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

MAP_JA = {
    "军工厂": "軍需工場", "红教堂": "赤の教会", "圣心医院": "聖心病院", "湖景村": "湖景村", "月亮河公园": "月の河公園",
    "里奥的回忆": "レオの思い出", "永眠镇": "永眠町", "唐人街": "中華街", "不归林": "罪の森",
    "克雷伯格赛马场": "クレイバーグ競馬場", "白沙街疯人院": "ホワイトサンド精神病院", "闪金石窟": "黄金の石窟",
}
CHAR_JA = {
    # ハンター
    "厂长": "復讐者", "小丑": "道化師", "鹿头": "断罪狩人", "杰克": "リッパー", "蜘蛛": "結魂者", "红蝶": "芸者",
    "宿伞之魂": "白黒無常", "摄影师": "写真家", "疯眼": "狂眼", "黄衣之主": "黄衣の王", "梦之女巫": "夢の魔女",
    "爱哭鬼": "泣き虫", "孽蜥": "魔トカゲ", "红夫人": "血の女王", "26号守卫": "ガードNo.26", "使徒": "「使徒」",
    "小提琴家": "ヴァイオリニスト", "雕刻家": "彫刻師", "博士": "「アンデッド」", "破轮": "破輪", "渔女": "漁師",
    "蜡像师": "蝋人形師", "噩梦": "「悪夢」", "记录员": "書記官", "隐士": "隠者", "守夜人": "夜の番人",
    "歌剧演员": "オペラ歌手", "愚人金": "「フールズ・ゴールド」", "时空之影": "時空の影", "跛脚羊": "「足萎えの羊」",
    "喧嚣": "「フラバルー」", "杂货商": "雑貨商", "台球手": "「ビリヤードプレイヤー」", "女王蜂": "「女王蜂」",
    "牙医": "「歯医者」", "心兽": "「心の獣」",
    # サバイバー
    "幸运儿": "幸運児", "医生": "医師", "律师": "弁護士", "慈善家": "泥棒", "园丁": "庭師", "魔术师": "マジシャン",
    "冒险家": "冒険家", "佣兵": "傭兵", "祭司": "祭司", "空军": "空軍", "机械师": "機械技師", "前锋": "オフェンス",
    "盲女": "心眼", "调香师": "調香師", "牛仔": "カウボーイ", "舞女": "踊り子", "先知": "占い師", "入殓师": "納棺師",
    "勘探员": "探鉱者", "咒术师": "呪術師", "野人": "野人", "杂技演员": "曲芸師", "大副": "一等航海士",
    "调酒师": "バーメイド", "邮差": "ポストマン", "守墓人": "墓守", "囚徒": "「囚人」", "昆虫学者": "昆虫学者",
    "画家": "画家", "击球手": "バッツマン", "玩具商": "玩具職人", "病患": "患者", "心理学家": "「心理学者」",
    "小说家": "小説家", "小女孩": "「少女」", "哭泣小丑": "泣きピエロ", "教授": "教授", "古董商": "骨董商",
    "作曲家": "作曲家", "记者": "記者", "飞行家": "航空エンジニア", "拉拉队员": "応援団", "木偶师": "人形師",
    "火灾调查员": "火災調査員", "法罗女士": "「レディ・ファウロ」", "骑士": "「騎士」", "气象学家": "気象学者",
    "弓箭手": "弓使い", "逃脱大师": "「脱出マスター」", "幻灯师": "幻灯師", "斗牛士": "闘牛士",
    "默剧艺人": "マイムアーティスト", "神童": "「神童」",
}


def _get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _pct(v):
    return round(float(v or 0), 1)


def fetch_maps():
    files = json.loads(_get("map/mapdata.json"))
    data = json.loads(_get("map/" + files[-1]))["data"]
    out, period = {}, ""
    for r in data:
        if r["week_num"] != "-127" or r["camp_id"] != 1:
            continue  # シーズン合計・ハンター側の行だけ使う
        ja = MAP_JA.get(r["space_name"])
        if not ja:
            continue
        key = "all" if r["part"] == -127 else "top" if r["part"] == 8 else None
        if key:
            out.setdefault(ja, {})[key] = [_pct(r["win_rate"]), _pct(r["ping_rate"]), _pct(r["fail_rate"])]
            period = f'{r["start_time"]}-{r["end_time"]}'
    season = re.sub(r"\D", "", files[-1])
    return {"season": season, "period": period, "maps": out}


def fetch_chars():
    js = _get("js/season.js")
    latest = re.search(r'latestSeason\s*=\s*"([^"]+)"', js).group(1)
    fname = re.search(rf'"{re.escape(latest)}"\s*:\s*"([^"]+)"', js).group(1)
    data = json.loads(_get("json/" + fname))["data"]
    out, period = {}, ""
    for r in data:
        if r["week_num"] != "-127":
            continue
        ja = CHAR_JA.get(r["name"])
        key = "all" if r["part"] == -127 else "top" if r["part"] == 8 else None
        if not ja or not key:
            continue
        out.setdefault(ja, {})[key] = {
            "win": round(r["win_rate"] * 100, 1), "draw": round((r["ping_rate"] or 0) * 100, 1),
            "use": round((r["use_rate"] or 0) * 100, 2), "ban": round((r["ban_rate"] or 0) * 100, 1),
        }
        period = f'{r["start_time"]}-{r["end_time"]}'
    return {"season": re.sub(r"\D", "", latest), "period": period, "chars": out}


def build():
    res = {"source": "第五人格游戏数据查询(中国版公式データ)", "url": PAGE}
    try:
        res["map"] = fetch_maps()
    except Exception as e:
        res["mapError"] = str(e)
    try:
        res["char"] = fetch_chars()
    except Exception as e:
        res["charError"] = str(e)
    return res


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    print(r.get("map", {}).get("season"), r.get("map", {}).get("period"))
    for k, v in sorted(r["map"]["maps"].items(), key=lambda x: x[1]["all"][0] - x[1]["all"][2]):
        print(k, v)
    c = r["char"]["chars"]
    print(r["char"]["season"], r["char"]["period"], len(c))
    for n in ["「女王蜂」", "オペラ歌手", "時空の影", "傭兵", "占い師", "弓使い"]:
        print(n, c.get(n))
