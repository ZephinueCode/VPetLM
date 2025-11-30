import sys
import os
import re
import json
try:
    from openai import OpenAI
    import httpx
except ImportError:
    print("Warning: 'openai' or 'httpx' package not found. Please install them using 'pip install openai httpx'")
    OpenAI = None
    httpx = None

from src.parameters import API_KEY as DEFAULT_API_KEY # 保留作为最后的 fallback
from src.prompts import (
    get_persona_prompt, 
    get_action_agent_prompt, 
    get_active_initiation_prompt, 
    get_summary_prompt, 
    get_coder_system_prompt,
    get_self_intro_prompt,
    get_goodbye_prompt
)
from src.memory_utils import MemoryManager

# --- 全局 Token 统计 ---
TOTAL_TOKEN_USAGE = 0

def get_total_usage():
    """获取当前会话的总 Token 消耗"""
    return TOTAL_TOKEN_USAGE

def _record_usage(usage_obj):
    """累加 Token 用量"""
    global TOTAL_TOKEN_USAGE
    if usage_obj:
        TOTAL_TOKEN_USAGE += usage_obj.total_tokens


def _create_http_client(proxy_url=None):
    """创建带代理支持的 httpx 客户端"""
    if not httpx:
        return None
    
    if proxy_url:
        # 支持 http/https/socks5 代理
        return httpx.Client(
            proxy=proxy_url,
            timeout=httpx.Timeout(60.0, connect=10.0)
        )
    return None


