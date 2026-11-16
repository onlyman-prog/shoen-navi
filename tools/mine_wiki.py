"""wikiwiki のキャラページ/対策ページから、相手キャラ・マップ名と有利不利表現を含む文を抜き出す。"""
import glob, html, json, re, sys
sys.stdout.reconfigure(encoding="utf-8")
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "data", "cache.json"), encoding="utf-8"))
CH = D["chars"]
SIDE = {n: c["side"] for n, c in CH.items()}
# 呼び名 (公式名 + 定着している愛称/略称。曖昧なものは入れない)
ALIAS = {
    "写真家": ["ジョゼフ"], "芸者": ["美智子", "ミチコ"], "白黒無常": ["白黒"], "黄衣の王": ["ハスター"],
    "結魂者": ["蜘蛛"], "断罪狩人": ["鹿"], "ガードNo.26": ["26号", "ボンボン"], "「使徒」": ["使徒"],
    "血の女王": ["マリー"], "彫刻師": ["ガラテア"], "破輪": ["車輪"], "漁師": ["グレイス"], "書記官": ["キーガン"],
    "夜の番人": ["イタカ"], "「アンデッド」": ["アンデッド", "ペルシー"], "「悪夢」": ["悪夢"], "時空の影": ["アイビー"],
    "「足萎えの羊」": ["足萎えの羊", "羊"], "「フラバルー」": ["フラバルー"], "「ビリヤードプレイヤー」": ["ビリヤードプレイヤー", "ビリプレ"],
    "「女王蜂」": ["女王蜂"], "「歯医者」": ["歯医者"], "「心の獣」": ["心の獣"], "「フールズ・ゴールド」": ["フールズ・ゴールド", "フールズゴールド"],
    "復讐者": ["レオ"], "道化師": ["ピエロ"], "泣き虫": ["ロビー"], "魔トカゲ": ["ルキノ"],
    "傭兵": ["ナワーブ"], "空軍": ["マーサ"], "祭司": ["フィオナ"], "機械技師": ["トレイシー"], "オフェンス": ["ウィリアム"],
    "心眼": ["ヘレナ"], "調香師": ["ウィラ"], "占い師": ["イライ"], "納棺師": ["イソップ"], "探鉱者": ["ノートン"],
    "呪術師": ["パトリシア"], "野人": ["ムルソー"], "一等航海士": ["航海士"], "バーメイド": ["デミ"], "ポストマン": ["ビクター"],
    "墓守": ["アンドルー"], "「囚人」": ["囚人", "ルカ"], "昆虫学者": ["メリー"], "画家": ["エドガー"], "バッツマン": ["ガンジ"],
    "玩具職人": ["アニー"], "患者": ["エミール"], "「心理学者」": ["心理学者", "エイダ"], "小説家": ["オルフェウス"],
    "「少女」": ["少女"], "教授": [], "骨董商": [], "記者": [], "航空エンジニア": ["エンジニア"], "応援団": [],
    "人形師": [], "火災調査員": [], "「レディ・ファウロ」": ["レディ・ファウロ", "ファウロ"], "「騎士」": ["騎士"],
    "気象学者": [], "弓使い": [], "「脱出マスター」": ["脱出マスター"], "幻灯師": [], "闘牛士": [], "マイムアーティスト": ["マイム"],
    "「神童」": ["神童"], "医師": ["エミリー"], "弁護士": ["フレディ"], "庭師": ["エマ"], "マジシャン": ["セルヴェ"],
    "冒険家": ["カート"], "カウボーイ": ["カヴィン"], "踊り子": ["マルガレータ"], "曲芸師": ["マイク"], "泣きピエロ": [],
    "作曲家": [], "幸運児": [], "泥棒": [],
}
MAPS = ["軍需工場", "赤の教会", "聖心病院", "湖景村", "月の河公園", "レオの思い出", "永眠町", "中華街", "罪の森",
        "クレイバーグ競馬場", "ホワイトサンド精神病院", "黄金の石窟"]
MAP_ALIAS = {"軍需工場": ["軍需", "工場マップ"], "赤の教会": ["教会"], "聖心病院": ["病院"], "湖景村": [], "月の河公園": ["月の河", "公園"],
             "レオの思い出": ["レオ思", "レオの思"], "永眠町": [], "中華街": [], "罪の森": [], "クレイバーグ競馬場": ["競馬場"],
             "ホワイトサンド精神病院": ["精神病院"], "黄金の石窟": ["石窟"]}

def terms(n):
    base = n.strip("「」")
    return sorted({base, *ALIAS.get(n, [])}, key=len, reverse=True)

POS = r"(有利|得意|強い|強く|刺さ|カモ|相性が(良|い)|相性(は|も)?(良|いい)|完封|メタ|対抗(でき|しやす)|楽|一方的|圧倒|ぶっ刺)"
NEG = r"(不利|苦手|弱い|弱く|キツい|きつい|厳しい|相性が悪|相性(は|も)?悪|天敵|辛い|つらい|苦戦|勝てない|分が悪|メタられ|対策され)"

def body_text(path):
    s = open(path, encoding="utf-8").read()
    i = s.find('id="body"'); s = s[i:]
    m = re.search(r"<h[23][^>]*>[^<]*(<[^>]+>)*\s*コメント欄", s)
    if m: s = s[:m.start()]
    j = s.find('id="menubar"')
    if j > 0: s = s[:j]
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    s = re.sub(r"<img[^>]*alt=\"([^\"]*)\"[^>]*>", r"\1", s)
    s = re.sub(r"<(br|tr|li|p|div|h\d)[^>]*>", "\n", s); s = re.sub(r"</t[dh]>", "。", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"[ \t\u3000]+", " ", s)

