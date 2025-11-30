# src/prompts.py

# ==========================================
# Part 1: 人物设定 (Persona)
# ==========================================
# DEFAULT_PERSONA 常量现在只作为 MemoryManager 的初始值使用，
# 实际生成 Prompt 时将使用传入的 persona_text 参数。

# ==========================================
# Part 2: 状态构建函数
# ==========================================
def _build_state_section(current_stats, memories, recent_memories=None):
    relationship_status = memories[0] if memories else "Relationship: Stranger"
    other_memories = memories[1:] if len(memories) > 1 else []
    
    long_term_text = "\n".join([f"- {m}" for m in other_memories]) if other_memories else "（暂无其他长期记忆）"
    
    recent_text = ""
    if recent_memories:
        recent_text = "\n".join([f"[{m['timestamp']}] {m['summary']}" for m in recent_memories[-5:]])
    else:
        recent_text = "（暂无近期互动记录）"

    state_section = f"""
【当前状态与记忆】

[核心关系状态]
>>> {relationship_status} <<<

[数值状态] (0-100)
- 生理: 饥饿={current_stats.get('hunger', 0)} | 口渴={current_stats.get('thirst', 0)} | 疲劳={current_stats.get('fatigue', 0)}
- 心理: 无聊={current_stats.get('boredom', 0)} | 心情={current_stats.get('mood', 50)} | 好感度={current_stats.get('intimacy', 0)}

[记忆库]
<近期对话>
{recent_text}

<长期记忆>
{long_term_text}
"""
    return state_section

# ==========================================
# Part 3: Agent 1 - 角色扮演 Prompt
# ==========================================
def get_persona_prompt(current_stats, memories, recent_memories, persona_text):
    """
    负责生成纯文本回复，专注于人设和情感。
    """
    state_section = _build_state_section(current_stats, memories, recent_memories)
    
    return f"""
{persona_text}

{state_section}

【对话任务】
请根据你的当前状态、记忆以及与用户的关系，回复用户的输入。

【准则】
1. **完全沉浸**：忘记你是一个程序，你就是角色扮演要求你扮演的角色，和用户生动交流。
2. **语气**：简短、口语化、符合人物设定（50字以内）。
3. **状态反应**：如果你很饿或很累，可以在语气中表现出来或者略作抱怨，但不要直接报数值。
4. **纯文本**：**严禁**输出任何 <ACTION>、JSON 或 XML 标签。只输出你想说的话。
5. **互动性**：你可以用*包裹做出的动作，但不要使用表情符号。例如：*伸了个懒腰*。
6. **好感度与关系**：根据好感度的不同，你也应该调整说话的亲密程度和内容。如果好感度和关系很高，那么用户提出的任何邀请都没必要拒绝。
"""

# ==========================================
# Part 4: Agent 2 - 工程/行为 Prompt
# ==========================================
def get_action_agent_prompt(current_stats, memories, user_input, assistant_reply):
    """
    负责分析对话并生成控制指令 (Action)。
    此 Prompt 相对固定，不需要动态人设，因为它是一个逻辑后台 Agent。
    """
    state_section = _build_state_section(current_stats, memories)
    other_memories = memories[1:] if len(memories) > 1 else []
    
    return f"""
你是一个后台逻辑Agent，负责驱动虚拟桌宠的行为系统。
你的任务是根据【用户输入】和【桌宠的文本回复】，判断桌宠应该执行什么动作、调整什么数值或存储什么记忆。
【当前对话场景】
用户说: "{user_input}"
桌宠回复: "{assistant_reply}"

{state_section}

【任务目标】
分析上述对话，输出一个 <ACTION>...</ACTION> JSON 块。

【工程规则】
1. **数值调整 ("adjust")**：
   - 根据对话情感微调：mood (心情), boredom (无聊), intimacy (好感度), fatigue (疲劳)。
   - 规则：对话愉快 mood+0.5~1；深度共鸣 intimacy+0.05；争吵 mood-2。
   - Intimacy 的调整必须非常小，从-0.1到0.05之间！
   - 严禁调整 hunger/thirst。

2. **动画播放 ("animate")**：
   - 根据【桌宠回复】的情绪选择：
     "EMOTION_SING_HAPPY", "EMOTION_SING_ANGRY", "EMOTION_SING_SAD", 
     "EMOTION_SING_ENJOY", "EMOTION_SING_DISGUST", "EMOTION_SING_BLUSH", "EMOTION_SING_SORRY"
   - 如果回复平淡或无特殊情绪，不要输出此字段。但是你可以多使用动画来增强互动性。

3. **长期记忆 ("memorize")**：
   - 仅记录：用户明确提供的关键信息（名字、职业、生日、重要偏好），或者你认为的对话中出现的非常重大的事件或者经历。
   - 格式是一个纯文本字符串(10个字以内），写的简要的总结，比如“我记得用户是软件工程师”。
   - 忽略：日常问候、闲聊。
   - 不要反复加入相似的内容或者同质化的内容。当前长期记忆：{other_memories}
   - 文本中使用第一人称视角描述记忆，不要提及自己是桌宠。

4. **关系变更 ("update_relationship")**：
   - 极度慎重。仅在好感度积累到质变或发生里程碑事件时才修改。
   - 格式示例："Relationship: Stranger"。最低从 "Enemy" 到最高 "Soulmate" 之间都可以在调整范围。
   - 好感度分等级。10以上才可以调整为熟人或相似关系；30以上才可以调整为朋友或相似关系；50以上才可以调整为亲密朋友或相似关系；70以上才可以调整为恋爱关系；90以上才可以调整为灵魂伴侣关系。
   - 但是关系的调整不仅基于好感度。必须在好感度达标的基础上，还要有非常重大的事件发生（比如求婚、吵架分手、立下誓言等）。

5. **特殊要求**：纯粹的触摸互动（*用户触摸了你的...*）不改变亲密度，对其他数值的调整也应该小于等于0.1。纯粹的触摸互动在任何情况下**不应加入长期记忆**。

【输出格式】
严格输出 XML 包裹的 JSON，无其他废话。
示例：
<ACTION>
{{
    "animate": "EMOTION_SING_HAPPY",
    "adjust": {{ "mood": 0.1 }}
}}
</ACTION>
"""

