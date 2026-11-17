"""SKYFALL desktop UI with Copilot chat and local conversation history."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from integrations.copilot.copilot_service import CopilotWorker
from memory.conversation_store import ConversationRecord, ConversationStore, MessageRecord
from skyfall_mcp.registry import CapabilityRegistry
from skyfall_workspace.manager import WorkspaceManager
from skyfall_workspace.worker import WorkspaceScanWorker
from skyfall_cloud.azure_profiles import AzureProfileManager
from skyfall_cloud.powerplatform import PowerPlatformDiscovery
from skyfall_cloud.worker import MicrosoftDiscoveryWorker


WELCOME_TEXT = (
    "Hello. I'm SKYFALL, your personal engineering assistant. I can help you "
    "think through Azure, Power Platform, Dynamics 365, Dataverse, PowerShell, "
    "Python and engineering automation. Conversation history is saved locally. "
    "SKYFALL can discover metadata in folders you explicitly add and approve for AI metadata sharing. "
    "Source code is not returned by workspace tools. Azure and Power Platform account discovery is read-only; resource changes and script execution are not enabled."
)


class MarkdownMessageLabel(QLabel):
    """QLabel that renders Copilot Markdown via Qt's Markdown parser."""

    MARKDOWN_CSS = r"""
    body { color: #E8ECF5; font-family: 'Segoe UI'; font-size: 13px; }
    p { margin: 0 0 7px 0; }
    h1, h2, h3, h4 { color: #F4F7FD; margin: 8px 0 5px 0; }
    a { color: #8BC5FF; }
    code { color: #B9D9FF; background-color: #1B2A42; font-family: Consolas; }
    pre { color: #DCE8F8; background-color: #0B1424; padding: 8px; font-family: Consolas; }
    blockquote { color: #B8C5D8; background-color: #15233A; }
    table { border-collapse: collapse; }
    th, td { border: 1px solid #33445F; padding: 4px 7px; }
    th { color: #F4F7FD; background-color: #1B2A42; }
    li { margin-bottom: 3px; }
    """

    def set_markdown(self, text: str) -> None:
        document = QTextDocument()
        document.setDefaultFont(self.font())
        document.setDefaultStyleSheet(self.MARKDOWN_CSS)
        document.setMarkdown(text or "")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setText(document.toHtml())
        self.setWordWrap(True)



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
            "Read-only core and opt-in workspace metadata tools are available; source code and script execution are not."
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
        ("Capabilities", "capabilities"),
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
        self.workspace_manager = WorkspaceManager()
        self._workspace_scan_worker: WorkspaceScanWorker | None = None
        self.current_conversation = self.conversation_store.get_or_create_active_conversation()
        self._pending_conversation_id: str | None = None

        self.metric_values: dict[str, QLabel] = {}
        self.status_labels: dict[str, QLabel] = {}
        self._active_reply_label: MarkdownMessageLabel | None = None
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
        self.workspace_list: QListWidget | None = None
        self.workspace_ai_checkbox: QCheckBox | None = None
        self.workspace_status_label: QLabel | None = None
        self.workspace_search_input: QLineEdit | None = None
        self.workspace_results_list: QListWidget | None = None
        self.workspace_scan_buttons: list[QPushButton] = []
        self.workspace_manage_buttons: list[QPushButton] = []
        self.azure_profile_manager = AzureProfileManager()
        self.powerplatform_discovery = PowerPlatformDiscovery()
        self._microsoft_worker: MicrosoftDiscoveryWorker | None = None
        self.azure_profile_combo: QComboBox | None = None
        self.azure_status_label: QLabel | None = None
        self.azure_tenant_label: QLabel | None = None
        self.azure_subscriptions_table: QTableWidget | None = None
        self.pp_status_label: QLabel | None = None
        self.pp_profiles_table: QTableWidget | None = None
        self.pp_environments_table: QTableWidget | None = None

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
        self.pages["capabilities"] = self._build_capabilities_page()
        self.pages["workspaces"] = self._build_workspaces_page()
        self.pages["azure"] = self._build_azure_page()
        self.pages["power_platform"] = self._build_power_platform_page()
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
        self._refresh_workspace_list()
        self._refresh_azure_profile_choices()

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
        account_layout.addWidget(self._status_row("MCP Tools", "Starting...", "pending"))
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
            ("Azure inventory", "Discover accessible Azure subscriptions", "Check my Azure account and list all accessible subscriptions."),
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
            "SKYFALL retains separate conversations locally and can resume Copilot sessions. "
            "SKYFALL Core and Workspace MCP expose read-only status, capability discovery and metadata-only "
            "workspace search. Azure subscription discovery and Power Platform PAC profile/environment "
            "discovery are now available in read-only mode. Resource modification and script execution remain disabled."
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

    def _build_capabilities_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)

        title = QLabel("SKYFALL Capabilities")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        intro = QLabel(
            "These are the registered read-only MCP tools. Workspace discovery returns metadata only "
            "for folders you explicitly approved for Copilot metadata sharing."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        summary = QFrame()
        summary.setObjectName("panel")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(8)
        summary_layout.addWidget(self._status_row("MCP server", "SKYFALL Local Intelligence · stdio", "good"))
        summary_layout.addWidget(self._status_row("Execution policy", "Read-only core + workspace metadata", "good"))
        summary_layout.addWidget(self._status_row("Azure / Power Platform", "Not connected", "offline"))
        summary_layout.addWidget(self._status_row("Workspace discovery", "Metadata-only · opt-in", "good"))
        layout.addWidget(summary)

        try:
            capabilities = CapabilityRegistry.default().list(enabled_only=True)
        except Exception as exc:
            error = QLabel(f"Capability catalogue could not be loaded: {exc}")
            error.setObjectName("muted")
            error.setWordWrap(True)
            layout.addWidget(error)
            capabilities = []

        heading = QLabel(f"REGISTERED TOOLS · {len(capabilities)}")
        heading.setObjectName("eyebrow")
        layout.addWidget(heading)

        for capability in capabilities:
            card = QFrame()
            card.setObjectName("quickCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(7)

            name = QLabel(capability.name)
            name.setStyleSheet("font-size:14px;font-weight:750;color:#F4F7FD;")
            tool = QLabel(capability.tool_name)
            tool.setObjectName("eyebrow")
            description = QLabel(capability.description)
            description.setObjectName("muted")
            description.setWordWrap(True)
            badge = QLabel("READ ONLY · NO APPROVAL REQUIRED")
            badge.setObjectName("statusGood")
            card_layout.addWidget(name)
            card_layout.addWidget(tool)
            card_layout.addWidget(description)
            card_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(card)

        note = QLabel(
            "Workspace tools are read-only and expose only locally extracted metadata from roots you approved. "
            "They do not return source code, execute scripts, or modify files. Azure account/subscription "
            "and Power Platform profile/environment discovery are available as read-only capabilities in v0.7."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page


    def _build_workspaces_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)

        title = QLabel("Workspace Intelligence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        intro = QLabel(
            "Add engineering folders that SKYFALL may index locally. Indexing is read-only: "
            "it extracts filenames, file metadata and static script structure without executing or modifying files."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        privacy = QFrame()
        privacy.setObjectName("panel")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(14, 12, 14, 12)
        privacy_note = QLabel(
            "PRIVACY: Workspace indexing stays on this PC. Copilot cannot see a workspace until you "
            "explicitly enable metadata sharing for that folder. v0.7 shares only filenames, paths and "
            "extracted structural metadata—not source code. Known credential-file patterns and files "
            "flagged by heuristic secret detection are excluded from AI search. Detection is not a guarantee; "
            "do not add folders containing sensitive data unless policy permits sharing their metadata."
        )
        privacy_note.setWordWrap(True)
        privacy_note.setStyleSheet("color:#B8C5D8;font-size:12px;")
        privacy_layout.addWidget(privacy_note)
        layout.addWidget(privacy)

        toolbar = QHBoxLayout()
        add_button = QPushButton("＋  Add folder")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self._add_workspace_folder)
        toolbar.addWidget(add_button)
        self.workspace_manage_buttons.append(add_button)

        scan_selected = QPushButton("Scan selected")
        scan_selected.setObjectName("secondaryButton")
        scan_selected.clicked.connect(self._scan_selected_workspace)
        toolbar.addWidget(scan_selected)
        self.workspace_scan_buttons.append(scan_selected)

        scan_all = QPushButton("Scan all")
        scan_all.setObjectName("secondaryButton")
        scan_all.clicked.connect(self._scan_all_workspaces)
        toolbar.addWidget(scan_all)
        self.workspace_scan_buttons.append(scan_all)

        remove_button = QPushButton("Remove selected")
        remove_button.setObjectName("secondaryButton")
        remove_button.clicked.connect(self._remove_selected_workspace)
        toolbar.addWidget(remove_button)
        self.workspace_manage_buttons.append(remove_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.workspace_list = QListWidget()
        self.workspace_list.setObjectName("conversationList")
        self.workspace_list.setMinimumHeight(145)
        self.workspace_list.currentItemChanged.connect(self._on_workspace_selection_changed)
        layout.addWidget(self.workspace_list, 1)

        self.workspace_ai_checkbox = QCheckBox(
            "Allow Copilot to receive filenames and extracted metadata for the selected workspace"
        )
        self.workspace_ai_checkbox.setEnabled(False)
        self.workspace_ai_checkbox.setToolTip(
            "This does not share source code. It permits workspace MCP tools to return paths, filenames, "
            "static summaries, parameter names, imports and function names to Copilot."
        )
        self.workspace_ai_checkbox.toggled.connect(self._toggle_workspace_ai_metadata)
        layout.addWidget(self.workspace_ai_checkbox)

        self.workspace_status_label = QLabel(
            "No folders configured. Add a folder to begin local indexing."
        )
        self.workspace_status_label.setObjectName("muted")
        self.workspace_status_label.setWordWrap(True)
        layout.addWidget(self.workspace_status_label)

        search_header = QLabel("LOCAL INDEX SEARCH")
        search_header.setObjectName("eyebrow")
        layout.addWidget(search_header)
        search_row = QHBoxLayout()
        self.workspace_search_input = QLineEdit()
        self.workspace_search_input.setObjectName("chatInput")
        self.workspace_search_input.setPlaceholderText("Search script names, parameters, functions, imports or summaries...")
        self.workspace_search_input.returnPressed.connect(self._search_workspace_index)
        search_row.addWidget(self.workspace_search_input, 1)
        search_button = QPushButton("Search locally")
        search_button.setObjectName("secondaryButton")
        search_button.clicked.connect(self._search_workspace_index)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self.workspace_results_list = QListWidget()
        self.workspace_results_list.setObjectName("conversationList")
        self.workspace_results_list.setMinimumHeight(150)
        self.workspace_results_list.itemDoubleClicked.connect(self._show_workspace_file_details)
        layout.addWidget(self.workspace_results_list, 1)

        return page

    def _selected_workspace_id(self) -> str | None:
        if self.workspace_list is None or self.workspace_list.currentItem() is None:
            return None
        value = self.workspace_list.currentItem().data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _refresh_workspace_list(self, select_id: str | None = None) -> None:
        if self.workspace_list is None:
            return
        try:
            records = self.workspace_manager.list_workspaces()
        except Exception as exc:
            if self.workspace_status_label is not None:
                self.workspace_status_label.setText(f"Workspace database error: {exc}")
            return
        self.workspace_list.blockSignals(True)
        self.workspace_list.clear()
        selected = None
        for record in records:
            sharing = "AI metadata: ON" if record.allow_ai_metadata else "AI metadata: OFF"
            status = record.scan_status.replace("_", " ").upper()
            label = (
                f"{record.display_name}  ·  {record.file_count} indexed files\n"
                f"{record.path}\n{status}  ·  {sharing}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setToolTip(
                f"{record.path}\nEnabled: {record.enabled}\n"
                f"AI metadata sharing: {record.allow_ai_metadata}\n"
                f"Indexed files: {record.file_count}\nSkipped: {record.skipped_count}\n"
                f"Last scan: {record.last_scan_at or 'Never'}"
            )
            self.workspace_list.addItem(item)
            if record.id == select_id:
                selected = item
        if selected is not None:
            self.workspace_list.setCurrentItem(selected)
        elif self.workspace_list.count() > 0 and self.workspace_list.currentItem() is None:
            self.workspace_list.setCurrentRow(0)
        self.workspace_list.blockSignals(False)
        self._sync_workspace_checkbox()
        if self.workspace_status_label is not None:
            local_files = sum(record.file_count for record in records)
            shared = sum(1 for record in records if record.allow_ai_metadata and record.enabled)
            self.workspace_status_label.setText(
                f"{len(records)} configured workspaces · {local_files} indexed files · "
                f"{shared} workspace(s) explicitly shared with Copilot. Source files remain local."
            )

    def _sync_workspace_checkbox(self) -> None:
        if self.workspace_ai_checkbox is None:
            return
        workspace_id = self._selected_workspace_id()
        record = self.workspace_manager.get_workspace(workspace_id) if workspace_id else None
        self.workspace_ai_checkbox.blockSignals(True)
        self.workspace_ai_checkbox.setEnabled(record is not None and record.enabled)
        self.workspace_ai_checkbox.setChecked(bool(record and record.allow_ai_metadata))
        self.workspace_ai_checkbox.blockSignals(False)

    def _on_workspace_selection_changed(self, current, previous) -> None:
        self._sync_workspace_checkbox()

    def _add_workspace_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Add an engineering workspace", str(Path.home())
        )
        if not selected:
            return
        try:
            record = self.workspace_manager.add_workspace(selected, allow_ai_metadata=False)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot add workspace", str(exc))
            return
        self._refresh_workspace_list(select_id=record.id)
        self.statusBar().showMessage(f"Added local workspace: {record.display_name}")
        self._start_workspace_scan([record.id])

    def _toggle_workspace_ai_metadata(self, checked: bool) -> None:
        workspace_id = self._selected_workspace_id()
        if not workspace_id:
            return
        if checked:
            answer = QMessageBox.question(
                self,
                "Allow workspace metadata sharing?",
                "This setting allows SKYFALL's workspace MCP tools to send the selected folder's "
                "filenames, paths, extracted summaries, script parameter names, function names and "
                "import/module names to GitHub Copilot when you ask it to search or describe files.\n\n"
                "Source file contents are not returned by v0.7. Heuristic secret detection excludes "
                "likely credential-bearing files from AI search, but it is not a guarantee. Do not share "
                "folders containing sensitive material unless your company policy permits sharing their "
                "metadata. Do you explicitly approve metadata sharing for this workspace?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._sync_workspace_checkbox()
                return
        try:
            self.workspace_manager.set_ai_metadata_access(workspace_id, checked)
            self._refresh_workspace_list(select_id=workspace_id)
            self.statusBar().showMessage(
                "Workspace metadata sharing enabled" if checked else "Workspace metadata sharing disabled"
            )
        except Exception as exc:
            QMessageBox.warning(self, "Workspace setting failed", str(exc))
            self._sync_workspace_checkbox()

    def _remove_selected_workspace(self) -> None:
        workspace_id = self._selected_workspace_id()
        if not workspace_id:
            QMessageBox.information(self, "Select a workspace", "Select a configured folder first.")
            return
        record = self.workspace_manager.get_workspace(workspace_id)
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove workspace from SKYFALL?",
            f"Remove {record.display_name} from SKYFALL's index?\n\n"
            "This deletes only SKYFALL's local index records. It does not delete or modify the folder or its files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.workspace_manager.remove_workspace(workspace_id)
            self._refresh_workspace_list()
            self.statusBar().showMessage("Workspace removed from SKYFALL; source folder untouched")

    def _scan_selected_workspace(self) -> None:
        workspace_id = self._selected_workspace_id()
        if not workspace_id:
            QMessageBox.information(self, "Select a workspace", "Select a folder to scan.")
            return
        self._start_workspace_scan([workspace_id])

    def _scan_all_workspaces(self) -> None:
        self._start_workspace_scan([])

    def _start_workspace_scan(self, workspace_ids: list[str]) -> None:
        if self._workspace_scan_worker is not None and self._workspace_scan_worker.isRunning():
            QMessageBox.information(self, "Scan in progress", "A workspace scan is already running.")
            return
        for button in self.workspace_scan_buttons + self.workspace_manage_buttons:
            button.setEnabled(False)
        if self.workspace_list is not None:
            self.workspace_list.setEnabled(False)
        if self.workspace_ai_checkbox is not None:
            self.workspace_ai_checkbox.setEnabled(False)
        if self.workspace_status_label is not None:
            self.workspace_status_label.setText("Scanning approved folders locally… source files will not be sent to Copilot.")
        worker = WorkspaceScanWorker(workspace_ids, parent=self)
        worker.completed.connect(self._on_workspace_scan_completed)
        worker.failed.connect(self._on_workspace_scan_failed)
        self._workspace_scan_worker = worker
        worker.start()

    def _on_workspace_scan_completed(self, results: object) -> None:
        for button in self.workspace_scan_buttons + self.workspace_manage_buttons:
            button.setEnabled(True)
        if self.workspace_list is not None:
            self.workspace_list.setEnabled(True)
        result_list = results if isinstance(results, list) else []
        self._refresh_workspace_list(select_id=self._selected_workspace_id())
        total = sum(int(item.get("indexed_files", 0)) for item in result_list if isinstance(item, dict))
        failed = sum(1 for item in result_list if isinstance(item, dict) and item.get("scan_status") == "failed")
        message = f"Workspace scan finished · {total} files indexed"
        if failed:
            message += f" · {failed} failed"
        if self.workspace_status_label is not None:
            self.workspace_status_label.setText(message + ". Index metadata is stored locally.")
        self.statusBar().showMessage(message)
        self._workspace_scan_worker = None
        self._sync_workspace_checkbox()

    def _on_workspace_scan_failed(self, error: str) -> None:
        for button in self.workspace_scan_buttons + self.workspace_manage_buttons:
            button.setEnabled(True)
        if self.workspace_list is not None:
            self.workspace_list.setEnabled(True)
        if self.workspace_status_label is not None:
            self.workspace_status_label.setText(f"Workspace scan failed: {error}")
        self.statusBar().showMessage("Workspace scan failed")
        self._workspace_scan_worker = None
        self._sync_workspace_checkbox()

    def _search_workspace_index(self) -> None:
        query = self.workspace_search_input.text().strip() if self.workspace_search_input else ""
        if not query:
            return
        try:
            results = self.workspace_manager.search_local(query, limit=100)
        except Exception as exc:
            QMessageBox.warning(self, "Workspace search failed", str(exc))
            return
        self.workspace_results_list.clear()
        for result in results:
            summary = result.get("summary") or "No static summary available."
            item = QListWidgetItem(
                f"{result['name']}  ·  {result['language']}\n"
                f"{result['workspace_name']}\\{result['relative_path']}\n"
                f"{summary[:180]}"
            )
            item.setData(Qt.ItemDataRole.UserRole, result)
            item.setToolTip("Double-click to view extracted metadata. Source code is not displayed or sent to Copilot.")
            self.workspace_results_list.addItem(item)
        if self.workspace_status_label is not None:
            self.workspace_status_label.setText(f"Local search returned {len(results)} result(s) for: {query}")

    def _show_workspace_file_details(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, dict):
            return
        details = [
            f"File: {result.get('name')}",
            f"Workspace: {result.get('workspace_name')}",
            f"Path: {result.get('absolute_path')}",
            f"Type: {result.get('language')} ({result.get('kind')})",
            f"Size: {int(result.get('size_bytes', 0)):,} bytes",
            f"Modified (UTC): {result.get('modified_at')}",
            f"Summary: {result.get('summary')}",
            f"Parameters: {', '.join(result.get('parameters', [])) or 'None detected'}",
            f"Functions: {', '.join(result.get('functions', [])) or 'None detected'}",
            f"Classes: {', '.join(result.get('classes', [])) or 'None detected'}",
            f"Imports/modules: {', '.join(result.get('imports', [])) or 'None detected'}",
            f"Command identifiers: {', '.join(result.get('commands', [])) or 'None detected'}",
            f"Top-level keys/headings: {', '.join(result.get('top_level_keys_or_headings', [])) or 'None detected'}",
            f"Static analysis: {result.get('parse_status')}",
            "\nSource code is not displayed or transmitted by this version.",
        ]
        QMessageBox.information(self, "Workspace file metadata", "\n".join(details))

    def _build_azure_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)

        title = QLabel("Azure Account Intelligence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Discover authenticated Azure CLI profiles, tenants and subscriptions. "
            "SKYFALL uses read-only discovery only; it does not create, update or delete Azure resources."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        account_panel = QFrame()
        account_panel.setObjectName("panel")
        account_layout = QVBoxLayout(account_panel)
        account_layout.setContentsMargins(16, 14, 16, 14)
        account_layout.setSpacing(10)
        account_layout.addWidget(self._section_label("AZURE CLI PROFILE"))

        profile_row = QHBoxLayout()
        self.azure_profile_combo = QComboBox()
        self.azure_profile_combo.setMinimumHeight(36)
        self.azure_profile_combo.setStyleSheet(
            "background:#101A2D;color:#E8ECF5;border:1px solid #30425E;"
            "border-radius:8px;padding:7px;"
        )
        profile_row.addWidget(self.azure_profile_combo, 1)
        add_profile = QPushButton("＋ Add isolated account")
        add_profile.setObjectName("secondaryButton")
        add_profile.clicked.connect(self._add_azure_profile)
        profile_row.addWidget(add_profile)
        refresh = QPushButton("Refresh subscriptions")
        refresh.setObjectName("primaryButton")
        refresh.clicked.connect(self._refresh_azure_discovery)
        profile_row.addWidget(refresh)
        account_layout.addLayout(profile_row)

        self.azure_status_label = QLabel("Select a profile and refresh to inspect its authentication status.")
        self.azure_status_label.setObjectName("muted")
        self.azure_status_label.setWordWrap(True)
        account_layout.addWidget(self.azure_status_label)
        self.azure_tenant_label = QLabel("Tenants: not discovered")
        self.azure_tenant_label.setObjectName("muted")
        self.azure_tenant_label.setWordWrap(True)
        account_layout.addWidget(self.azure_tenant_label)
        layout.addWidget(account_panel)

        layout.addWidget(self._section_label("ACCESSIBLE SUBSCRIPTIONS"))
        self.azure_subscriptions_table = QTableWidget(0, 6)
        self.azure_subscriptions_table.setHorizontalHeaderLabels(
            ["Account profile", "Subscription", "Subscription ID", "Tenant ID", "State", "Default"]
        )
        self._style_data_table(self.azure_subscriptions_table)
        layout.addWidget(self.azure_subscriptions_table, 1)

        note = QLabel(
            "Account isolation: the Default Azure CLI profile reads your existing Azure CLI context. "
            "Additional SKYFALL profiles use separate AZURE_CONFIG_DIR folders. To sign in, run the "
            "displayed device-code command in PowerShell. Tenant IDs are derived from the selected "
            "profile's authenticated account and subscription cache; they are not a directory-wide guest-tenant inventory."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _build_power_platform_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)

        title = QLabel("Power Platform Account Intelligence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Inspect PAC CLI authentication profiles and discover environments through the currently active profile. "
            "SKYFALL will not switch your global PAC CLI profile automatically."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(self._section_label("AUTHENTICATION PROFILES"))
        buttons = QHBoxLayout()
        refresh_profiles = QPushButton("Refresh profiles")
        refresh_profiles.setObjectName("secondaryButton")
        refresh_profiles.clicked.connect(self._refresh_powerplatform_profiles)
        buttons.addWidget(refresh_profiles)
        connect_help = QPushButton("How to add an account")
        connect_help.setObjectName("secondaryButton")
        connect_help.clicked.connect(self._show_pac_profile_help)
        buttons.addWidget(connect_help)
        discover = QPushButton("Discover environments")
        discover.setObjectName("primaryButton")
        discover.clicked.connect(self._discover_powerplatform_environments)
        buttons.addWidget(discover)
        buttons.addStretch(1)
        panel_layout.addLayout(buttons)
        self.pp_status_label = QLabel("PAC CLI profile status has not been checked.")
        self.pp_status_label.setObjectName("muted")
        self.pp_status_label.setWordWrap(True)
        panel_layout.addWidget(self.pp_status_label)
        layout.addWidget(panel)

        layout.addWidget(self._section_label("REGISTERED PAC CLI PROFILES"))
        self.pp_profiles_table = QTableWidget(0, 6)
        self.pp_profiles_table.setHorizontalHeaderLabels(
            ["Index", "Active", "Kind", "Profile", "Environment URL", "User"]
        )
        self._style_data_table(self.pp_profiles_table)
        self.pp_profiles_table.setMaximumHeight(210)
        layout.addWidget(self.pp_profiles_table)

        layout.addWidget(self._section_label("DISCOVERED ENVIRONMENTS"))
        self.pp_environments_table = QTableWidget(0, 6)
        self.pp_environments_table.setHorizontalHeaderLabels(
            ["Environment", "Type", "Environment ID", "URL", "Organization ID", "Region"]
        )
        self._style_data_table(self.pp_environments_table)
        layout.addWidget(self.pp_environments_table, 1)

        note = QLabel(
            "Environment discovery runs `pac admin list --json` using the active PAC CLI profile. "
            "It may require Power Platform administrative permissions. Multiple PAC profiles can be "
            "listed, but switching profiles remains a user-controlled PAC CLI action in this release."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    @staticmethod
    def _style_data_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(
            "QTableWidget{background:#101A2D;alternate-background-color:#142139;"
            "color:#E8ECF5;border:1px solid #293A55;gridline-color:#293A55;"
            "selection-background-color:#24466D;}"
            "QHeaderView::section{background:#17243A;color:#AFC3DD;border:0;"
            "border-bottom:1px solid #30425E;padding:8px;font-weight:650;}"
        )

    def _refresh_azure_profile_choices(self) -> None:
        if self.azure_profile_combo is None:
            return
        current = self.azure_profile_combo.currentData()
        self.azure_profile_combo.blockSignals(True)
        self.azure_profile_combo.clear()
        try:
            self.azure_profile_combo.addItem("All connected Azure accounts", "all")
            profiles = self.azure_profile_manager.store.list_profiles()
            for profile in profiles:
                self.azure_profile_combo.addItem(profile["name"], profile["profile_id"])
        except Exception as exc:
            self.azure_profile_combo.addItem(f"Profile registry error: {exc}", "azure-cli-default")
        if current:
            index = self.azure_profile_combo.findData(current)
            if index >= 0:
                self.azure_profile_combo.setCurrentIndex(index)
        self.azure_profile_combo.blockSignals(False)

    def _add_azure_profile(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add Azure account", "Profile name:")
        if not accepted or not name.strip():
            return
        tenant, tenant_accepted = QInputDialog.getText(
            self,
            "Azure tenant (optional)",
            "Tenant ID or verified tenant domain (leave blank for default tenant):",
        )
        if not tenant_accepted:
            return
        try:
            profile = self.azure_profile_manager.store.create_profile(name, tenant or None)
        except Exception as exc:
            QMessageBox.critical(self, "Could not create Azure profile", str(exc))
            return
        command = profile["login_command"]
        QApplication.clipboard().setText(command)
        self._refresh_azure_profile_choices()
        index = self.azure_profile_combo.findData(profile["profile_id"])
        if index >= 0:
            self.azure_profile_combo.setCurrentIndex(index)
        QMessageBox.information(
            self,
            "Azure profile created",
            "A separate Azure CLI configuration folder has been created. No sign-in has been performed yet.\n\n"
            "The device-code command has been copied to your clipboard. Open a separate PowerShell terminal, "
            "paste and run it, complete Microsoft sign-in, then return to SKYFALL and refresh subscriptions.\n\n"
            "This profile is isolated from your default Azure CLI configuration. Do not share the device code with anyone.\n\n"
            + command,
        )

    def _start_microsoft_worker(self, action: str, profile_id: str = "azure-cli-default") -> None:
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            QMessageBox.information(self, "Discovery in progress", "A Microsoft account discovery task is already running.")
            return
        worker = MicrosoftDiscoveryWorker(action, profile_id, self)
        self._microsoft_worker = worker
        worker.completed.connect(self._on_microsoft_discovery_completed)
        worker.failed.connect(self._on_microsoft_discovery_failed)
        if action == "azure":
            if self.azure_status_label:
                self.azure_status_label.setText("Checking Azure CLI authentication and refreshing subscriptions...")
        elif self.pp_status_label:
            self.pp_status_label.setText("Querying PAC CLI profiles and environment context...")
        worker.start()

    def _refresh_azure_discovery(self) -> None:
        profile_id = self.azure_profile_combo.currentData() if self.azure_profile_combo else "azure-cli-default"
        self._start_microsoft_worker("azure", str(profile_id or "azure-cli-default"))

    def _refresh_powerplatform_profiles(self) -> None:
        self._start_microsoft_worker("powerplatform_profiles")

    def _discover_powerplatform_environments(self) -> None:
        self._start_microsoft_worker("powerplatform_environments")

    def _show_pac_profile_help(self) -> None:
        command = 'pac auth create --name "Skyfall Work" --deviceCode'
        QApplication.clipboard().setText(command)
        QMessageBox.information(
            self,
            "Add a Power Platform account",
            "To add another PAC CLI authentication profile, run this command in a separate PowerShell terminal:\n\n"
            + command
            + "\n\nPAC CLI may make the newly created profile active. This affects the PAC CLI installation globally. "
            "SKYFALL will not switch profiles automatically; review `pac auth list` and confirm the active profile "
            "before discovering environments. The command was copied to your clipboard.",
        )

    def _on_microsoft_discovery_completed(self, action: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if action == "azure":
            auth = data.get("auth", {})
            subscriptions = data.get("subscriptions", {})
            tenants = data.get("tenants", {})
            if self.azure_status_label:
                if auth.get("profile_id") == "all":
                    self.azure_status_label.setText(
                        f"Connected Azure profiles: {auth.get('authenticated_profile_count', 0)} / "
                        f"{auth.get('profile_count', 0)} · Subscriptions discovered: {subscriptions.get('count', 0)}"
                    )
                elif auth.get("authenticated"):
                    self.azure_status_label.setText(
                        f"Authenticated: {auth.get('user') or 'Microsoft account'} · "
                        f"Current subscription: {auth.get('subscription_name') or 'Not selected'} · "
                        f"Profile: {auth.get('profile')} · "
                        f"Subscriptions discovered: {subscriptions.get('count', 0)}"
                    )
                else:
                    self.azure_status_label.setText(
                        f"Not authenticated for this profile. {auth.get('error') or subscriptions.get('error') or ''}"
                    )
            if self.azure_tenant_label:
                tenant_ids = [
                    f"{item.get('tenant_id', '')} ({', '.join(item.get('profile_ids', []))})"
                    for item in tenants.get("tenants", [])
                ]
                self.azure_tenant_label.setText(
                    "Tenant IDs represented in connected profiles: " + (", ".join(tenant_ids) if tenant_ids else "None discovered")
                )
            if self.azure_subscriptions_table:
                rows = subscriptions.get("subscriptions", []) if subscriptions.get("success") else []
                self.azure_subscriptions_table.setRowCount(len(rows))
                for row_index, item in enumerate(rows):
                    values = [item.get("profile", ""), item.get("name", ""), item.get("subscription_id", ""), item.get("tenant_id", ""), item.get("state", ""), "Yes" if item.get("is_default") else ""]
                    for column, value in enumerate(values):
                        self.azure_subscriptions_table.setItem(row_index, column, QTableWidgetItem(str(value)))
                if not subscriptions.get("success") and self.azure_status_label:
                    self.azure_status_label.setText(
                        f"{self.azure_status_label.text()} · {subscriptions.get('error', 'Subscription discovery failed.')}"
                    )
        elif action.startswith("powerplatform"):
            profiles = data.get("profiles", {})
            auth = data.get("auth", {})
            if self.pp_status_label:
                active = auth.get("active_profile") or {}
                if auth.get("authenticated"):
                    self.pp_status_label.setText(
                        f"Active PAC profile: #{active.get('index')} · {active.get('label') or active.get('environment_url') or 'Unnamed'} · "
                        f"User: {active.get('user') or 'Not parsed'} · Registered profiles: {auth.get('profile_count', 0)}"
                    )
                else:
                    self.pp_status_label.setText(
                        f"No active PAC profile detected. {profiles.get('error') or 'Sign in using PAC CLI, then refresh.'}"
                    )
            if self.pp_profiles_table:
                rows = profiles.get("profiles", [])
                self.pp_profiles_table.setRowCount(len(rows))
                for row_index, item in enumerate(rows):
                    values = [item.get("index", ""), "Yes" if item.get("active") else "", item.get("kind", ""), item.get("label", ""), item.get("environment_url", ""), item.get("user", "")]
                    for column, value in enumerate(values):
                        self.pp_profiles_table.setItem(row_index, column, QTableWidgetItem(str(value)))
            if action == "powerplatform_environments" and self.pp_environments_table:
                env_result = data.get("environments", {})
                rows = env_result.get("environments", []) if env_result.get("success") else []
                self.pp_environments_table.setRowCount(len(rows))
                for row_index, item in enumerate(rows):
                    values = [item.get("name", ""), item.get("type", ""), item.get("environment_id", ""), item.get("environment_url", ""), item.get("organization_id", ""), item.get("region", "")]
                    for column, value in enumerate(values):
                        self.pp_environments_table.setItem(row_index, column, QTableWidgetItem(str(value)))
                if not env_result.get("success") and self.pp_status_label:
                    self.pp_status_label.setText(
                        f"{self.pp_status_label.text()} · {env_result.get('error', 'Environment discovery failed.')}")

    def _on_microsoft_discovery_failed(self, action: str, error: str) -> None:
        if action == "azure" and self.azure_status_label:
            self.azure_status_label.setText(f"Azure discovery failed: {error}")
        elif self.pp_status_label:
            self.pp_status_label.setText(f"Power Platform discovery failed: {error}")

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
            "This release enables read-only MCP Core and metadata-only workspace discovery. "
            "Azure and Power Platform account/environment discovery are available in read-only mode. "
            "Resource modification and script execution remain disabled in v0.7."
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
        panel_layout.addWidget(self._status_row("Version", "0.7.0", "good"))
        panel_layout.addWidget(self._status_row("Runtime", "Local desktop", "good"))
        panel_layout.addWidget(self._status_row("AI provider", "GitHub Copilot", "good"))
        panel_layout.addWidget(self._status_row("MCP integration", "Starting...", "pending"))
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
        self._set_status_value("MCP Tools", "7 read-only tools", "good")
        self._set_status_value("MCP integration", "Core + workspace metadata", "good")
        self.top_state.setText("●  COPILOT + MCP CONNECTED")
        self.top_state.setObjectName("statusGood")
        self.top_state.style().unpolish(self.top_state)
        self.top_state.style().polish(self.top_state)
        self.chat_subtitle.setText(
            "Connected to GitHub Copilot and the local SKYFALL MCP server. Seven read-only tools are enabled: "
            "core status/capability discovery and metadata-only workspace search for explicitly approved folders. "
            "Source code, cloud operations and script execution are not enabled."
        )
        self.chat_input.setEnabled(True)
        self.chat_send_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.history_list.setEnabled(True)
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self.statusBar().showMessage("SKYFALL AI connected · MCP Core + Workspace enabled · 7 read-only tools available")

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
            self._active_reply_label.set_markdown("")
        self._active_reply_text += chunk
        self._active_reply_label.set_markdown(self._active_reply_text)
        self._scroll_chat_to_bottom()

    def _on_response_finished(self) -> None:
        final_text = self._active_reply_text.strip()
        if self._active_reply_label is not None and not final_text:
            final_text = "Copilot completed the turn without text."
            self._active_reply_label.set_markdown(final_text)
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
            self._active_reply_label.set_markdown(text)
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
        scan_worker = getattr(self, "_workspace_scan_worker", None)
        if scan_worker is not None and scan_worker.isRunning():
            if not scan_worker.wait(5000):
                QMessageBox.information(
                    self,
                    "Workspace scan is still running",
                    "SKYFALL is finishing a read-only workspace scan. Please close the application again after the scan completes.",
                )
                event.ignore()
                return
        microsoft_worker = getattr(self, "_microsoft_worker", None)
        if microsoft_worker is not None and microsoft_worker.isRunning():
            if not microsoft_worker.wait(5000):
                QMessageBox.information(
                    self,
                    "Microsoft discovery is still running",
                    "SKYFALL is waiting for a read-only Azure or Power Platform discovery request. "
                    "Please close the application again after it finishes.",
                )
                event.ignore()
                return
        worker = getattr(self, "copilot_worker", None)
        if worker is not None:
            worker.shutdown()
        super().closeEvent(event)

    def _add_message(self, sender: str, text: str, assistant: bool) -> MarkdownMessageLabel | None:
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
        message_label = MarkdownMessageLabel()
        message_label.setObjectName("messageText")
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message_label.set_markdown(text)
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
