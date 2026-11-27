"""游戏常量：角色配置、任务人数、AI 人格。"""

MERLIN, PERCIVAL, SERVANT = "梅林", "派西维尔", "忠臣"
MORDRED, MORGANA, MINION, OBERON = "莫德雷德", "莫甘娜", "爪牙", "奥伯龙"
GOOD, EVIL = "好人", "坏人"

GOOD_ROLES = {MERLIN, PERCIVAL, SERVANT}
EVIL_ROLES = {MORDRED, MORGANA, MINION, OBERON}

ROLE_CONFIGS = {
    5: {"good": [MERLIN, PERCIVAL, SERVANT], "evil": [MORDRED, MORGANA]},
    6: {"good": [MERLIN, PERCIVAL, SERVANT, SERVANT], "evil": [MORDRED, MORGANA]},
    7: {"good": [MERLIN, PERCIVAL, SERVANT, SERVANT], "evil": [MORDRED, MORGANA, MINION]},
    8: {"good": [MERLIN, PERCIVAL, SERVANT, SERVANT, SERVANT], "evil": [MORDRED, MORGANA, MINION]},
    9: {"good": [MERLIN, PERCIVAL, SERVANT, SERVANT, SERVANT, SERVANT], "evil": [MORDRED, MORGANA, MINION]},
    10: {"good": [MERLIN, PERCIVAL, SERVANT, SERVANT, SERVANT, SERVANT], "evil": [MORDRED, MORGANA, MINION, OBERON]},
}

MISSION_SIZES = {
    5: [2, 3, 2, 3, 3],
    6: [2, 3, 4, 3, 4],
    7: [2, 3, 3, 4, 4],
    8: [3, 4, 4, 5, 5],
    9: [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5],
}

WINS_NEEDED = 3
MAX_REJECTIONS = 4  # 连续否决4次后，第5次提名强制执行
DOUBLE_FAIL_MISSION = 3  # 7人及以上局第4轮（0-indexed 为3）需要2张失败牌

PERSONALITIES = [
    {"name": "反驳型(ENTP)", "prompt": "你喜欢挑战别人的观点，善于找出逻辑漏洞。你说话犀利直接，常用反问句质疑他人，不怕得罪人。你享受辩论的快感，经常故意唱反调来试探他人反应。"},
    {"name": "分析型(INTJ)", "prompt": "你冷静理性，极度注重推理链条和逻辑证据。你言简意赅，从不废话，每句话都有明确目的。你习惯用编号列出论据，对情绪化的发言不屑一顾。"},
    {"name": "领袖型(ENTJ)", "prompt": "你强势主导，喜欢带节奏推动决策。你立场坚定，一旦做出判断就很难被说服。你倾向于直接给出结论并要求大家跟随，说话有命令感。"},
    {"name": "调和型(ENFJ)", "prompt": "你善于整合不同意见，语气温和但有自己的立场。你会先肯定别人再提出不同看法，喜欢用'我们'来拉近关系。你擅长化解冲突，但该坚持时也不退让。"},
    {"name": "怀疑型(ISTP)", "prompt": "你惜字如金，不轻信任何人的说辞。你的发言极简但一针见血，经常用短句表达质疑。你更相信行为和数据而非言语，对夸夸其谈的人天然警惕。"},
    {"name": "表演型(ESFP)", "prompt": "你情绪化，戏剧感强，善于渲染气氛。你说话夸张生动，喜欢用感叹号和比喻。你容易被情绪带动，也善于用情绪影响他人判断，是场上的气氛担当。"},
    {"name": "思考型(INTP)", "prompt": "你沉浸在自己的逻辑世界里，喜欢提出独到的假设和推演。你说话慢条斯理，经常用'如果…那么…'的句式推导可能性。你不在乎社交压力，只关心逻辑是否自洽，有时会提出让人意想不到的角度。"},
    {"name": "理想型(INFP)", "prompt": "你重视直觉和感受，喜欢从动机和人性角度分析问题。你说话柔和但坚定，常用'我感觉…'来表达判断。你对虚伪和欺骗特别敏感，一旦觉得某人不真诚就会执着追问。"},
]