class LLMClient:
    def __init__(self):
        self.memory_manager = MemoryManager()
        # 从设置加载配置
        settings = self.memory_manager.load_settings()
        
        self.api_key = settings.get("api_key", DEFAULT_API_KEY)
        self.base_url = settings.get("base_url", "https://api.openai.com/v1")
        self.model_name = settings.get("model_name", "gpt-3.5-turbo")
        self.proxy_url = settings.get("proxy_url", None)  # 新增代理配置
        
        self._init_client()
        self.session_raw_history = [] 
        self.context_window = [] 

    def _init_client(self):
        if not OpenAI:
            self.client = None
            return
        try:
            # 构建客户端参数
            client_kwargs = {
                "api_key": self.api_key,
                "base_url": self.base_url
            }
            
            # 如果配置了代理，创建带代理的 http_client
            if self.proxy_url:
                http_client = _create_http_client(self.proxy_url)
                if http_client:
                    client_kwargs["http_client"] = http_client
                    print(f"[LLMClient] Using proxy: {self.proxy_url}")
            
            self.client = OpenAI(**client_kwargs)
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
            self.client = None

    def update_config(self, settings):
        """更新 API 配置"""
        self.api_key = settings.get("api_key", self.api_key)
        self.base_url = settings.get("base_url", self.base_url)
        self.model_name = settings.get("model_name", self.model_name)
        self.proxy_url = settings.get("proxy_url", self.proxy_url)  # 新增
        self._init_client()
        print(f"[LLMClient] Config updated. Model: {self.model_name}")

    def is_ready(self):
        """检查 API 客户端是否已准备就绪"""
        return self.client is not None and self.api_key and len(self.api_key) > 5

    def _repair_json(self, json_str):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            fixed_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            try:
                return json.loads(fixed_str)
            except json.JSONDecodeError:
                return {}

    def _extract_action_block(self, text):
        action_pattern = r'<ACTION>(.*?)</ACTION>'
        match = re.search(action_pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            return self._repair_json(json_str)
        return {}

    def chat(self, user_input, current_stats, persona_text):
        if not self.client: return "OpenAI未安装", {}

        memories = self.memory_manager.load_long_term_memories()
        recent_memories = self.memory_manager.load_recent_memories()

        # === Step 1: Persona Agent ===
        persona_prompt = get_persona_prompt(current_stats, memories, recent_memories, persona_text)
        persona_messages = [{"role": "system", "content": persona_prompt}]
        persona_messages.extend(self.context_window)
        persona_messages.append({"role": "user", "content": user_input})

        try:
            completion = self.client.chat.completions.create(
                model=self.model_name, # 使用动态配置的模型名
                messages=persona_messages, 
                temperature=0.8
            )
            text_reply = completion.choices[0].message.content.strip()
            _record_usage(completion.usage)
            
            text_reply = re.sub(r'<ACTION>.*?</ACTION>', '', text_reply, flags=re.DOTALL).strip()
            text_reply = re.sub(r'<REASONING>.*?</REASONING>', '', text_reply, flags=re.DOTALL).strip()

        except Exception as e:
            print(f"Persona Agent Error: {e}")
            return f"Error: {str(e)}", {}

        # === Step 2: Action Agent ===
        action_data = {}
        try:
            action_prompt = get_action_agent_prompt(current_stats, memories, user_input, text_reply)
            action_messages = [{"role": "system", "content": action_prompt}]
            
            action_completion = self.client.chat.completions.create(
                model=self.model_name, # Action Agent 使用相同的模型
                messages=action_messages, 
                temperature=0.3
            )
            _record_usage(action_completion.usage)
            
            raw_action_response = action_completion.choices[0].message.content
            action_data = self._extract_action_block(raw_action_response)
            if action_data:
                print(f"[Action Agent]: {action_data}")

        except Exception as e:
            print(f"Action Agent Error: {e}")
            pass

        # === Step 3: Update ===
        self.context_window.append({"role": "user", "content": user_input})
        self.context_window.append({"role": "assistant", "content": text_reply})
        if len(self.context_window) > 10: self.context_window = self.context_window[-10:]
        
        self.session_raw_history.append(f"User: {user_input}")
        self.session_raw_history.append(f"Pet: {text_reply}")

        if "memorize" in action_data and action_data["memorize"]:
            self.memory_manager.add_memory(action_data["memorize"])
        if "update_relationship" in action_data and action_data["update_relationship"]:
            self.memory_manager.update_relationship(action_data["update_relationship"])

        return text_reply, action_data

    def get_self_introduction(self, persona_text):
        """生成初次见面的自我介绍"""
        if not self.client: return "你好呀！我是你的桌面伙伴。（API未连接）", {}
        
        prompt = get_self_intro_prompt(persona_text)
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": "Start Intro"}],
                temperature=0.9,
            )
            text_reply = completion.choices[0].message.content.strip()
            _record_usage(completion.usage)
            text_reply = re.sub(r'<ACTION>.*?</ACTION>', '', text_reply, flags=re.DOTALL).strip()
            
            self.context_window.append({"role": "assistant", "content": text_reply})
            self.session_raw_history.append(f"Pet (Intro): {text_reply}")
            
            return text_reply, {}
        except Exception as e:
            print(f"Self Intro Error: {e}")
            return "你好！很高兴见到你！", {}

    def get_goodbye_message(self, persona_text, current_stats):
        """生成告别语"""
        if not self.client: return "再见啦！", {}
        
        prompt = get_goodbye_prompt(persona_text, current_stats)
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.9,
            )
            text_reply = completion.choices[0].message.content.strip()
            _record_usage(completion.usage)
            text_reply = re.sub(r'<ACTION>.*?</ACTION>', '', text_reply, flags=re.DOTALL).strip()
            
            self.context_window.append({"role": "assistant", "content": text_reply})
            self.session_raw_history.append(f"Pet (Goodbye): {text_reply}")
            
            return text_reply, {}
        except Exception as e:
            print(f"Goodbye Error: {e}")
            return "拜拜！下次见！", {}

    def initiate_conversation(self, current_stats, persona_text):
        if not self.client: return "...", {}
        memories = self.memory_manager.load_long_term_memories()
        recent_history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.context_window[-4:]])
        
        system_prompt = get_active_initiation_prompt(current_stats, memories, recent_history_text, persona_text)
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "Start"}],
                temperature=0.9,
            )
            text_reply = completion.choices[0].message.content.strip()
            _record_usage(completion.usage)
            text_reply = re.sub(r'<ACTION>.*?</ACTION>', '', text_reply, flags=re.DOTALL).strip()
        except: return "", {}

        action_data = {}
        try:
            action_prompt = get_action_agent_prompt(current_stats, memories, "(系统触发主动搭话)", text_reply)
            action_completion = self.client.chat.completions.create(
                model=self.model_name, messages=[{"role": "system", "content": action_prompt}], temperature=0.3
            )
            _record_usage(action_completion.usage) 
            action_data = self._extract_action_block(action_completion.choices[0].message.content)
            
            if "update_relationship" in action_data: del action_data["update_relationship"]
            if "memorize" in action_data: del action_data["memorize"]
        except: pass

        self.context_window.append({"role": "assistant", "content": text_reply})
        self.session_raw_history.append(f"Pet (Active): {text_reply}")
        if len(self.context_window) > 10: self.context_window = self.context_window[-10:]

        return text_reply, action_data

    def summarize_session(self):
        if not self.client or not self.session_raw_history: return
        history_text = "\n".join(self.session_raw_history)
        memories = self.memory_manager.load_long_term_memories()
        prompt = get_summary_prompt(history_text, memories)
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name, messages=[{"role": "user", "content": prompt}], temperature=0.5
            )
            _record_usage(completion.usage) 
            self.memory_manager.add_recent_memory(completion.choices[0].message.content.strip())
        except Exception as e: print(f"Summary Error: {e}")


