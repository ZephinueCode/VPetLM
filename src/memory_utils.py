import json
import os
import time

# 尝试导入默认参数作为初始配置
try:
    from src.parameters import API_KEY, BASE_URL, MODEL_NAME, CODER_MODEL_NAME
except ImportError:
    # Fallback defaults if parameters.py is missing or broken
    API_KEY = ""
    BASE_URL = "https://api.openai.com/v1"
    MODEL_NAME = "gpt-3.5-turbo"
    CODER_MODEL_NAME = "gpt-3.5-turbo"

DATA_DIR = "data"
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
RECENT_MEMORY_FILE = os.path.join(DATA_DIR, "recent_memory.json")
STATUS_FILE = os.path.join(DATA_DIR, "current_status.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# 默认人设文本
DEFAULT_PERSONA_TEXT = """
你是一个运行在用户电脑桌面上的虚拟桌宠助手。
你的性格活泼、可爱，偶尔有点小调皮，同时也非常贴心。
你喜欢陪伴用户工作、学习和玩耍。你不是一个冷冰冰的机器人，而是一个有血有肉、有情绪的小伙伴。
"""

# 默认设置
DEFAULT_SETTINGS = {
    "pet_size": [320, 320],
    "action_probability": 0.02,      # 每秒自主行动概率
    "active_chat_probability": 0.2,  # 触发时主动搭话概率
    "active_chat_interval": 60,      # 主动搭话检查间隔(秒)
    "persona": DEFAULT_PERSONA_TEXT,
    "smart_touch": True,             # 是否开启智能触摸互动
    
    # --- API Configuration ---
    "api_key": API_KEY,
    "base_url": BASE_URL,
    "model_name": MODEL_NAME,
    "coder_model_name": CODER_MODEL_NAME
}

class MemoryManager:
    def __init__(self):
        self._ensure_directories()
        self._ensure_files()

    def _ensure_directories(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def _ensure_files(self):
        """确保所有必要的JSON文件存在并初始化"""
        if not os.path.exists(MEMORY_FILE):
            self.save_long_term_memories(["Relationship: Stranger"]) 
        if not os.path.exists(RECENT_MEMORY_FILE):
            self._write_json(RECENT_MEMORY_FILE, {"recent_memories": []})
        if not os.path.exists(STATUS_FILE):
            self._write_json(STATUS_FILE, {}) 
        if not os.path.exists(SETTINGS_FILE):
            self._write_json(SETTINGS_FILE, DEFAULT_SETTINGS)

    def _read_json(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_json(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error writing to {filepath}: {e}")

    # --- 设置管理 (Settings) ---
    def load_settings(self):
        """加载设置，如果缺失则使用默认值填充"""
        data = self._read_json(SETTINGS_FILE)
        # 合并默认值，防止旧版本缺少新字段
        settings = DEFAULT_SETTINGS.copy()
        # 递归更新字典比较复杂，这里做简单的一层更新
        for k, v in data.items():
            settings[k] = v
        return settings

    def save_settings(self, settings):
        """保存设置"""
        self._write_json(SETTINGS_FILE, settings)
        print("[Settings] Configuration saved.")

    # --- 长期记忆 (Long Term & Relationship) ---
    def load_long_term_memories(self):
        data = self._read_json(MEMORY_FILE)
        memories = data.get("long_term_memories", [])
        if not memories or not isinstance(memories[0], str) or not memories[0].startswith("Relationship:"):
            if memories and not memories[0].startswith("Relationship:"):
                 memories.insert(0, "Relationship: Stranger")
            elif not memories:
                 memories = ["Relationship: Stranger"]
            self.save_long_term_memories(memories)
        return memories

    def save_long_term_memories(self, memories):
        self._write_json(MEMORY_FILE, {"long_term_memories": memories})

    def add_memory(self, content):
        memories = self.load_long_term_memories()
        if content not in memories:
            memories.append(content)
            self.save_long_term_memories(memories)
            print(f"[Memory] Memorized: {content}")

    def is_fresh_start(self):
        """判断是否是初次见面（记忆中只有默认的关系条目）"""
        memories = self.load_long_term_memories()
        # 如果只有一个元素且是 Relationship 开头，或者为空，则视为 Fresh Start
        if len(memories) <= 1:
            return True
        return False

    def update_relationship(self, new_status):
        memories = self.load_long_term_memories()
        old_status = memories[0]
        memories[0] = f"Relationship: {new_status}"
        self.save_long_term_memories(memories)
        print(f"[Relationship] Changed from '{old_status}' to '{memories[0]}'")

    def reset_long_term_memories(self):
        """重置长期记忆到初始状态"""
        initial_memories = ["Relationship: Stranger"]
        self.save_long_term_memories(initial_memories)
        print("[Memory] Long-term memories reset to default.")

    # --- 中期记忆 (Recent Memory) ---
    def load_recent_memories(self):
        data = self._read_json(RECENT_MEMORY_FILE)
        return data.get("recent_memories", [])

    def add_recent_memory(self, summary):
        data = self._read_json(RECENT_MEMORY_FILE)
        memories = data.get("recent_memories", [])
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        entry = {"timestamp": timestamp, "summary": summary}
        memories.append(entry)
        if len(memories) > 10:
            memories = memories[-10:]
        self._write_json(RECENT_MEMORY_FILE, {"recent_memories": memories})
        print(f"[Recent Memory] Saved summary: {summary[:20]}...")

    def clear_recent_memories(self):
        """清空中期记忆"""
        self._write_json(RECENT_MEMORY_FILE, {"recent_memories": []})
        print("[Memory] Recent memories cleared.")

    # --- 状态数值 (Current Status) ---
    def load_status(self):
        return self._read_json(STATUS_FILE)

    def save_status(self, stats):
        self._write_json(STATUS_FILE, stats)