def sentences(t):
    for line in t.split("\n"):
        for x in re.split(r"(?<=[。！？!?])", line):
            x = x.strip()
            if 6 <= len(x) <= 260: yield x

ALLTERMS = None
def _skip_chain(sent, pos):
    """「A・B・Cに有利」の並列を飛ばして、最後の名前の後ろの位置を返す"""
    global ALLTERMS
    if ALLTERMS is None:
        ALLTERMS = sorted({t for n in CH for t in terms(n)}, key=len, reverse=True)
    while True:
        m = re.match(r"(・|、|や|と|,|／|/)", sent[pos:])
        if not m: return pos
        nxt = pos + m.end()
        hit = next((t for t in ALLTERMS if sent.startswith(t, nxt)), None)
        if not hit: return pos
        pos = nxt + len(hit)
        q = re.match(r"」|など", sent[pos:])
        if q: pos += q.end()

def classify(sent, term, kind="main"):
    """返り値: '+' = このページのキャラが term に強い / '-' = 弱い"""
    out = []
    for m in re.finditer(re.escape(term), sent):
        end = _skip_chain(sent, m.end())
        tail = sent[end: end + 24]
        head = sent[max(0, m.start() - 14): m.start()]
        if kind == "taisaku":
            ni = re.match(r"」?(など|等)?[^。]{0,12}?(に|には|に対して|に対しては|相手だと|相手では)", tail)
            if ni and (re.match(r"(よ|とって|とり|なっ|なる)", tail[ni.end():])
                       or re.search(r"[はがも]|(非常|特|的|常|更|既|逆|実)$", tail[:ni.start(2)])): ni = None
            if ni and re.match(r"[^。]{0,4}" + NEG, tail[ni.end():]): out.append("-"); continue
            if ni and re.match(r"[^。]{0,4}" + POS, tail[ni.end():]): out.append("+"); continue
            # 対策ページ: 相手 Y についての記述。Y が有利 => このキャラは Y に弱い
            mp, mn = re.search(POS, tail), re.search(NEG, tail)
            if mn and (not mp or mn.start() <= mp.start()): out.append("+")
            elif mp: out.append("-")
            continue
        if re.match(r"」?(など|等)?[^。]{0,3}(に|には|に対して|に対しては|相手|相手に|相手だと|相手では)[^。]{0,10}?" + POS, tail):
            out.append("+")
        elif re.match(r"」?(など|等)?[^。]{0,3}(に|には|に対して|に対しては|相手|相手に|相手だと|相手では)[^。]{0,10}?" + NEG, tail):
            out.append("-")
        elif re.match(r"」?(など|等)?[^。]{0,3}(とは|との|と)[^。]{0,6}?相性[^。]{0,4}?(悪|最悪)", tail): out.append("-")
        elif re.match(r"」?(など|等)?[^。]{0,3}(とは|との|と)[^。]{0,6}?相性[^。]{0,4}?(良|いい|抜群)", tail): out.append("+")
        elif re.match(r"」?(など|等)?[^。]{0,3}(は|が)[^。]{0,8}?(天敵|苦手|きつい|キツい|厳しい)", tail):
            out.append("+" if kind == "taisaku" else "-")
        elif re.match(r"」?(など|等)?[^。]{0,3}(は|が)[^。]{0,8}?(有利|得意|強い|刺さる)", tail):
            # 対策ページでは「Yは有利/強い」= Y がこのハンター(サバ)に強い
            out.append("-" if kind == "taisaku" else "+")
        elif re.search(r"(天敵|苦手)(である|の|は|となる)$", head): out.append("-")
    return out

def mine(path, me, kind):
    t = body_text(path)
    opp = [n for n in CH if SIDE[n] != SIDE[me]]
    res = []
    for sent in sentences(t):
        if re.search(r"一見|ように見え|そうに見え|と思われがち|かもしれないが", sent): continue
        for n in opp:
            for term in terms(n):
                if term in sent:
                    if term in ("レオ",) and "レオの思い出" in sent: continue
                    pol = classify(sent, term, kind)
                    if pol:
                        p = max(set(pol), key=pol.count)
                        # 対策ページは視点が逆 (X対策: 「Yに有利」は Y 視点の話が多い)
                        res.append({"opp": n, "pol": p, "kind": kind, "s": sent[:160]})
                    break
        for mp in MAPS:
            for term in [mp] + MAP_ALIAS[mp]:
                if term in sent and kind == "main":
                    pol = classify(sent, term)
                    if not pol and re.search(r"(では|だと|で)[^。]{0,12}" + POS, sent[sent.find(term):sent.find(term) + 30]): pol = ["+"]
                    if not pol and re.search(r"(では|だと|で)[^。]{0,12}" + NEG, sent[sent.find(term):sent.find(term) + 30]): pol = ["-"]
                    if pol:
                        res.append({"map": mp, "pol": pol[0], "kind": kind, "s": sent[:160]})
                    break
    return res

if __name__ == "__main__":
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "wikicache", "*.html"))):
        kind, _, name = os.path.basename(f)[:-5].split("_", 2)
        me = next((n for n in CH if n.strip("「」") == name), None)
        if not me: print("??", f); continue
        out.setdefault(me, []).extend(mine(f, me, kind))
    json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "matchups_wiki.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for me, rs in out.items():
        print("■", me, len(rs))
        for r in rs[:14]: print("  ", r["kind"][0], r["pol"], r.get("opp") or "@" + r["map"], "|", r["s"][:110])
