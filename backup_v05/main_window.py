"""SKYFALL desktop UI with Copilot chat and local conversation history."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from integrations.copilot.copilot_service import CopilotWorker
from memory.conversation_store import ConversationRecord, ConversationStore, MessageRecord


WELCOME_TEXT = (
    "Hello. I'm SKYFALL, your personal engineering assistant. I can help you "
    "think through Azure, Power Platform, Dynamics 365, Dataverse, PowerShell, "
    "Python and engineering automation. Conversation history is saved locally. "
    "Operational tools, workspace access and cloud actions are not enabled yet."
)


class FloatingAssistant(QDialog):
    """Compact entry point that sends messages to the current main conversation."""

    message_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("SKYFALL Assistant")
        self.setMinimumWidth(390)
        self.setMaximumWidth(470)
        self.setStyleSheet("background:#0E1528; color:#E8ECF5;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("SKYFALL")
        title.setStyleSheet("font-size:18px;font-weight:800;letter-spacing:3px;color:#F4F7FD;")
        subtitle = QLabel("PERSONAL ENGINEERING INTELLIGENCE")
        subtitle.setStyleSheet("font-size:9px;color:#8291AA;letter-spacing:1px;")
        brand_col = QVBoxLayout()
        brand_col.addWidget(title)
        brand_col.addWidget(subtitle)
        header.addLayout(brand_col)
        header.addStretch(1)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setStyleSheet(
            "background:#17243A;border:1px solid #2D405C;border-radius:8px;font-size:18px;"
        )
        close_button.clicked.connect(self.hide)
        header.addWidget(close_button)
        layout.addLayout(header)

        info = QLabel(
            "Messages are sent to your current SKYFALL conversation. "
            "Operational tools are not enabled in this release."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#AAB7CA;font-size:12px;padding:10px;background:#121E32;"
            "border:1px solid #293A55;border-radius:9px;"
        )
        layout.addWidget(info)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Skyfall...")
        self.input.setStyleSheet(
            "background:#101A2D;border:1px solid #30425E;border-radius:9px;"
            "padding:11px;color:#F1F5FB;"
        )
        self.input.returnPressed.connect(self._submit)
        send = QPushButton("Send")
        send.setStyleSheet(
            "background:#3478C8;border:1px solid #4B91E0;border-radius:9px;"
            "padding:10px 14px;font-weight:650;"
        )
        send.clicked.connect(self._submit)
        row.addWidget(self.input, 1)
        row.addWidget(send)
        layout.addLayout(row)

    def _submit(self) -> None:
        message = self.input.text().strip()
        if not message:
            return
        self.input.clear()
        self.message_submitted.emit(message)


class MainWindow(QMainWindow):
    NAV_ITEMS = [
        ("Overview", "overview"),
        ("Chat", "chat"),
        ("Workspaces", "workspaces"),
        ("Azure", "azure"),
        ("Power Platform", "power_platform"),
        ("Executions", "executions"),
        ("Reports", "reports"),
        ("Settings", "settings"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SKYFALL — Personal Engineering Intelligence")
        self.resize(1420, 900)
        self.setMinimumSize(1080, 700)

        self.conversation_store = ConversationStore()
        self.current_conversation = self.conversation_store.get_or_create_active_conversation()
        self._pending_conversation_id: str | None = None

        self.metric_values: dict[str, QLabel] = {}
        self.status_labels: dict[str, QLabel] = {}
        self._active_reply_label: QLabel | None = None
        self._active_reply_text = ""
        self._request_active = False

        self.nav_buttons: dict[str, QPushButton] = {}
        self.page_titles: dict[str, str] = {key: label for label, key in self.NAV_ITEMS}
        self.chat_layout: QVBoxLayout | None = None
        self.chat_scroll: QScrollArea | None = None
        self.history_list: QListWidget | None = None
        self.new_chat_button: QPushButton | None = None
        self.chat_input: QLineEdit | None = None
        self.chat_send_button: QPushButton | None = None

        self.floating = FloatingAssistant(self)
        self.floating.message_submitted.connect(self._handle_floating_message)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        content_host = QWidget()
        content_host.setObjectName("contentHost")
        content_layout = QVBoxLayout(content_host)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.top_bar = self._build_top_bar()
        content_layout.addWidget(self.top_bar)

        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        self.pages["overview"] = self._build_overview()
        self.pages["chat"] = self._build_chat_page()
        self.pages["workspaces"] = self._build_placeholder_page(
            "Workspace intelligence",
            "Connect approved engineering folders so SKYFALL can catalogue scripts, documentation and project structure.",
            ["Add approved workspace folders", "Index supported file types", "Discover scripts and dependencies"],
        )
        self.pages["azure"] = self._build_placeholder_page(
            "Azure",
            "Azure account discovery and resource inventory will appear here after the Azure connector is configured.",
            ["Connect Microsoft account", "Discover accessible tenants and subscriptions", "Explore resources and Function Apps"],
        )
        self.pages["power_platform"] = self._build_placeholder_page(
            "Power Platform",
            "Power Platform environment discovery and operational capabilities will appear here after authentication is configured.",
            ["Connect Microsoft account", "Discover environments", "Explore flows, solutions and Dataverse"],
        )
        self.pages["executions"] = self._build_placeholder_page(
            "Execution centre",
            "Approved script and tool executions will be tracked here. Operational execution is not enabled yet.",
            ["Execution plans", "Approval queue", "Live logs and results"],
        )
        self.pages["reports"] = self._build_placeholder_page(
            "Reports library",
            "Reports generated by SKYFALL will be organized here once reporting tools are connected.",
            ["Azure inventories", "Power Platform inventories", "Custom report templates"],
        )
        self.pages["settings"] = self._build_settings_page()

        for page in self.pages.values():
            self.stack.addWidget(page)

        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content_host, 1)
        self.setCentralWidget(root)

        self._select_page("overview")
        self._install_shortcuts()
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self._render_conversation(self.current_conversation.id)

        self.statusBar().showMessage("SKYFALL desktop ready · Starting Copilot AI runtime...")
        self.statusBar().setStyleSheet(
            "background:#0E1528;color:#8291AA;border-top:1px solid #202B43;padding:4px;"
        )

        self.copilot_worker = CopilotWorker(
            session_id=self.current_conversation.copilot_session_id,
            resume_existing=self.current_conversation.sdk_session_initialized,
            parent=self,
        )
        self.copilot_worker.status_changed.connect(self._on_ai_status_changed)
        self.copilot_worker.connected.connect(self._on_ai_connected)
        self.copilot_worker.connection_failed.connect(self._on_ai_connection_failed)
        self.copilot_worker.response_chunk.connect(self._on_response_chunk)
        self.copilot_worker.response_finished.connect(self._on_response_finished)
        self.copilot_worker.response_failed.connect(self._on_response_failed)
        self.copilot_worker.conversation_opened.connect(self._on_conversation_opened)
        self.copilot_worker.conversation_open_failed.connect(self._on_conversation_open_failed)
        self.copilot_worker.start()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(17, 22, 17, 18)
        layout.setSpacing(8)

        brand_row = QHBoxLayout()
        mark = QFrame()
        mark.setObjectName("brandMark")
        mark.setFixedSize(43, 43)
        mark_layout = QVBoxLayout(mark)
        mark_layout.setContentsMargins(0, 0, 0, 0)
        letter = QLabel("S")
        letter.setObjectName("brandLetter")
        letter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark_layout.addWidget(letter)
        brand_text = QVBoxLayout()
        name = QLabel("SKYFALL")
        name.setObjectName("brandName")
        caption = QLabel("ENGINEERING INTELLIGENCE")
        caption.setObjectName("brandCaption")
        brand_text.addWidget(name)
        brand_text.addWidget(caption)
        brand_row.addWidget(mark)
        brand_row.addSpacing(10)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        layout.addLayout(brand_row)
        layout.addSpacing(26)

        section = QLabel("WORKSPACE")
        section.setObjectName("eyebrow")
        layout.addWidget(section)

        for label, key in self.NAV_ITEMS:
            button = QPushButton(f"   {label}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, page=key: self._select_page(page))
            self.nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        floating_button = QPushButton("＋  Open floating assistant")
        floating_button.setObjectName("secondaryButton")
        floating_button.clicked.connect(self._show_floating)
        layout.addWidget(floating_button)

        account = QFrame()
        account.setObjectName("accountPanel")
        account_layout = QVBoxLayout(account)
        account_layout.setContentsMargins(12, 12, 12, 12)
        account_layout.setSpacing(7)
        account_title = QLabel("LOCAL SESSION")
        account_title.setObjectName("eyebrow")
        account_layout.addWidget(account_title)
        account_layout.addWidget(self._status_row("Copilot CLI", "Signed in", "good"))
        account_layout.addWidget(self._status_row("SKYFALL AI runtime", "Connecting...", "pending"))
        layout.addWidget(account)
        return sidebar

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(70)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(27, 0, 27, 0)
        title = QLabel("Overview")
        title.setObjectName("pageTitle")
        self.top_title = title
        layout.addWidget(title)
        layout.addStretch(1)
        state = QLabel("●  AI CONNECTING")
        state.setObjectName("statusPending")
        self.top_state = state
        layout.addWidget(state)
        return bar

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 27, 30, 26)
        layout.setSpacing(20)

        greeting = QLabel("Your engineering workspace, in one place.")
        greeting.setStyleSheet("font-size:25px;font-weight:750;color:#F4F7FD;")
        sub = QLabel(
            "Your personal engineering assistant is online. Conversation history is stored locally; "
            "cloud operations will be introduced after the tool-security layer."
        )
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        layout.addWidget(greeting)
        layout.addWidget(sub)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        metrics.addWidget(self._metric_card("DESKTOP", "Running", "Local interface is active", "good"))
        metrics.addWidget(self._metric_card("COPILOT CLI", "Signed in", "CLI authentication detected", "good"))
        metrics.addWidget(self._metric_card("AI RUNTIME", "Connecting...", "Starting Copilot SDK session", "pending"))
        metrics.addWidget(self._metric_card("LOCAL MEMORY", "Ready", "Conversation history stored locally", "good"))
        layout.addLayout(metrics)

        quick_title = QLabel("Quick actions")
        quick_title.setObjectName("sectionTitle")
        layout.addWidget(quick_title)

        quick_grid = QHBoxLayout()
        quick_grid.setSpacing(12)
        quick_actions = [
            ("Azure inventory", "Fetch Function Apps across accessible subscriptions", "Fetch all Function Apps across my accessible Azure subscriptions and prepare a detailed Excel report."),
            ("Flow inventory", "Collect cloud flows from a selected environment", "Find the existing Power Automate flow inventory script and prepare to run it in QA."),
            ("Environment comparison", "Compare resources or configurations", "Prepare a comparison between my QA and PROD environments."),
            ("Run a script", "Discover and validate existing automation", "Find the appropriate existing PowerShell script for my requested operation."),
        ]
        for title, description, prompt in quick_actions:
            quick_grid.addWidget(self._quick_card(title, description, prompt))
        layout.addLayout(quick_grid)

        activity_title = QLabel("Getting started")
        activity_title.setObjectName("sectionTitle")
        layout.addWidget(activity_title)
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 17, 18, 17)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(QLabel("Your local desktop foundation is ready."))
        note = QLabel(
            "SKYFALL now retains separate conversations locally and can resume their Copilot sessions. "
            "This release remains conversational only: no SKYFALL MCP tools, Azure actions, "
            "Power Platform actions or local script execution are enabled."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        panel_layout.addWidget(note)
        layout.addWidget(panel)
        layout.addStretch(1)
        return page

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(14)

        history_panel = QFrame()
        history_panel.setObjectName("chatHistoryPanel")
        history_panel.setFixedWidth(238)
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(12, 14, 12, 12)
        history_layout.setSpacing(10)

        history_header = QLabel("CONVERSATIONS")
        history_header.setObjectName("eyebrow")
        history_layout.addWidget(history_header)

        self.new_chat_button = QPushButton("＋  New conversation")
        self.new_chat_button.setObjectName("secondaryButton")
        self.new_chat_button.clicked.connect(self._create_new_conversation)
        history_layout.addWidget(self.new_chat_button)

        self.history_list = QListWidget()
        self.history_list.setObjectName("conversationList")
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.currentItemChanged.connect(self._on_history_selection_changed)
        history_layout.addWidget(self.history_list, 1)

        history_note = QLabel("Your chat history is stored in the local SKYFALL database.")
        history_note.setObjectName("muted")
        history_note.setWordWrap(True)
        history_layout.addWidget(history_note)
        body.addWidget(history_panel)

        conversation_panel = QWidget()
        conversation_layout = QVBoxLayout(conversation_panel)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_layout.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("Talk to SKYFALL")
        title.setStyleSheet("font-size:23px;font-weight:750;color:#F4F7FD;")
        subtitle = QLabel(
            "Your Copilot conversation is private to your signed-in account and this local application. "
            "Operational tools are not enabled yet."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        self.chat_subtitle = subtitle
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        conversation_layout.addLayout(header)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setObjectName("chatScroll")
        messages_host = QWidget()
        self.chat_layout = QVBoxLayout(messages_host)
        self.chat_layout.setContentsMargins(4, 8, 4, 8)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch(1)
        self.chat_scroll.setWidget(messages_host)
        conversation_layout.addWidget(self.chat_scroll, 1)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setPlaceholderText("Ask SKYFALL to explain, plan or help with an engineering problem...")
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.chat_send_button = QPushButton("Send")
        self.chat_send_button.setObjectName("primaryButton")
        self.chat_send_button.clicked.connect(self._send_chat_message)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.chat_send_button)
        conversation_layout.addLayout(input_row)

        body.addWidget(conversation_panel, 1)
        layout.addLayout(body, 1)
        return page

    def _build_placeholder_page(self, title: str, description: str, items: list[str]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        desc = QLabel(description)
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(14)
        panel_layout.addWidget(self._status_row("Integration status", "Not connected", "offline"))
        for item in items:
            line = QLabel(f"•  {item}")
            line.setStyleSheet("color:#B8C5D8;font-size:13px;padding:5px 0;")
            panel_layout.addWidget(line)
        layout.addWidget(panel)
        layout.addStretch(1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "SKYFALL stores its conversation index and visible chat history locally. "
            "Voice, account management, startup and operational controls will be added in later milestones."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)
        panel_layout.addWidget(self._section_label("APPLICATION"))
        panel_layout.addWidget(self._status_row("Version", "0.4.0", "good"))
        panel_layout.addWidget(self._status_row("Runtime", "Local desktop", "good"))
        panel_layout.addWidget(self._status_row("AI provider", "GitHub Copilot", "good"))
        panel_layout.addWidget(self._status_row("MCP integration", "Not configured", "offline"))
        database_label = QLabel(
            f"Local conversation database (not app-encrypted): {self.conversation_store.database_path}"
        )
        database_label.setObjectName("muted")
        database_label.setWordWrap(True)
        panel_layout.addWidget(database_label)
        layout.addWidget(panel)
        layout.addStretch(1)
        return page

    def _metric_card(self, label: str, value: str, detail: str, status: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setMinimumHeight(126)
        box = QVBoxLayout(card)
        box.setContentsMargins(15, 14, 15, 14)
        box.setSpacing(7)
        lbl = QLabel(label)
        lbl.setObjectName("metricLabel")
        val = QLabel(value)
        val.setObjectName("metricValue")
        val.setStyleSheet("font-size:19px;font-weight:750;color:#F6F8FC;")
        self.metric_values[label] = val
        det = QLabel(detail)
        det.setObjectName("muted")
        det.setWordWrap(True)
        box.addWidget(lbl)
        box.addWidget(val)
        box.addWidget(det)
        return card

    def _quick_card(self, title: str, description: str, prompt: str) -> QFrame:
        card = QFrame()
        card.setObjectName("quickCard")
        card.setMinimumWidth(150)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 15, 14, 14)
        box.setSpacing(10)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:13px;font-weight:700;color:#EAF0F9;")
        body = QLabel(description)
        body.setObjectName("muted")
        body.setWordWrap(True)
        button = QPushButton("Prepare request  →")
        button.setObjectName("secondaryButton")
        button.clicked.connect(lambda checked=False, p=prompt: self._open_chat_with_prompt(p))
        box.addWidget(heading)
        box.addWidget(body, 1)
        box.addWidget(button)
        return card

    def _status_row(self, label: str, value: str, state: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        name = QLabel(label)
        name.setStyleSheet("color:#AAB7CA;font-size:11px;")
        status = QLabel(value)
        status.setObjectName(
            {"good": "statusGood", "pending": "statusPending", "offline": "statusOffline"}.get(state, "statusOffline")
        )
        self.status_labels[label] = status
        layout.addWidget(name)
        layout.addStretch(1)
        layout.addWidget(status)
        return row

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("eyebrow")
        return label

    def _select_page(self, key: str) -> None:
        if key not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[key])
        self.top_title.setText(self.page_titles.get(key, "SKYFALL"))
        for nav_key, button in self.nav_buttons.items():
            button.setChecked(nav_key == key)

    def _install_shortcuts(self) -> None:
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        shortcut.activated.connect(self._show_floating)

    def _show_floating(self) -> None:
        self.floating.show()
        self.floating.raise_()
        self.floating.activateWindow()

    def _open_chat_with_prompt(self, prompt: str) -> None:
        self._select_page("chat")
        self.chat_input.setText(prompt)
        self.chat_input.setFocus()

    def _send_chat_message(self) -> None:
        message = self.chat_input.text().strip()
        if not message:
            return
        self.chat_input.clear()
        self._submit_to_copilot(message)

    def _handle_floating_message(self, message: str) -> None:
        self._select_page("chat")
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._submit_to_copilot(message)

    def _submit_to_copilot(self, message: str) -> None:
        if self._request_active:
            QMessageBox.information(
                self,
                "SKYFALL is responding",
                "Please wait for the current response to finish before sending another message.",
            )
            return

        if not self.copilot_worker.is_connected:
            self._add_message(
                "SKYFALL",
                "The Copilot session is not connected. Check the AI runtime status and try again. "
                "No tools or external operations were run.",
                assistant=True,
            )
            return

        self.conversation_store.add_message(self.current_conversation.id, "user", message)
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self._add_message("YOU", message, assistant=False)

        self._request_active = True
        self._active_reply_text = ""
        self._active_reply_label = self._add_message("SKYFALL", "Thinking...", assistant=True)
        self.chat_input.setEnabled(False)
        self.chat_send_button.setEnabled(False)
        self.new_chat_button.setEnabled(False)
        self.history_list.setEnabled(False)
        self.statusBar().showMessage("SKYFALL is waiting for Copilot...")

        if not self.copilot_worker.send_prompt(message):
            self._on_response_failed("The Copilot worker is busy or unavailable. Please try again.")

    def _on_ai_status_changed(self, status: str) -> None:
        self.statusBar().showMessage(f"SKYFALL AI runtime: {status}")

    def _on_ai_connected(self) -> None:
        self._set_status_value("AI RUNTIME", "Connected")
        self._set_status_value("SKYFALL AI runtime", "Connected", "good")
        self._set_status_value("AI provider", "GitHub Copilot connected", "good")
        self.top_state.setText("●  COPILOT CONNECTED")
        self.top_state.setObjectName("statusGood")
        self.top_state.style().unpolish(self.top_state)
        self.top_state.style().polish(self.top_state)
        self.chat_subtitle.setText(
            "Connected to your signed-in GitHub Copilot account. Conversation text is sent to Copilot "
            "and saved locally. SKYFALL tools, MCP servers and cloud operations are not enabled yet."
        )
        self.chat_input.setEnabled(True)
        self.chat_send_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.history_list.setEnabled(True)
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self.statusBar().showMessage("SKYFALL AI connected · Local conversation memory enabled · No operational tools enabled")

    def _on_ai_connection_failed(self, error: str) -> None:
        self._set_status_value("AI RUNTIME", "Connection failed")
        self._set_status_value("SKYFALL AI runtime", "Connection failed", "offline")
        self._set_status_value("AI provider", "Connection failed", "offline")
        self.top_state.setText("●  AI OFFLINE")
        self.top_state.setObjectName("statusOffline")
        self.top_state.style().unpolish(self.top_state)
        self.top_state.style().polish(self.top_state)
        self.chat_subtitle.setText(
            "Copilot could not connect. Check the details in the conversation. "
            "No tools or cloud operations are enabled."
        )
        self._add_message("SKYFALL", f"I couldn't connect to Copilot.\n\n{error}", assistant=True)
        self.statusBar().showMessage("SKYFALL AI connection failed")

    def _set_status_value(self, key: str, value: str, state: str | None = None) -> None:
        metric = self.metric_values.get(key)
        if metric is not None:
            metric.setText(value)

        status = self.status_labels.get(key)
        if status is not None:
            status.setText(value)
            if state:
                status.setObjectName(
                    {"good": "statusGood", "pending": "statusPending", "offline": "statusOffline"}.get(state, "statusOffline")
                )
                status.style().unpolish(status)
                status.style().polish(status)

    def _on_response_chunk(self, chunk: str) -> None:
        if self._active_reply_label is None:
            return
        if not self._active_reply_text:
            self._active_reply_label.setText("")
        self._active_reply_text += chunk
        self._active_reply_label.setText(self._active_reply_text)
        self._scroll_chat_to_bottom()

    def _on_response_finished(self) -> None:
        final_text = self._active_reply_text.strip()
        if self._active_reply_label is not None and not final_text:
            final_text = "Copilot completed the turn without text."
            self._active_reply_label.setText(final_text)
        if final_text:
            self.conversation_store.add_message(
                self.current_conversation.id,
                "assistant",
                final_text,
                status="complete",
            )
        self.conversation_store.set_sdk_session_initialized(self.current_conversation.id, True)
        self.current_conversation = self.conversation_store.get_conversation(self.current_conversation.id) or self.current_conversation
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self._finish_current_request()
        self.statusBar().showMessage("SKYFALL response received and saved locally")

    def _on_response_failed(self, error: str) -> None:
        if self._active_reply_label is not None:
            if self._active_reply_text:
                text = self._active_reply_text + "\n\n[Response interrupted]\n" + error
                stored_text = self._active_reply_text
                stored_status = "interrupted"
            else:
                text = "I couldn't complete that response.\n\n" + error
                stored_text = error
                stored_status = "failed"
            self._active_reply_label.setText(text)
            self.conversation_store.add_message(
                self.current_conversation.id,
                "assistant",
                stored_text,
                status=stored_status,
            )
            self.conversation_store.set_sdk_session_initialized(self.current_conversation.id, True)
        else:
            self._add_message("SKYFALL", f"Copilot error: {error}", assistant=True)
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self._finish_current_request()
        self.statusBar().showMessage("SKYFALL response failed")

    def _finish_current_request(self) -> None:
        self._request_active = False
        self._active_reply_label = None
        self._active_reply_text = ""
        self.chat_input.setEnabled(True)
        self.chat_send_button.setEnabled(True)
        self.new_chat_button.setEnabled(self.copilot_worker.is_connected)
        self.history_list.setEnabled(self.copilot_worker.is_connected)
        self.chat_input.setFocus()

    def _create_new_conversation(self) -> None:
        if self._request_active or self.copilot_worker.is_busy:
            QMessageBox.information(
                self,
                "Conversation in progress",
                "Wait for the current operation to finish before starting a new conversation.",
            )
            return
        if not self.copilot_worker.is_connected:
            QMessageBox.warning(
                self,
                "Copilot is not connected",
                "SKYFALL must be connected to Copilot before opening a new conversation.",
            )
            return
        conversation = self.conversation_store.create_conversation()
        self._request_conversation_switch(conversation.id)

    def _on_history_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        conversation_id = current.data(Qt.ItemDataRole.UserRole)
        if conversation_id and conversation_id != self.current_conversation.id:
            self._request_conversation_switch(str(conversation_id))

    def _request_conversation_switch(self, conversation_id: str) -> None:
        if self._request_active or self.copilot_worker.is_busy:
            self._restore_history_selection()
            return
        conversation = self.conversation_store.get_conversation(conversation_id)
        if conversation is None:
            self._restore_history_selection()
            return
        if conversation.id == self.current_conversation.id:
            return

        self._pending_conversation_id = conversation.id
        self.new_chat_button.setEnabled(False)
        self.history_list.setEnabled(False)
        self.statusBar().showMessage(f"Opening conversation: {conversation.title}")
        accepted = self.copilot_worker.switch_conversation(
            conversation.copilot_session_id,
            resume=conversation.sdk_session_initialized,
        )
        if not accepted:
            self._pending_conversation_id = None
            self.new_chat_button.setEnabled(True)
            self.history_list.setEnabled(True)
            self._restore_history_selection()
            self.statusBar().showMessage("Could not switch conversations")

    def _on_conversation_opened(self, copilot_session_id: str) -> None:
        pending_id = self._pending_conversation_id
        if pending_id is None:
            return
        conversation = self.conversation_store.get_conversation(pending_id)
        if conversation is None or conversation.copilot_session_id != copilot_session_id:
            return

        self.current_conversation = conversation
        self.conversation_store.set_active_conversation(conversation.id)
        self._pending_conversation_id = None
        self._refresh_conversation_list(select_id=conversation.id)
        self._render_conversation(conversation.id)
        self.new_chat_button.setEnabled(True)
        self.history_list.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.chat_send_button.setEnabled(True)
        self.statusBar().showMessage(f"Conversation opened · {conversation.title}")

    def _on_conversation_open_failed(self, copilot_session_id: str, error: str) -> None:
        self._pending_conversation_id = None
        self.new_chat_button.setEnabled(True)
        self.history_list.setEnabled(True)
        self._restore_history_selection()
        self.statusBar().showMessage("Unable to open conversation")
        QMessageBox.warning(
            self,
            "Unable to open conversation",
            "SKYFALL could not resume or create that Copilot conversation. "
            "Your local chat history has been preserved.\n\n" + error,
        )

    def _refresh_conversation_list(self, select_id: str | None = None) -> None:
        if self.history_list is None:
            return
        self.history_list.blockSignals(True)
        self.history_list.clear()
        selected_item = None
        for record in self.conversation_store.list_conversations(limit=200):
            item = QListWidgetItem(record.title)
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setToolTip(f"{record.title}\n{record.message_count} messages\nUpdated: {record.updated_at}")
            self.history_list.addItem(item)
            if record.id == select_id:
                selected_item = item
        if selected_item is not None:
            self.history_list.setCurrentItem(selected_item)
        self.history_list.blockSignals(False)

    def _restore_history_selection(self) -> None:
        self._refresh_conversation_list(select_id=self.current_conversation.id)

    def _render_conversation(self, conversation_id: str) -> None:
        self._clear_chat_messages()
        messages = self.conversation_store.get_messages(conversation_id)
        if not messages:
            self._add_message("SKYFALL", WELCOME_TEXT, assistant=True)
            return
        for record in messages:
            self._render_stored_message(record)

    def _render_stored_message(self, record: MessageRecord) -> None:
        sender = "YOU" if record.role == "user" else "SKYFALL"
        text = record.content
        if record.status not in {"complete", "sent"}:
            text = f"{text}\n\n[{record.status.upper()}]"
        self._add_message(sender, text, assistant=(record.role != "user"))

    def _clear_chat_messages(self) -> None:
        if self.chat_layout is None:
            return
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        worker = getattr(self, "copilot_worker", None)
        if worker is not None:
            worker.shutdown()
        super().closeEvent(event)

    def _add_message(self, sender: str, text: str, assistant: bool) -> QLabel | None:
        if self.chat_layout is None:
            return None
        bubble = QFrame()
        bubble.setObjectName("assistantMessage" if assistant else "userMessage")
        bubble.setMaximumWidth(850)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 11, 14, 11)
        bubble_layout.setSpacing(6)
        sender_label = QLabel(sender)
        sender_label.setObjectName("eyebrow")
        message_label = QLabel(text)
        message_label.setObjectName("messageText")
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble_layout.addWidget(sender_label)
        bubble_layout.addWidget(message_label)

        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        if assistant:
            wrapper_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            wrapper_layout.addStretch(1)
        else:
            wrapper_layout.addStretch(1)
            wrapper_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        self.chat_layout.insertWidget(max(0, self.chat_layout.count() - 1), wrapper)
        self._scroll_chat_to_bottom()
        return message_label

    def _scroll_chat_to_bottom(self) -> None:
        if self.chat_scroll is not None:
            QTimer.singleShot(
                40,
                lambda: self.chat_scroll
                and self.chat_scroll.verticalScrollBar().setValue(
                    self.chat_scroll.verticalScrollBar().maximum()
                ),
            )