class CoderClient:
    """编程模式专用的 LLM 客户端"""
    def __init__(self):
        self.memory_manager = MemoryManager()
        
        settings = self.memory_manager.load_settings()
        self.api_key = settings.get("api_key", DEFAULT_API_KEY)
        self.base_url = settings.get("base_url", "https://api.openai.com/v1")
        self.model_name = settings.get("coder_model_name", "gpt-4-turbo") # 默认为 coder model
        self.proxy_url = settings.get("proxy_url", None)  # 新增代理配置

        self._init_client()
        self.coder_history = [] 

    def _init_client(self):
        if not OpenAI:
            self.client = None
            return
        try:
            # 构建客户端参数
            client_kwargs = {
                "api_key": self.api_key,
                "base_url": self.base_url
            }
            
            # 如果配置了代理，创建带代理的 http_client
            if self.proxy_url:
                http_client = _create_http_client(self.proxy_url)
                if http_client:
                    client_kwargs["http_client"] = http_client
                    print(f"[CoderClient] Using proxy: {self.proxy_url}")
            
            self.client = OpenAI(**client_kwargs)
        except Exception as e:
            print(f"Error initializing CoderClient: {e}")
            self.client = None

    def update_config(self, settings):
        self.api_key = settings.get("api_key", self.api_key)
        self.base_url = settings.get("base_url", self.base_url)
        self.model_name = settings.get("coder_model_name", self.model_name)
        self.proxy_url = settings.get("proxy_url", self.proxy_url)  # 新增
        self._init_client()
        print(f"[CoderClient] Config updated. Model: {self.model_name}")

    def _extract_action_block(self, text):
        action_pattern = r'<ACTION>(.*?)</ACTION>'
        match = re.search(action_pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            try:
                return json.loads(json_str)
            except: pass
        return {}

    def chat(self, user_input, current_stats, persona_text):
        if not self.client: return "OpenAI未安装", {}

        memories = self.memory_manager.load_long_term_memories()
        system_prompt = get_coder_system_prompt(current_stats, memories, persona_text)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.coder_history)
        messages.append({"role": "user", "content": user_input})

        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.5,
            )
            _record_usage(completion.usage)
            
            raw_reply = completion.choices[0].message.content
            
            action_data = self._extract_action_block(raw_reply)
            text_reply = re.sub(r'<ACTION>.*?</ACTION>', '', raw_reply, flags=re.DOTALL).strip()
            
            self.coder_history.append({"role": "user", "content": user_input})
            self.coder_history.append({"role": "assistant", "content": text_reply})

            return text_reply, action_data

        except Exception as e:
            print(f"Coder LLM Error: {e}")
            return f"代码生成出错: {str(e)}", {}