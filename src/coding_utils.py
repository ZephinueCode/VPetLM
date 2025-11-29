import html
import re
import uuid
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QTextBrowser,
                             QPushButton, QSplitter, QLabel, QFrame, QSizeGrip, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QRegularExpression, QUrl
from PyQt6.QtGui import QFont, QTextCursor, QColor, QPalette, QSyntaxHighlighter, QTextCharFormat, QTextBlockFormat, QDesktopServices

# --- 1. Geek 语法高亮器 (用于输入框) ---
class GeekHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # --- 样式定义 ---
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6")) 
        keyword_format.setFontWeight(QFont.Weight.Bold)
        
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))
        
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#dcdcaa"))
        
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#b5cea8"))

        # --- 规则定义 ---
        keywords = [
            'def', 'class', 'lambda', 'with', 'as', 'pass', 'from', 'import',
            'global', 'nonlocal', 'assert', 'del', 'yield', 'int', 'float', 'str', 'bool', 'list', 'dict'
        ]
        controls = [
            'if', 'else', 'elif', 'while', 'for', 'break', 'continue', 
            'return', 'try', 'except', 'finally', 'raise', 'in', 'is', 'and', 'or', 'not'
        ]
        
        for word in keywords:
            pattern = QRegularExpression(r'\b' + word + r'\b')
            self.highlighting_rules.append((pattern, keyword_format))
            
        for word in controls:
            pattern = QRegularExpression(r'\b' + word + r'\b')
            self.highlighting_rules.append((pattern, keyword_format)) # 使用相同颜色保持简洁

        # 字符串
        self.highlighting_rules.append((QRegularExpression(r'".*?"'), string_format))
        self.highlighting_rules.append((QRegularExpression(r"'.*?'"), string_format))
        
        # 函数名
        self.highlighting_rules.append((QRegularExpression(r'\b[A-Za-z0-9_]+(?=\()'), function_format))
        
        # 注释 (Python #)
        self.highlighting_rules.append((QRegularExpression(r'#[^\n]*'), comment_format))
        # 注释 (C++/JS //)
        self.highlighting_rules.append((QRegularExpression(r'//[^\n]*'), comment_format))
        
        # 数字
        self.highlighting_rules.append((QRegularExpression(r'\b\d+\b'), number_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

# --- 2. 稳健的 HTML 语法高亮工具 ---
def highlight_code_html(code_text):
    """
    使用正则分词进行 HTML 高亮，避免破坏结构。
    """
    # 基础转义，保留引号以便后续匹配字符串
    # 注意：后续生成的 HTML 属性值必须用双引号包裹，且内容中的双引号需再次转义，
    # 但这里我们生成的是 innerHTML，所以直接 escape 即可。
    # 为了正则匹配字符串方便，我们先不完全转义引号，或者在正则中处理。
    # 策略：先完全转义，然后在转义后的文本上做正则替换是比较安全的，
    # 但正则会变得复杂（因为 " 变成了 &quot;）。
    # 
    # 更好的策略：先分词，对每个 token 进行转义并包裹 span。
    
    token_pattern = re.compile(
        r'(?P<string>".*?"|\'.*?\')|'           # 字符串
        r'(?P<comment>#[^a-fA-F0-9].*|//.*)|'   # 注释 (修复：#后不跟十六进制字符才算注释，防止误伤颜色代码)
        r'(?P<keyword>\b(?:def|class|lambda|with|as|pass|from|import|global|return|try|except|finally|if|else|elif|while|for|break|continue|in|is|and|or|not|int|float|str|bool|list|dict)\b)|'
        r'(?P<function>\b[a-zA-Z_]\w*(?=\())|'  # 函数名
        r'(?P<number>\b\d+\b)'                  # 数字
    )

    def escape(s):
        return html.escape(s)

    result = []
    pos = 0
    
    for match in token_pattern.finditer(code_text):
        # 处理匹配之前的普通文本
        if match.start() > pos:
            result.append(escape(code_text[pos:match.start()]))
        
        text = match.group(0)
        
        if match.group('string'):
            result.append(f'<span style="color:#ce9178;">{escape(text)}</span>')
        elif match.group('comment'):
            result.append(f'<span style="color:#6a9955;">{escape(text)}</span>')
        elif match.group('keyword'):
            result.append(f'<span style="color:#569cd6; font-weight:bold;">{escape(text)}</span>')
        elif match.group('function'):
            result.append(f'<span style="color:#dcdcaa;">{escape(text)}</span>')
        elif match.group('number'):
            result.append(f'<span style="color:#b5cea8;">{escape(text)}</span>')
        else:
            result.append(escape(text))
            
        pos = match.end()
        
    if pos < len(code_text):
        result.append(escape(code_text[pos:]))
        
    return "".join(result)

# --- 3. 后台工作线程 ---
class CoderWorker(QThread):
    reply_signal = pyqtSignal(str, dict)

    def __init__(self, client, text, stats, persona):
        super().__init__()
        self.client = client
        self.text = text
        self.stats = stats
        self.persona = persona

    def run(self):
        if self.client:
            reply, action = self.client.chat(self.text, self.stats, self.persona)
            self.reply_signal.emit(reply, action)

# --- 4. 编程窗口主类 ---
class CodingWindow(QWidget):
    action_signal = pyqtSignal(dict) 

    def __init__(self, coder_client, current_stats_getter):
        super().__init__()
        self.client = coder_client
        self.get_stats = current_stats_getter
        self.get_persona = lambda: "" # 默认回退
        self.worker = None
        self.drag_pos = None
        self.history = [] 
        self.is_processing = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Terminal - Coding Assistant")
        self.resize(950, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setStyleSheet("""
            QWidget#main_frame {
                background-color: #1e1e1e; 
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QLabel#header {
                color: #cccccc;
                font-family: 'Consolas', monospace;
                font-weight: bold;
                font-size: 13px;
                padding-left: 8px;
            }
            QTextBrowser#output_area {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 14px;
                padding: 10px;
                line-height: 1.6;
            }
            QTextEdit#input_field {
                background-color: #252526;
                border-top: 1px solid #3e3e42;
                color: #d4d4d4; 
                font-family: 'Consolas', 'Microsoft YaHei', monospace;
                font-size: 14px;
                padding: 8px;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e1e1e;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical { border: none; background: none; }
            QScrollBar::sub-line:vertical { border: none; background: none; }
            
            QSplitter::handle {
                background-color: #333333;
                height: 2px;
            }
            QPushButton#close_btn {
                color: #888888;
                border: none;
                font-weight: bold;
                font-size: 16px;
                background: transparent;
            }
            QPushButton#close_btn:hover { color: #ff5555; }
            QPushButton#send_btn {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: bold;
            }
            QPushButton#send_btn:hover { background-color: #1177bb; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.main_frame = QFrame()
        self.main_frame.setObjectName("main_frame")
        
        frame_layout = QVBoxLayout(self.main_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(35)
        title_bar.setStyleSheet("background-color: #252526; border-top-left-radius: 6px; border-top-right-radius: 6px; border-bottom: 1px solid #333;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 5, 0)
        
        self.header_label = QLabel(" >_ root@desktop-pet:~/coding-mode")
        self.header_label.setObjectName("header")
        
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("close_btn")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.hide)

        title_layout.addWidget(self.header_label)
        title_layout.addStretch()
        title_layout.addWidget(self.close_btn)
        frame_layout.addWidget(title_bar)

        # 内容区
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # 输出区
        self.output_area = QTextBrowser()
        self.output_area.setObjectName("output_area")
        self.output_area.setOpenExternalLinks(False)
        self.output_area.anchorClicked.connect(self.on_anchor_clicked)
        self.splitter.addWidget(self.output_area)

        # 输入区
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(10)

        self.input_field = QTextEdit()
        self.input_field.setObjectName("input_field")
        self.input_field.setAcceptRichText(False) 
        self.input_field.setPlaceholderText("# 输入代码或指令... (Ctrl+Enter 发送)")
        
        self.highlighter = GeekHighlighter(self.input_field.document())

        self.send_btn = QPushButton("RUN")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.setFixedSize(90, 40)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        
        self.splitter.addWidget(input_container)
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)

        content_layout.addWidget(self.splitter)
        frame_layout.addWidget(content_area)

        # 底部手柄
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 5, 5)
        bottom_bar.addStretch()
        size_grip = QSizeGrip(self.main_frame)
        bottom_bar.addWidget(size_grip)
        frame_layout.addLayout(bottom_bar)

        main_layout.addWidget(self.main_frame)

    # --- 拖拽 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 40:
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_pos:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    # --- 核心交互 ---
    def on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("toggle://"):
            block_id = url_str.replace("toggle://", "")
            self.toggle_code_block(block_id)
        else:
            QDesktopServices.openUrl(url)

    def toggle_code_block(self, block_id):
        found = False
        for msg in self.history:
            if msg['type'] == 'coder':
                for chunk in msg['content']:
                    if chunk['type'] == 'code' and chunk['id'] == block_id:
                        chunk['expanded'] = not chunk['expanded']
                        found = True
                        break
            if found: break
        if found: self.render_all_history()

    def start_session(self):
        self.show()
        if not self.history:
            self.append_system_message("Env Initialized. Mode: Programming.")
            self.process_input("我们开始编程吧！请根据当前状态准备好环境。", is_system=True)

    def send_message(self):
        text = self.input_field.toPlainText().strip()
        if not text: return
        self.append_user_message(text)
        self.input_field.clear()
        self.process_input(text)

    def process_input(self, text, is_system=False):
        self.is_processing = True
        self.render_all_history()
        
        stats = self.get_stats()
        persona = self.get_persona()
        self.worker = CoderWorker(self.client, text, stats, persona)
        self.worker.reply_signal.connect(self.handle_reply)
        self.worker.start()

    def handle_reply(self, reply, action):
        self.is_processing = False
        # 再次清理，确保 UI 不显示标签
        reply = re.sub(r'<REASONING>.*?</REASONING>', '', reply, flags=re.DOTALL).strip()
        
        # 尝试提取动作
        match = re.search(r'<ACTION>(.*?)</ACTION>', reply, re.DOTALL)
        if match:
            if not action:
                try:
                    action = json.loads(match.group(1).strip())
                except: pass
            reply = reply.replace(match.group(0), "").strip()

        self.append_ai_message(reply)
        if action: self.action_signal.emit(action)

    def append_system_message(self, text):
        self.history.append({'type': 'system', 'content': text})
        self.render_all_history()

    def append_user_message(self, text):
        self.history.append({'type': 'user', 'content': text})
        self.render_all_history()

    def append_ai_message(self, text):
        chunks = []
        # 使用正则表达式进行安全的分割，匹配位于行首的 ```
        # (?m) 开启多行模式，^ 匹配行首
        # 捕获组：(语言), (代码内容)
        pattern = re.compile(r'(?m)^```(\w*)\n([\s\S]*?)\n```')
        
        last_end = 0
        for match in pattern.finditer(text):
            # 添加之前的普通文本
            pre_text = text[last_end:match.start()].strip()
            if pre_text:
                chunks.append({'type': 'text', 'text': pre_text})
            
            lang = match.group(1).strip() or "CODE"
            code = match.group(2).strip()
            
            line_count = code.count('\n') + 1
            is_long = line_count > 15
            
            chunks.append({
                'type': 'code',
                'lang': lang.upper(),
                'code': code,
                'id': str(uuid.uuid4()),
                'expanded': not is_long,
                'line_count': line_count
            })
            
            last_end = match.end()
            
        # 添加剩余文本
        if last_end < len(text):
            post_text = text[last_end:].strip()
            if post_text:
                chunks.append({'type': 'text', 'text': post_text})
        
        self.history.append({'type': 'coder', 'content': chunks})
        self.render_all_history()

    def render_all_history(self):
        scrollbar = self.output_area.verticalScrollBar()
        was_at_bottom = scrollbar.value() == scrollbar.maximum()
        
        html_buffer = []
        
        for msg in self.history:
            if msg['type'] == 'system':
                html_buffer.append(f"<div style='color: #4ec9b0; margin: 10px 0; font-family: Consolas;'>[SYSTEM] {html.escape(msg['content'])}</div>")
            elif msg['type'] == 'user':
                safe_text = html.escape(msg['content']).replace('\n', '<br>')
                html_buffer.append(f"<div style='margin-top: 20px; margin-bottom: 10px; color: #d4d4d4;'><span style='color: #569cd6; font-weight: bold; font-family: Consolas;'>user@local:~$</span> <span style='font-family: Consolas;'>{safe_text}</span></div>")
            elif msg['type'] == 'coder':
                html_buffer.append(f"<div style='margin-top: 10px; margin-bottom: 5px;'><span style='color: #ce9178; font-weight: bold; font-family: Consolas;'>coder@remote:~$</span></div>")
                for chunk in msg['content']:
                    if chunk['type'] == 'text':
                        safe_text = html.escape(chunk['text']).replace('\n', '<br>')
                        html_buffer.append(f"<div style='color: #cccccc; padding: 2px 15px; text-align: left; font-family: \"Segoe UI\", \"Microsoft YaHei\", sans-serif;'>{safe_text}</div>")
                    elif chunk['type'] == 'code':
                        code_text = chunk['code']
                        if not chunk['expanded']:
                            lines = code_text.split('\n')
                            code_text = "\n".join(lines[:10]) + f"\n... (Total {chunk['line_count']} lines) ..."
                            toggle_text = f"[+] Show All ({chunk['line_count']} lines)"
                        else:
                            toggle_text = "[-]"
                            
                        highlighted = highlight_code_html(code_text)
                        html_buffer.append(f"""
                        <div style='background-color: #0d0d0d; border: 1px solid #333; border-left: 3px solid #0e639c; border-radius: 4px; margin: 10px 0;'>
                            <div style='background-color: #1e1e1e; color: #888; font-size: 10px; padding: 4px 10px; border-bottom: 1px solid #333; font-family: Consolas; display: flex; justify-content: space-between;'>
                                <span>{chunk['lang']}</span>
                                <a href='toggle://{chunk['id']}' style='color: #569cd6; text-decoration: none; font-weight: bold; float: right;'>{toggle_text}</a>
                            </div>
                            <pre style='color: #d4d4d4; font-family: Consolas, \"Microsoft YaHei\", monospace; font-size: 13px; padding: 10px; margin: 0; white-space: pre-wrap; text-align: left;'>{highlighted}</pre>
                        </div>""")
                html_buffer.append("<div style='border-bottom: 1px dashed #333; margin: 15px 0;'></div>")

        if self.is_processing:
            html_buffer.append("<div style='color: #6a9955; font-family: Consolas; margin-left: 15px; margin-top: 5px;'>// Processing...</div>")

        self.output_area.setHtml("".join(html_buffer))
        if was_at_bottom: scrollbar.setValue(scrollbar.maximum())