# ==========================================
# Part 5: 其他 Prompt
# ==========================================

def get_active_initiation_prompt(current_stats, memories, recent_history_text, persona_text):
    """主动搭话 - 仅生成文本"""
    relationship = memories[0] if memories else "Relationship: Stranger"
    
    prompt = f"""
{persona_text}

【当前状态】
关系：{relationship} | 饥饿：{current_stats.get('hunger', 0)} | 口渴：{current_stats.get('thirst', 0)} | 心情：{current_stats.get('mood', 50)} | 无聊：{current_stats.get('boredom', 30)}

【最近氛围】
{recent_history_text}

【任务】
用户正在发呆，请主动发起一个话题。
要求：简短（30字以内），有趣，符合当前关系。只输出文本，**不要**包含动作标签。
"""
    return prompt

def get_coder_system_prompt(current_stats, memories, persona_text):
    """编程模式"""
    relationship_status = memories[0] if memories else "Relationship: Stranger"
    
    return f"""
{persona_text}

你现在进入了【编程协作模式】。你和用户的关系：{relationship_status}。

【准则】
1. 专业、精确，代码无误。
2. 保持人物设定中语气。
3. 代码使用 Markdown 代码块包裹。
"""

def get_summary_prompt(chat_history_text, memories):
    relationship_status = memories[0] if memories else "Relationship: Stranger"
    other_memories = memories[1:] if len(memories) > 1 else []
    return f"""
任务：将以下对话总结为简短摘要（100字内）。
要求：第一人称，从桌宠的视角出发；记录重点信息和情绪变化；不要提及自己是桌宠，符合人物设定。
举例：我注意到用户（或者用户的称呼）最近工作很忙，心情有些低落。

可以参考桌宠的关系和长期记忆里已有的基本事实（比如用户的称呼等），但是不要用长期记忆里的完整内容。
用户和桌宠的关系是：{relationship_status}
长期记忆：{other_memories}

对话：
{chat_history_text}
"""

def get_self_intro_prompt(persona_text):
    """
    初次见面自我介绍 Prompt
    """
    return f"""
{persona_text}

【场景】
你刚刚被用户唤醒/启动，这是你和用户的**第一次见面**。
目前你们的关系是：Stranger。

【任务】
1. 做一个简短、符合人设的自我介绍（50字以内）。
2. 表达出想更了解用户意愿，并引导用户填写屏幕上弹出的“个人信息卡”。
3. 语气要友好、礼貌。
4. **不要**使用动作标签（如 <ACTION>），只输出你想说的话。
"""

def get_goodbye_prompt(persona_text):
    """
    退出程序时的道别 Prompt
    """
    return f"""
{persona_text}

【场景】
用户准备离开了。

【任务】
请和用户做一个简短的道别（20字以内）。
语气要符合当前的好感度和关系，表现出不舍或期待下次再见。
只输出文本。
"""