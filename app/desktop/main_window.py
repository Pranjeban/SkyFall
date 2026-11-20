"""SKYFALL desktop UI with Copilot chat and local conversation history."""

from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QTextDocument, QDesktopServices, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
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
    QMenu,
    QPlainTextEdit,
    QProgressBar,
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
from skyfall_cloud.powerplatform_resources import PowerPlatformFlowInventory
from skyfall_cloud.powerplatform_accounts import PowerPlatformAccountStore
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
    body { color: #E8E1EC; font-family: 'Segoe UI'; font-size: 13px; }
    p { margin: 0 0 7px 0; }
    h1, h2, h3, h4 { color: #F4EFF8; margin: 8px 0 5px 0; }
    a { color: #C69AFF; }
    code { color: #D8C5E8; background-color: #302A37; font-family: Consolas; }
    pre { color: #E8E1EC; background-color: #29242F; padding: 8px; font-family: Consolas; }
    blockquote { color: #B7AFC0; background-color: #29242F; }
    table { border-collapse: collapse; }
    th, td { border: 1px solid #554A60; padding: 4px 7px; }
    th { color: #E8E1EC; background-color: #302A37; }
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


class SmoothScrollArea(QScrollArea):
    """Small eased wheel movement for the Kiro-style quiet scroll surfaces."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wheel_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._wheel_animation.setDuration(180)
        self._wheel_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.verticalScrollBar().setSingleStep(28)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        bar = self.verticalScrollBar()
        delta = event.pixelDelta().y()
        if not delta:
            delta = int(event.angleDelta().y() / 120 * 54)
        if not delta:
            super().wheelEvent(event)
            return
        self._wheel_animation.stop()
        self._wheel_animation.setStartValue(bar.value())
        self._wheel_animation.setEndValue(max(bar.minimum(), min(bar.maximum(), bar.value() - delta)))
        self._wheel_animation.start()
        event.accept()



class FloatingAssistant(QDialog):
    """Compact entry point that sends messages to the current main conversation."""

    message_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("SKYFALL Assistant")
        self.setMinimumWidth(390)
        self.setMaximumWidth(470)
        self.setStyleSheet("background:#141119; color:#F0EFF2; border:1px solid rgba(255,255,255,0.07); border-radius:18px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("SKYFALL")
        title.setStyleSheet("font-size:17px;font-weight:600;letter-spacing:2px;color:#F0EFF2;")
        subtitle = QLabel("PERSONAL ENGINEERING INTELLIGENCE")
        subtitle.setStyleSheet("font-size:9px;color:#8A8A95;letter-spacing:1px;")
        brand_col = QVBoxLayout()
        brand_col.addWidget(title)
        brand_col.addWidget(subtitle)
        header.addLayout(brand_col)
        header.addStretch(1)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setStyleSheet(
            "background:#19161F;color:#C8C5CD;border:1px solid rgba(255,255,255,0.07);border-radius:8px;font-size:18px;"
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
            "color:#B1B1BA;font-size:12px;padding:10px;background:#18151E;"
            "border:1px solid rgba(255,255,255,0.06);border-radius:10px;"
        )
        layout.addWidget(info)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Skyfall...")
        self.input.setStyleSheet(
            "background:#15121A;color:#E7E5EA;border:1px solid rgba(255,255,255,0.075);border-radius:10px;"
            "padding:11px;"
        )
        self.input.returnPressed.connect(self._submit)
        send = QPushButton("Send")
        send.setStyleSheet(
            "background:#745394;color:#F7F4FA;border:1px solid rgba(193,160,229,0.24);border-radius:10px;"
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


class ProfileManagerDialog(QDialog):
    """Small profile-management dialog used by Azure and Power Platform pages."""

    def __init__(self, title: str, entries: list[tuple[str, str]], primary_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.action = "close"
        self.selected_value = ""
        self.setStyleSheet("QDialog{background:#1B1821;color:#F0ECF4;}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        hint = QLabel("Select an existing profile or create a new one. Sign-in starts only after you explicitly request it.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#A69EAD;font-size:12px;")
        layout.addWidget(hint)

        self.items = QListWidget()
        self.items.setStyleSheet(
            "QListWidget{background:#25212B;color:#F0ECF4;border:1px solid #594769;border-radius:8px;padding:6px;}"
            "QListWidget::item{padding:9px;border-radius:5px;}"
            "QListWidget::item:selected{background:#503665;color:#E4CAFF;}"
        )
        for label, value in entries:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.items.addItem(item)
        if self.items.count():
            self.items.setCurrentRow(0)
        layout.addWidget(self.items, 1)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("＋ Add profile")
        self.add_button.setObjectName("secondaryButton")
        self.add_button.clicked.connect(self._add)
        buttons.addWidget(self.add_button)
        self.primary_button = QPushButton(primary_label)
        self.primary_button.setObjectName("primaryButton")
        self.primary_button.clicked.connect(self._primary)
        buttons.addWidget(self.primary_button)
        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _add(self) -> None:
        self.action = "add"
        self.accept()

    def _primary(self) -> None:
        item = self.items.currentItem()
        if item is None:
            QMessageBox.information(self, "Select a profile", "Select a profile first.")
            return
        self.selected_value = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self.action = "primary"
        self.accept()


class AzureProfileCreateDialog(QDialog):
    """Collect the profile name and tenant before starting browser sign-in."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Azure profile")
        self.setMinimumWidth(540)
        self.setStyleSheet("QDialog{background:#1B1821;color:#F0ECF4;}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        heading = QLabel("Connect a Microsoft Azure account")
        heading.setStyleSheet("font-size:17px;font-weight:700;color:#F4EFF8;")
        layout.addWidget(heading)

        info = QLabel(
            "Give this account a local SKYFALL profile name and enter its tenant ID or verified tenant domain. "
            "After you create the profile, SKYFALL opens Microsoft sign-in in your browser and automatically "
            "discovers the signed-in tenant and accessible subscriptions."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#A69EAD;font-size:12px;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("For example: Company QA")
        self.tenant_edit = QLineEdit()
        self.tenant_edit.setPlaceholderText("Tenant GUID or contoso.onmicrosoft.com")
        for field in (self.name_edit, self.tenant_edit):
            field.setMinimumHeight(36)
            field.setStyleSheet(
                "background:#211D27;color:#F0ECF4;border:1px solid #594769;"
                "border-radius:8px;padding:7px 10px;"
            )
        form.addRow("Profile name", self.name_edit)
        form.addRow("Tenant ID / domain", self.tenant_edit)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#F09BA7;font-size:11px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create & sign in")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        tenant = self.tenant_edit.text().strip()
        if not name:
            self.error_label.setText("Enter a profile name.")
            self.name_edit.setFocus()
            return
        if not tenant:
            self.error_label.setText("Enter the tenant ID or verified tenant domain.")
            self.tenant_edit.setFocus()
            return
        if len(name) > 80:
            self.error_label.setText("Profile name must be 80 characters or fewer.")
            return
        self.accept()

    @property
    def profile_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def tenant_id(self) -> str:
        return self.tenant_edit.text().strip()


class PowerPlatformProfileCreateDialog(QDialog):
    """Collect a named Power Platform profile before the Azure browser sign-in."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Power Platform profile")
        self.setMinimumWidth(540)
        self.setStyleSheet("QDialog{background:#1B1821;color:#F0ECF4;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        heading = QLabel("Connect a Power Platform account")
        heading.setStyleSheet("font-size:17px;font-weight:700;color:#F4EFF8;")
        layout.addWidget(heading)
        info = QLabel(
            "SKYFALL opens the same Microsoft browser sign-in used for Azure, saves this account as a local profile, "
            "then lists the environments that account can access."
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("For example: Company QA")
        self.tenant_edit = QLineEdit()
        self.tenant_edit.setPlaceholderText("Tenant GUID or contoso.onmicrosoft.com (optional)")
        for field in (self.name_edit, self.tenant_edit):
            field.setMinimumHeight(36)
            field.setStyleSheet(
                "background:#211D27;color:#F0ECF4;border:1px solid #594769;"
                "border-radius:8px;padding:7px 10px;"
            )
        form.addRow("Profile name", self.name_edit)
        form.addRow("Tenant (optional)", self.tenant_edit)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#F09BA7;font-size:11px;")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue to Microsoft sign-in")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        tenant = self.tenant_edit.text().strip()
        if not name or len(name) > 80:
            self.error_label.setText("Enter a profile name between 1 and 80 characters.")
            self.name_edit.setFocus()
            return
        if len(tenant) > 200 or any(char in tenant for char in "\r\n/\\"):
            self.error_label.setText("Enter a tenant ID or domain, or leave it blank for work and school accounts.")
            self.tenant_edit.setFocus()
            return
        self.accept()

    @property
    def profile_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def tenant(self) -> str:
        return self.tenant_edit.text().strip()


class MainWindow(QMainWindow):
    NAV_ITEMS = [
        ("Overview", "overview"),
        ("Chat", "chat"),
        ("Capabilities", "capabilities"),
        ("Workspaces", "workspaces"),
        ("Azure", "azure"),
        ("Azure Resources", "azure_resources"),
        ("Power Platform", "power_platform"),
        ("Flow Inventory", "power_platform_resources"),
        ("Orchestration", "executions"),
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
        self._pending_auth_refresh_targets: set[str] = set()
        self._auth_refresh_queue: list[str] = []
        self._auth_refresh_target_in_flight: str | None = None
        self._auth_refresh_attempts = 0

        self.nav_buttons: dict[str, QPushButton] = {}
        self.page_titles: dict[str, str] = {key: label for label, key in self.NAV_ITEMS}
        self.chat_layout: QVBoxLayout | None = None
        self.chat_scroll: QScrollArea | None = None
        self.history_list: QListWidget | None = None
        self.history_search_input: QLineEdit | None = None
        self.new_chat_button: QPushButton | None = None
        self.delete_chat_button: QPushButton | None = None
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
        self.powerplatform_account_store = PowerPlatformAccountStore()
        self._microsoft_worker: MicrosoftDiscoveryWorker | None = None
        self.azure_profile_combo: QComboBox | None = None
        self.azure_status_label: QLabel | None = None
        self.azure_tenant_label: QLabel | None = None
        self.azure_subscriptions_table: QTableWidget | None = None
        self.azure_inventory_status_label: QLabel | None = None
        self.azure_inventory_table: QTableWidget | None = None
        self.azure_inventory_button: QPushButton | None = None
        self.azure_inventory_report_label: QLabel | None = None
        self.azure_inventory_open_button: QPushButton | None = None
        self.azure_inventory_report_path: str | None = None
        self.azure_lookup_input: QLineEdit | None = None
        self.azure_lookup_button: QPushButton | None = None
        self.azure_lookup_result_label: QLabel | None = None
        self.pp_status_label: QLabel | None = None
        self.pp_profile_combo: QComboBox | None = None
        self.pp_refresh_environments_button: QPushButton | None = None
        self.pp_profiles_table: QTableWidget | None = None
        self.pp_environments_table: QTableWidget | None = None
        self.pp_resource_environment_combo: QComboBox | None = None
        self.pp_flow_status_label: QLabel | None = None
        self.pp_flow_inventory_button: QPushButton | None = None
        self.pp_flow_open_button: QPushButton | None = None
        self.pp_flow_table: QTableWidget | None = None
        self.pp_flow_report_path: str | None = None
        self.exec_search_input: QLineEdit | None = None
        self.exec_candidates: QComboBox | None = None
        self.exec_candidate_detail: QLabel | None = None
        self.exec_identity_label: QLabel | None = None
        self.exec_environment_label: QLabel | None = None
        self.exec_progress: QProgressBar | None = None
        self.exec_progress_label: QLabel | None = None
        self.exec_stage_labels: list[QLabel] = []
        self.exec_run_button: QPushButton | None = None
        self._exec_candidate_rows: list[dict] = []
        self._execution_orchestration_active = False
        self._execution_plan_prepared = False

        self.floating = FloatingAssistant(self)
        self.floating.message_submitted.connect(self._handle_floating_message)

        root = QWidget()
        root.setObjectName("appRoot")
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(9, 8, 9, 8)
        root_layout.setSpacing(0)

        app_surface = QFrame()
        app_surface.setObjectName("appSurface")
        app_surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        surface_layout = QHBoxLayout(app_surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        surface_layout.addWidget(self.sidebar)

        content_host = QWidget()
        content_host.setObjectName("contentHost")
        content_layout = QVBoxLayout(content_host)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.top_bar = self._build_top_bar()
        content_layout.addWidget(self.top_bar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        self.pages: dict[str, QWidget] = {}
        self.pages["overview"] = self._build_overview()
        self.pages["chat"] = self._build_chat_page()
        self.pages["capabilities"] = self._build_capabilities_page()
        self.pages["workspaces"] = self._build_workspaces_page()
        self.pages["azure"] = self._build_azure_page()
        self.pages["azure_resources"] = self._build_azure_resources_page()
        self.pages["power_platform"] = self._build_power_platform_page()
        self.pages["power_platform_resources"] = self._build_power_platform_resources_page()
        self.pages["executions"] = self._build_execution_page()
        self.pages["reports"] = self._build_placeholder_page(
            "Reports library",
            "Reports generated by SKYFALL will be organized here once reporting tools are connected.",
            ["Azure inventories", "Power Platform inventories", "Custom report templates"],
        )
        self.pages["settings"] = self._build_settings_page()

        for page in self.pages.values():
            self.stack.addWidget(page)

        content_layout.addWidget(self.stack, 1)
        surface_layout.addWidget(content_host, 1)
        root_layout.addWidget(app_surface, 1)
        self.setCentralWidget(root)

        self._select_page("overview")
        self._install_shortcuts()
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self._render_conversation(self.current_conversation.id)
        self._refresh_workspace_list()
        self._refresh_azure_profile_choices()

        self.statusBar().showMessage("SKYFALL desktop ready · Starting Copilot AI runtime...")

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
        # Refresh the current account context on startup. Unauthenticated
        # profiles are shown as a normal signed-out state, not a raw CLI error.
        QTimer.singleShot(350, self._refresh_azure_discovery)
        QTimer.singleShot(500, self._refresh_powerplatform_profiles)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(13, 16, 13, 12)
        layout.setSpacing(7)

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

        navigation_scroll = SmoothScrollArea()
        navigation_scroll.setObjectName("sidebarNavigationScroll")
        navigation_scroll.setWidgetResizable(True)
        navigation_scroll.setFrameShape(QFrame.Shape.NoFrame)
        navigation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navigation_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        navigation_content = QWidget()
        navigation_content.setObjectName("sidebarNavigationContent")
        navigation_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        navigation_layout = QVBoxLayout(navigation_content)
        navigation_layout.setContentsMargins(2, 8, 3, 8)
        navigation_layout.setSpacing(4)

        section = QLabel("YOUR SESSION")
        section.setObjectName("eyebrow")
        navigation_layout.addWidget(section)

        workflow_keys = {"azure", "azure_resources", "power_platform", "power_platform_resources", "executions", "reports"}
        workflow_heading_added = False
        for label, key in self.NAV_ITEMS:
            if key in workflow_keys and not workflow_heading_added:
                navigation_layout.addSpacing(9)
                workflow_heading = QLabel("CLOUD WORKFLOWS")
                workflow_heading.setObjectName("eyebrow")
                navigation_layout.addWidget(workflow_heading)
                workflow_heading_added = True
            button = QPushButton(f"   {label}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setMinimumHeight(36)
            button.clicked.connect(lambda checked=False, page=key: self._select_page(page))
            self.nav_buttons[key] = button
            navigation_layout.addWidget(button)
        navigation_layout.addStretch(1)
        navigation_scroll.setWidget(navigation_content)
        layout.addWidget(navigation_scroll, 1)

        floating_button = QPushButton("＋  Open floating assistant")
        floating_button.setObjectName("secondaryButton")
        floating_button.setMinimumHeight(36)
        floating_button.clicked.connect(self._show_floating)
        layout.addWidget(floating_button)

        account = QFrame()
        account.setObjectName("accountPanel")
        account_layout = QVBoxLayout(account)
        account_layout.setContentsMargins(10, 9, 10, 9)
        account_layout.setSpacing(5)
        account_title = QLabel("LOCAL SESSION")
        account_title.setObjectName("eyebrow")
        account_layout.addWidget(account_title)
        account_layout.addWidget(self._status_row("Copilot CLI", "Signed in", "good"))
        account_layout.addWidget(self._status_row("AI runtime", "Connecting...", "pending"))
        account_layout.addWidget(self._status_row("MCP tools", "Starting...", "pending"))
        layout.addWidget(account)
        return sidebar

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(58)
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
        greeting.setStyleSheet("font-size:25px;font-weight:750;color:#F4EFF8;")
        sub = QLabel(
            "Your personal engineering assistant is online. Plan engineering work, review account context, "
            "and track supervised read-only operations from the Orchestration workspace."
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
            "workspace search. Azure subscription discovery and Power Platform OAuth profile/environment "
            "discovery are available in read-only mode. The v1.0 Execution Center prepares plans and runs "
            "the reviewed native Flow Inventory route; general workspace script execution remains gated."
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
        history_panel.setFixedWidth(270)
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(12, 14, 12, 12)
        history_layout.setSpacing(10)

        history_header = QLabel("SESSIONS")
        history_header.setObjectName("eyebrow")
        history_layout.addWidget(history_header)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.new_chat_button = QPushButton("+  New")
        self.new_chat_button.setObjectName("primaryButton")
        self.new_chat_button.clicked.connect(self._create_new_conversation)
        actions.addWidget(self.new_chat_button, 1)
        self.delete_chat_button = QPushButton("Delete")
        self.delete_chat_button.setObjectName("secondaryButton")
        self.delete_chat_button.setFixedWidth(72)
        self.delete_chat_button.setToolTip("Conversation actions")
        menu = QMenu(self.delete_chat_button)
        menu.addAction("Delete selected conversation", self._delete_selected_conversation)
        self.delete_chat_button.setMenu(menu)
        actions.addWidget(self.delete_chat_button)
        history_layout.addLayout(actions)

        self.history_search_input = QLineEdit()
        self.history_search_input.setObjectName("sessionSearch")
        self.history_search_input.setPlaceholderText("Search sessions...")
        self.history_search_input.setClearButtonEnabled(True)
        self.history_search_input.textChanged.connect(self._filter_conversation_list)
        history_layout.addWidget(self.history_search_input)

        self.history_list = QListWidget()
        self.history_list.setObjectName("conversationList")
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.currentItemChanged.connect(self._on_history_selection_changed)
        history_layout.addWidget(self.history_list, 1)

        history_note = QLabel("Older sessions · stored locally")
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
        title = QLabel(self.current_conversation.title or "New conversation")
        title.setObjectName("chatPageTitle")
        self.chat_page_title = title
        subtitle = QLabel(
            "Your conversation is private to this local SKYFALL session."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        self.chat_subtitle = subtitle
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        conversation_layout.addLayout(header)

        self.chat_scroll = SmoothScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setObjectName("chatScroll")
        messages_host = QWidget()
        messages_host.setObjectName("chatMessageCanvas")
        self.chat_layout = QVBoxLayout(messages_host)
        self.chat_layout.setContentsMargins(4, 8, 4, 8)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch(1)
        self.chat_scroll.setWidget(messages_host)
        conversation_layout.addWidget(self.chat_scroll, 1)

        composer = QFrame()
        composer.setObjectName("chatComposer")
        input_row = QHBoxLayout(composer)
        input_row.setContentsMargins(12, 8, 8, 8)
        input_row.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setFrame(False)
        self.chat_input.setPlaceholderText("Ask SKYFALL to explain, plan or help with an engineering problem...")
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.chat_send_button = QPushButton("?")
        self.chat_send_button.setObjectName("primaryButton")
        self.chat_send_button.setFixedSize(38, 38)
        self.chat_send_button.clicked.connect(self._send_chat_message)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.chat_send_button)
        conversation_layout.addWidget(composer)

        body.addWidget(conversation_panel, 1)
        layout.addLayout(body, 1)
        return page

    def _build_capabilities_page(self) -> QWidget:
        """Show readable capability cards in a scrollable two-column layout."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)

        title = QLabel("Capabilities")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        intro = QLabel(
            "Explore what SKYFALL can currently do. Each capability shows its purpose, "
            "availability and permission level. Planned features are not shown as active tools."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        summary = QFrame()
        summary.setObjectName("panel")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(8)
        summary_layout.addWidget(self._status_row("Tool connection", "SKYFALL Local Intelligence · connected through Copilot", "good"))
        summary_layout.addWidget(self._status_row("Execution policy", "Read-only discovery and local report generation", "good"))
        summary_layout.addWidget(self._status_row("Azure", "Account discovery and Function App inventory", "good"))
        summary_layout.addWidget(self._status_row("Power Platform", "Account discovery and cloud-flow inventory", "good"))
        summary_layout.addWidget(self._status_row("Workspace discovery", "Local metadata · sharing is opt-in", "good"))
        layout.addWidget(summary)

        try:
            capabilities = CapabilityRegistry.default().list(enabled_only=True)
        except Exception as exc:
            error = QLabel(f"The capability catalogue could not be loaded: {exc}")
            error.setObjectName("muted")
            error.setWordWrap(True)
            layout.addWidget(error)
            capabilities = []

        heading = QLabel(f"AVAILABLE CAPABILITIES · {len(capabilities)}")
        heading.setObjectName("eyebrow")
        layout.addWidget(heading)

        grid_host = QWidget()
        grid_host.setObjectName("capabilityGrid")
        grid_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        risk_labels = {
            "read_only": "READ ONLY",
            "interactive_authentication": "SIGN-IN ACTION",
            "write": "MODIFIES DATA",
            "destructive": "DESTRUCTIVE",
        }
        category_labels = {
            "core": "CORE",
            "workspace": "WORKSPACE",
            "azure": "AZURE",
            "azure_resources": "AZURE RESOURCES",
            "power_platform": "POWER PLATFORM",
            "power_platform_resources": "POWER PLATFORM RESOURCES",
            "authentication": "AUTHENTICATION",
            "identity": "IDENTITY",
            "orchestration": "ORCHESTRATION",
            "cross_platform": "CROSS-PLATFORM",
            "monitoring": "MONITORING",
            "reporting": "REPORTING",
            "governance": "GOVERNANCE",
            "copilot": "COPILOT",
            "operations": "OPERATIONS",
            "execution": "EXECUTION",
        }
        for index, capability in enumerate(capabilities):
            card = QFrame()
            card.setObjectName("capabilityCard")
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            card.setMinimumSize(340, 168)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setToolTip(f"{capability.name}\nInternal capability: {capability.id}\nMCP tool: {capability.tool_name}")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(9)

            header = QHBoxLayout()
            name = QLabel(capability.name)
            name.setObjectName("capabilityTitle")
            name.setWordWrap(True)
            category = QLabel(category_labels.get(capability.category, capability.category.replace("_", " ").upper()))
            category.setObjectName("capabilityCategory")
            category.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.addWidget(name, 1)
            header.addWidget(category, 0, Qt.AlignmentFlag.AlignTop)
            card_layout.addLayout(header)

            description = QLabel(capability.description)
            description.setObjectName("capabilityDescription")
            description.setWordWrap(True)
            description.setMinimumHeight(44)
            card_layout.addWidget(description, 1)

            footer = QHBoxLayout()
            risk = QLabel(risk_labels.get(capability.risk, capability.risk.replace("_", " ").upper()))
            risk.setObjectName("capabilityRisk")
            availability = QLabel("AVAILABLE")
            availability.setObjectName("statusGood")
            footer.addWidget(risk)
            footer.addStretch(1)
            footer.addWidget(availability)
            card_layout.addLayout(footer)

            grid.addWidget(card, index // 2, index % 2)

        layout.addWidget(grid_host)
        note = QLabel(
            "Capabilities are registered and permission-scoped. Workspace tools expose only metadata "
            "from folders you approved. Inventory tools read cloud metadata and create local reports; "
            "they do not modify resources or execute your scripts."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

        scroll.setWidget(content)
        page_layout.addWidget(scroll)
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
            "explicitly enable metadata sharing for that folder. This release shares only filenames, paths and "
            "extracted structural metadata—not source code. Known credential-file patterns and files "
            "flagged by heuristic secret detection are excluded from AI search. Detection is not a guarantee; "
            "do not add folders containing sensitive data unless policy permits sharing their metadata."
        )
        privacy_note.setWordWrap(True)
        privacy_note.setStyleSheet("color:#A69EAD;font-size:12px;")
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
                "Source file contents are not returned by SKYFALL. Heuristic secret detection excludes "
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
            "background:#211D27;color:#F0ECF4;border:1px solid #594769;"
            "border-radius:8px;padding:7px 10px;"
        )
        self.azure_profile_combo.currentIndexChanged.connect(self._on_azure_profile_changed)
        profile_row.addWidget(self.azure_profile_combo, 1)
        manage_profiles = QPushButton("Manage profiles")
        manage_profiles.setObjectName("primaryButton")
        manage_profiles.clicked.connect(self._manage_azure_profiles)
        profile_row.addWidget(manage_profiles)
        account_layout.addLayout(profile_row)

        self.azure_status_label = QLabel("SKYFALL will discover your current Azure login automatically.")
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
            "To connect a new Azure account, open Manage profiles → Add profile, enter a profile name and tenant ID or verified tenant domain, then select Create & sign in. "
            "SKYFALL opens Microsoft's browser sign-in and automatically discovers the canonical tenant ID and accessible subscriptions after login. "
            "Each named profile has an isolated AZURE_CONFIG_DIR; your default Azure CLI context is not changed."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _build_azure_resources_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)

        title = QLabel("Azure Resource Intelligence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        intro = QLabel(
            "Discover Azure Function Apps across the subscriptions visible to your selected Azure profile. "
            "This is read-only against Azure; SKYFALL never retrieves app settings, connection strings, "
            "publishing profiles, host keys or function keys."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        lookup_panel = QFrame()
        lookup_panel.setObjectName("panel")
        lookup_layout = QVBoxLayout(lookup_panel)
        lookup_layout.setContentsMargins(18, 16, 18, 16)
        lookup_layout.setSpacing(10)
        lookup_layout.addWidget(self._section_label("FIND A FUNCTION APP BY NAME"))

        lookup_hint = QLabel(
            "Ask in chat, for example: \"which subscription is fn-qa-orders in?\" "
            "You can also use this search for the same plain-text answer without generating an Excel report."
        )
        lookup_hint.setObjectName("muted")
        lookup_hint.setWordWrap(True)
        lookup_layout.addWidget(lookup_hint)

        lookup_row = QHBoxLayout()
        self.azure_lookup_input = QLineEdit()
        self.azure_lookup_input.setPlaceholderText("Function App name, e.g. fn-qa-orders")
        self.azure_lookup_input.returnPressed.connect(self._start_function_app_lookup)
        lookup_row.addWidget(self.azure_lookup_input, 1)
        self.azure_lookup_button = QPushButton("Find by name")
        self.azure_lookup_button.setObjectName("secondaryButton")
        self.azure_lookup_button.clicked.connect(self._start_function_app_lookup)
        lookup_row.addWidget(self.azure_lookup_button)
        lookup_layout.addLayout(lookup_row)

        self.azure_lookup_result_label = QLabel(
            "No lookup run yet. Exact name matching is case-insensitive."
        )
        self.azure_lookup_result_label.setObjectName("muted")
        self.azure_lookup_result_label.setWordWrap(True)
        lookup_layout.addWidget(self.azure_lookup_result_label)
        layout.addWidget(lookup_panel)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(self._section_label("FUNCTION APP INVENTORY"))

        self.azure_inventory_status_label = QLabel(
            "Ready. The inventory scope follows the Azure profile selected on the Azure page."
        )
        self.azure_inventory_status_label.setObjectName("muted")
        self.azure_inventory_status_label.setWordWrap(True)
        panel_layout.addWidget(self.azure_inventory_status_label)

        actions = QHBoxLayout()
        self.azure_inventory_button = QPushButton("Generate Function App Excel inventory")
        self.azure_inventory_button.setObjectName("primaryButton")
        self.azure_inventory_button.clicked.connect(self._start_function_app_inventory)
        actions.addWidget(self.azure_inventory_button)
        self.azure_inventory_open_button = QPushButton("Open latest report")
        self.azure_inventory_open_button.setObjectName("secondaryButton")
        self.azure_inventory_open_button.setEnabled(False)
        self.azure_inventory_open_button.clicked.connect(self._open_function_app_report)
        actions.addWidget(self.azure_inventory_open_button)
        actions.addStretch(1)
        panel_layout.addLayout(actions)

        self.azure_inventory_report_label = QLabel("No Function App report generated in this session.")
        self.azure_inventory_report_label.setObjectName("muted")
        self.azure_inventory_report_label.setWordWrap(True)
        panel_layout.addWidget(self.azure_inventory_report_label)
        layout.addWidget(panel)

        layout.addWidget(self._section_label("DISCOVERED FUNCTION APPS · PREVIEW"))
        self.azure_inventory_table = QTableWidget(0, 8)
        self.azure_inventory_table.setHorizontalHeaderLabels(
            ["Profile", "Subscription", "Resource Group", "Function App", "Runtime", "Plan SKU", "Region", "State"]
        )
        self._style_data_table(self.azure_inventory_table)
        layout.addWidget(self.azure_inventory_table, 1)

        note = QLabel(
            "The detailed XLSX report is saved under SKYFALL\\reports\\Azure. "
            "The preview shows up to 10 apps; use Find by name or ask in chat for a specific app's "
            "subscription and details as text. Azure Resource Graph indexing can lag recent changes; "
            "SKYFALL reports partial discovery errors instead of silently claiming complete coverage."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _start_function_app_inventory(self) -> None:
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            QMessageBox.information(
                self,
                "Microsoft task in progress",
                "Another Microsoft account or inventory task is running. Try again when it finishes.",
            )
            return
        profile_id = str(
            self.azure_profile_combo.currentData()
            if self.azure_profile_combo is not None and self.azure_profile_combo.currentData()
            else "all"
        )
        if self.azure_inventory_button:
            self.azure_inventory_button.setEnabled(False)
        if self.azure_inventory_status_label:
            self.azure_inventory_status_label.setText(
                "Querying Azure Resource Graph across enabled subscriptions visible to the selected profile(s)..."
            )
        self._start_microsoft_worker("azure_function_apps", profile_id)

    def _start_function_app_lookup(self) -> None:
        name = str(self.azure_lookup_input.text().strip()) if self.azure_lookup_input else ""
        if not name:
            QMessageBox.information(
                self,
                "Function App name required",
                "Enter the Function App name you want to locate, then select Find by name.",
            )
            return
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            QMessageBox.information(
                self,
                "Microsoft task in progress",
                "Another Microsoft account or inventory task is running. Try again when it finishes.",
            )
            return
        profile_id = str(
            self.azure_profile_combo.currentData()
            if self.azure_profile_combo is not None and self.azure_profile_combo.currentData()
            else "all"
        )
        if self.azure_lookup_button:
            self.azure_lookup_button.setEnabled(False)
        if self.azure_lookup_input:
            self.azure_lookup_input.setEnabled(False)
        if self.azure_lookup_result_label:
            self.azure_lookup_result_label.setText(
                f"Searching Azure Resource Graph for Function App '{name}'..."
            )
        self._start_microsoft_worker(
            "azure_function_app_lookup",
            profile_id,
            {"name": name, "exact": True},
        )

    def _open_function_app_report(self) -> None:
        path = self.azure_inventory_report_path
        if not path or not Path(path).is_file():
            QMessageBox.information(self, "Report unavailable", "The latest Function App report could not be found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _build_power_platform_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)

        title = QLabel("Power Platform Account Intelligence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Sign in through the same Microsoft browser flow as Azure, then discover environments available to your account. "
            "Each profile uses an isolated SKYFALL credential folder and leaves your regular Azure CLI account untouched."
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
        self.pp_profile_combo = QComboBox()
        self.pp_profile_combo.setMinimumHeight(36)
        self.pp_profile_combo.setStyleSheet(
            "background:#211D27;color:#F0ECF4;border:1px solid #594769;"
            "border-radius:8px;padding:7px 10px;"
        )
        self.pp_profile_combo.currentIndexChanged.connect(self._on_powerplatform_profile_changed)
        buttons.addWidget(self.pp_profile_combo, 1)
        add_account = QPushButton("Add profile")
        add_account.setObjectName("primaryButton")
        add_account.clicked.connect(self._manage_powerplatform_profiles)
        buttons.addWidget(add_account)
        self.pp_refresh_environments_button = QPushButton("Refresh environments")
        self.pp_refresh_environments_button.setObjectName("secondaryButton")
        self.pp_refresh_environments_button.clicked.connect(
            lambda: self._start_microsoft_worker("powerplatform_environments")
        )
        buttons.addWidget(self.pp_refresh_environments_button)
        remove_account = QPushButton("Remove account")
        remove_account.setObjectName("dangerButton")
        remove_account.clicked.connect(self._remove_powerplatform_profile)
        buttons.addWidget(remove_account)
        buttons.addStretch(1)
        panel_layout.addLayout(buttons)
        self.pp_status_label = QLabel(
            "Add a profile to sign in through Microsoft. SKYFALL will discover accessible environments automatically."
        )
        self.pp_status_label.setObjectName("muted")
        self.pp_status_label.setWordWrap(True)
        panel_layout.addWidget(self.pp_status_label)
        layout.addWidget(panel)

        layout.addWidget(self._section_label("SAVED MICROSOFT ACCOUNTS"))
        self.pp_profiles_table = QTableWidget(0, 6)
        self.pp_profiles_table.setHorizontalHeaderLabels(
            ["Authentication", "Selected", "Tenant ID", "Profile", "Last Environment ID", "User"]
        )
        self._style_data_table(self.pp_profiles_table)
        self.pp_profiles_table.setMaximumHeight(210)
        layout.addWidget(self.pp_profiles_table)

        layout.addWidget(self._section_label("DISCOVERED ENVIRONMENTS"))
        self.pp_environments_table = QTableWidget(0, 7)
        self.pp_environments_table.setHorizontalHeaderLabels(
            ["Environment", "Type", "Environment ID", "URL", "Organization ID", "Region", "Tenant ID"]
        )
        self._style_data_table(self.pp_environments_table)
        layout.addWidget(self.pp_environments_table, 1)

        note = QLabel(
            "Add profile opens the same Microsoft browser sign-in used by Azure. SKYFALL keeps its Azure CLI token cache in an isolated profile, lists accessible Power Platform environments automatically, and does not need PAC CLI or a manually entered client ID. "
            "Environment discovery runs after sign-in and when you refresh. The flow selector includes environments with a Dataverse URL. "
            "Flow inventory uses Dataverse metadata columns only; definitions, connections and secrets are excluded."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _build_power_platform_resources_page(self) -> QWidget:
        """Build a calmer, metric-led flow inventory workspace with a useful empty state."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel("Power Automate")
        title.setObjectName("pageTitle")
        title_column.addWidget(title)
        intro = QLabel(
            "Inventory cloud flows in a selected environment, preview key metadata and create a polished Excel workbook. "
            "SKYFALL uses your selected Microsoft account and the read-only Dataverse Web API."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        title_column.addWidget(intro)
        header.addLayout(title_column, 1)
        read_only_badge = QLabel("READ-ONLY INVENTORY")
        read_only_badge.setObjectName("readOnlyBadge")
        read_only_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(read_only_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        # Summary cards keep the page informative without a large empty table.
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)
        self.pp_flow_metric_values = {}
        metric_specs = [
            ("ENVIRONMENT", "Not selected", "Choose an accessible environment", "environment"),
            ("CLOUD FLOWS", "—", "Flows visible to the selected account", "flows"),
            ("ENABLED", "—", "Currently enabled flows", "enabled"),
            ("REPORT", "Not generated", "A dated Excel workbook", "report"),
        ]
        for label_text, value_text, detail_text, key in metric_specs:
            card = QFrame()
            card.setObjectName("metricCard")
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            card.setMinimumHeight(112)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 13, 15, 13)
            card_layout.setSpacing(6)
            label = QLabel(label_text)
            label.setObjectName("metricLabel")
            value = QLabel(value_text)
            value.setObjectName("metricValue")
            value.setWordWrap(True)
            value.setStyleSheet("font-size:18px;font-weight:750;color:#F4EFF8;")
            detail = QLabel(detail_text)
            detail.setObjectName("muted")
            detail.setWordWrap(True)
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            card_layout.addWidget(detail, 1)
            self.pp_flow_metric_values[key] = value
            metrics_row.addWidget(card, 1)
        layout.addLayout(metrics_row)

        scope_panel = QFrame()
        scope_panel.setObjectName("panel")
        scope_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        scope_layout = QVBoxLayout(scope_panel)
        scope_layout.setContentsMargins(18, 16, 18, 16)
        scope_layout.setSpacing(11)
        scope_header = QHBoxLayout()
        scope_header.addWidget(self._section_label("INVENTORY SCOPE"))
        scope_header.addStretch(1)
        scope_caption = QLabel("Select one environment")
        scope_caption.setObjectName("muted")
        scope_header.addWidget(scope_caption)
        scope_layout.addLayout(scope_header)

        selection_row = QHBoxLayout()
        self.pp_resource_environment_combo = QComboBox()
        self.pp_resource_environment_combo.setMinimumHeight(42)
        self.pp_resource_environment_combo.setPlaceholderText("Select a discovered environment")
        self.pp_resource_environment_combo.setStyleSheet(
            "background:#211D27;color:#F0ECF4;border:1px solid #594769;"
            "border-radius:9px;padding:8px 11px;font-size:13px;"
        )
        self.pp_resource_environment_combo.currentIndexChanged.connect(self._on_powerplatform_environment_changed)
        selection_row.addWidget(self.pp_resource_environment_combo, 1)
        self.pp_flow_inventory_button = QPushButton("Generate Excel workbook")
        self.pp_flow_inventory_button.setObjectName("primaryButton")
        self.pp_flow_inventory_button.setMinimumHeight(42)
        self.pp_flow_inventory_button.clicked.connect(self._start_powerplatform_flow_inventory)
        selection_row.addWidget(self.pp_flow_inventory_button)
        self.pp_flow_open_button = QPushButton("Open latest report")
        self.pp_flow_open_button.setObjectName("secondaryButton")
        self.pp_flow_open_button.setMinimumHeight(42)
        self.pp_flow_open_button.setEnabled(False)
        self.pp_flow_open_button.clicked.connect(self._open_powerplatform_flow_report)
        selection_row.addWidget(self.pp_flow_open_button)
        scope_layout.addLayout(selection_row)

        self.pp_flow_status_label = QLabel(
            "Ready when an environment is available. SKYFALL discovers environments after Power Platform sign-in."
        )
        self.pp_flow_status_label.setObjectName("operationStatus")
        self.pp_flow_status_label.setWordWrap(True)
        scope_layout.addWidget(self.pp_flow_status_label)

        self.pp_flow_retry_environment_button = QPushButton("Retry environment discovery")
        self.pp_flow_retry_environment_button.setObjectName("secondaryButton")
        self.pp_flow_retry_environment_button.setVisible(False)
        self.pp_flow_retry_environment_button.clicked.connect(
            lambda: self._start_microsoft_worker("powerplatform_environments")
        )
        scope_layout.addWidget(self.pp_flow_retry_environment_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(scope_panel)

        preview_panel = QFrame()
        preview_panel.setObjectName("panel")
        preview_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(18, 16, 18, 16)
        preview_layout.setSpacing(12)
        preview_header = QHBoxLayout()
        preview_header.addWidget(self._section_label("FLOW PREVIEW"))
        preview_header.addStretch(1)
        self.pp_flow_preview_count = QLabel("No inventory yet")
        self.pp_flow_preview_count.setObjectName("muted")
        preview_header.addWidget(self.pp_flow_preview_count)
        preview_layout.addLayout(preview_header)

        self.pp_flow_empty_state = QFrame()
        self.pp_flow_empty_state.setObjectName("emptyStateCard")
        self.pp_flow_empty_state.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        empty_layout = QVBoxLayout(self.pp_flow_empty_state)
        empty_layout.setContentsMargins(22, 24, 22, 24)
        empty_layout.setSpacing(7)
        self.pp_flow_empty_title = QLabel("Your flow inventory will appear here")
        self.pp_flow_empty_title.setObjectName("emptyStateTitle")
        self.pp_flow_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pp_flow_empty_message = QLabel(
            "Connect a Power Platform profile, select an environment and generate an Excel workbook."
        )
        self.pp_flow_empty_message.setObjectName("muted")
        self.pp_flow_empty_message.setWordWrap(True)
        self.pp_flow_empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.pp_flow_empty_title)
        empty_layout.addWidget(self.pp_flow_empty_message)
        preview_layout.addWidget(self.pp_flow_empty_state)

        self.pp_flow_table = QTableWidget(0, 5)
        self.pp_flow_table.setHorizontalHeaderLabels(
            ["Flow name", "Status", "Type", "Owner", "Last modified"]
        )
        self._style_data_table(self.pp_flow_table)
        self.pp_flow_table.setMinimumHeight(260)
        self.pp_flow_table.setMaximumHeight(440)
        self.pp_flow_table.hide()
        preview_layout.addWidget(self.pp_flow_table)
        layout.addWidget(preview_panel)

        note = QLabel(
            "Coverage is limited to cloud flows visible to the selected Microsoft account in the selected environment. "
            "Flow definitions, action payloads, connection details and secrets are never exported. "
            "The documented Dataverse code path covers solution cloud flows; My Flows is not currently supported. "
            "The signed-in account must have permission to read flows in the selected Dataverse environment."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

        self.pp_flow_report_path = None
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return page

    def _start_powerplatform_flow_inventory(self) -> None:
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            QMessageBox.information(
                self, "Microsoft task in progress",
                "Another Microsoft account or inventory task is running. Try again when it finishes.",
            )
            return
        selected = self.pp_resource_environment_combo.currentData() if self.pp_resource_environment_combo else None
        if not isinstance(selected, dict) or not selected.get("environment_id"):
            QMessageBox.information(
                self, "Select an environment",
                "Refresh Power Platform environments and select the environment you want to inventory.",
            )
            return
        if self.pp_flow_inventory_button:
            self.pp_flow_inventory_button.setEnabled(False)
        if self.pp_flow_status_label:
            self.pp_flow_status_label.setText(
                f"Collecting flow metadata from {selected.get('name') or 'the selected environment'} using the selected Microsoft account..."
            )
        if self.pp_flow_empty_state:
            self.pp_flow_empty_title.setText("Inventory in progress")
            self.pp_flow_empty_message.setText("SKYFALL is retrieving flow metadata and preparing your Excel workbook.")
            self.pp_flow_empty_state.show()
        if self.pp_flow_table:
            self.pp_flow_table.hide()
            self.pp_flow_table.setRowCount(0)
        if self.pp_flow_preview_count:
            self.pp_flow_preview_count.setText("Collecting results...")
        if getattr(self, "pp_flow_metric_values", None):
            self.pp_flow_metric_values["environment"].setText(str(selected.get("name") or "Selected"))
            self.pp_flow_metric_values["report"].setText("Preparing...")
        self._start_microsoft_worker(
            "powerplatform_flow_inventory",
            params={
                "environment_id": str(selected["environment_id"]),
                "environment_name": str(selected.get("name") or "Selected Environment"),
                "environment_url": str(selected.get("environment_url") or ""),
                "profile_id": str(self.pp_profile_combo.currentData() or "") if self.pp_profile_combo else "",
            },
        )

    def _open_powerplatform_flow_report(self) -> None:
        path = self.pp_flow_report_path
        if not path or not Path(path).is_file():
            QMessageBox.information(self, "Report unavailable", "The latest Power Automate flow report could not be found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @staticmethod
    def _style_data_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(
            "QTableWidget{background:#211D27;alternate-background-color:#28242E;"
            "color:#E8E1EC;border:1px solid #443B4D;gridline-color:#3B3442;"
            "selection-background-color:#503665;}"
            "QHeaderView::section{background:#29242F;color:#C8B8D7;border:0;"
            "border-bottom:1px solid #443B4D;padding:8px;font-weight:650;}"
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
                suffix = " · home tenant auto-detected" if profile.get("kind") == "skyfall_isolated_profile" and not profile.get("tenant_hint") else ""
                self.azure_profile_combo.addItem(profile["name"] + suffix, profile["profile_id"])
        except Exception as exc:
            self.azure_profile_combo.addItem(f"Profile registry error: {exc}", "all")
        if current:
            index = self.azure_profile_combo.findData(current)
            if index >= 0:
                self.azure_profile_combo.setCurrentIndex(index)
        self.azure_profile_combo.blockSignals(False)

    def _on_azure_profile_changed(self, _index: int) -> None:
        if self.azure_profile_combo is None:
            return
        profile_id = str(self.azure_profile_combo.currentData() or "all")
        self._start_microsoft_worker("azure", profile_id)

    def _manage_azure_profiles(self) -> None:
        try:
            profiles = self.azure_profile_manager.store.list_profiles()
        except Exception as exc:
            QMessageBox.critical(self, "Azure profile registry error", str(exc))
            return
        entries = []
        for profile in profiles:
            tenant = profile.get("tenant_hint") or "tenant not configured"
            kind = "Default CLI context" if profile["profile_id"] == "azure-cli-default" else "Isolated profile"
            entries.append((f"{profile['name']}  ·  {kind}  ·  {tenant}", profile["profile_id"]))
        dialog = ProfileManagerDialog("Manage Azure profiles", entries, "Sign in selected", self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.action == "add":
            self._create_azure_profile()
        elif dialog.action == "primary":
            self._sign_in_azure_profile(dialog.selected_value)

    def _create_azure_profile(self) -> None:
        dialog = AzureProfileCreateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            profile = self.azure_profile_manager.store.create_profile(
                dialog.profile_name, dialog.tenant_id
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create Azure profile", str(exc))
            return
        self._refresh_azure_profile_choices()
        if self.azure_profile_combo is not None:
            index = self.azure_profile_combo.findData(profile["profile_id"])
            if index >= 0:
                self.azure_profile_combo.blockSignals(True)
                self.azure_profile_combo.setCurrentIndex(index)
                self.azure_profile_combo.blockSignals(False)
        # Profile creation is immediately followed by the requested browser
        # sign-in. Tenant/subscription discovery runs automatically on success.
        self._start_microsoft_worker("azure_login", profile["profile_id"])

    def _sign_in_azure_profile(self, profile_id: str) -> None:
        if not profile_id or profile_id == "azure-cli-default":
            QMessageBox.information(
                self,
                "Use a named SKYFALL profile",
                "The Default Azure CLI profile is read-only so SKYFALL does not alter your existing Azure CLI context. Add a named profile to sign in with a separate tenant.",
            )
            return
        try:
            self.azure_profile_manager.store.get_profile(profile_id)
            self._start_microsoft_worker("azure_login", profile_id)
        except Exception as exc:
            QMessageBox.critical(self, "Could not start Azure sign-in", str(exc))

    def _start_microsoft_worker(
        self,
        action: str,
        profile_id: str = "azure-cli-default",
        params: dict | None = None,
    ) -> None:
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            if action in {"azure", "powerplatform_profiles"}:
                return
            QMessageBox.information(self, "Microsoft task in progress", "Another Microsoft account task is already running. Try again when it finishes.")
            return
        worker = MicrosoftDiscoveryWorker(action, profile_id, params=params, parent=self)
        self._microsoft_worker = worker
        worker.completed.connect(self._on_microsoft_discovery_completed)
        worker.failed.connect(self._on_microsoft_discovery_failed)
        if action == "azure":
            if self.azure_status_label:
                self.azure_status_label.setText("Checking the selected Azure profile and discovering subscriptions...")
        elif action == "azure_login":
            if self.azure_status_label:
                self.azure_status_label.setText("Opening Microsoft sign-in for this isolated Azure profile. Complete sign-in in the browser; SKYFALL will discover tenants and subscriptions automatically.")
        elif action == "powerplatform_login":
            if self.pp_status_label:
                self.pp_status_label.setText("Opening Microsoft sign-in for this SKYFALL account. Environments will refresh automatically after sign-in.")
        elif action == "powerplatform_azure_login":
            if self.pp_status_label:
                self.pp_status_label.setText("Opening the Azure browser sign-in for this Power Platform profile. Accessible environments will load after sign-in.")
        elif action == "powerplatform_select":
            if self.pp_status_label:
                self.pp_status_label.setText("Switching the selected SKYFALL account and refreshing its environments...")
        elif action == "powerplatform_environments":
            if self.pp_refresh_environments_button:
                self.pp_refresh_environments_button.setEnabled(False)
            if self.pp_status_label:
                self.pp_status_label.setText("Refreshing environments for the selected Microsoft account...")
        elif action == "powerplatform_flow_inventory":
            if self.pp_flow_status_label:
                self.pp_flow_status_label.setText("Retrieving cloud-flow metadata and preparing the Excel report...")
        elif action == "azure_function_app_lookup":
            if self.azure_lookup_result_label:
                lookup_name = str((params or {}).get("name", ""))
                self.azure_lookup_result_label.setText(
                    f"Looking up Function App '{lookup_name}' by name..."
                )
        elif self.pp_status_label:
            self.pp_status_label.setText("Refreshing saved Microsoft accounts and environment context...")
        worker.start()

    def _refresh_azure_discovery(self) -> None:
        profile_id = self.azure_profile_combo.currentData() if self.azure_profile_combo else "all"
        self._start_microsoft_worker("azure", str(profile_id or "all"))

    def _refresh_powerplatform_profiles(self) -> None:
        self._start_microsoft_worker("powerplatform_profiles")

    def _remove_powerplatform_profile(self) -> None:
        profile_id = str(self.pp_profile_combo.currentData() or "") if self.pp_profile_combo else ""
        profile = self.powerplatform_account_store.get_profile(profile_id) if profile_id else None
        if not profile:
            QMessageBox.information(self, "No account selected", "Select a saved Microsoft account to remove.")
            return
        answer = QMessageBox.question(
            self,
            "Remove Microsoft account?",
            f"Remove {profile.get('name') or 'this account'} from SKYFALL and delete its isolated sign-in profile and local token cache?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        azure_profile_id = str(profile.get("azure_profile_id") or "")
        if azure_profile_id:
            try:
                self.azure_profile_manager.store.delete_profile(azure_profile_id)
            except KeyError:
                pass
        self.powerplatform_account_store.remove_profile(profile_id)
        self._refresh_powerplatform_profiles()

    def _manage_powerplatform_profiles(self) -> None:
        dialog = PowerPlatformProfileCreateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_microsoft_worker(
            "powerplatform_azure_login",
            params={"profile_name": dialog.profile_name, "tenant": dialog.tenant},
        )

    def _on_powerplatform_profile_changed(self, _index: int) -> None:
        if self.pp_profile_combo is None:
            return
        profile_id = str(self.pp_profile_combo.currentData() or "")
        if not profile_id or profile_id == self.powerplatform_account_store.get_active_profile_id():
            return
        self._start_microsoft_worker("powerplatform_select", params={"profile_id": profile_id})

    def _on_powerplatform_environment_changed(self, _index: int) -> None:
        if self.pp_resource_environment_combo is None:
            return
        selected = self.pp_resource_environment_combo.currentData()
        profile_id = self.powerplatform_account_store.get_active_profile_id()
        if profile_id and isinstance(selected, dict) and selected.get("environment_id"):
            self.powerplatform_account_store.set_selected_environment(
                profile_id, str(selected["environment_id"])
            )
        if getattr(self, "exec_environment_label", None):
            profile, environment = self._refresh_execution_context()
            if self.exec_run_button:
                self.exec_run_button.setEnabled(bool(self._execution_plan_prepared and profile and environment))

    def _on_microsoft_discovery_completed(self, action: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if action in {"azure", "azure_login"}:
            self._refresh_azure_profile_choices()
            auth = data.get("auth", {})
            if auth.get("authenticated"):
                self._pending_auth_refresh_targets.discard("azure")
                if not self._pending_auth_refresh_targets:
                    self._auth_refresh_queue.clear()
                    self._auth_refresh_attempts = 0
            subscriptions = data.get("subscriptions", {})
            tenants = data.get("tenants", {})
            if self.azure_status_label:
                if auth.get("profile_id") == "all":
                    connected_count = auth.get("authenticated_profile_count", 0)
                    if connected_count:
                        self.azure_status_label.setText(
                            f"Connected Azure profiles: {connected_count} / {auth.get('profile_count', 0)} · "
                            f"Subscriptions discovered: {subscriptions.get('count', 0)}"
                        )
                    else:
                        self.azure_status_label.setText(
                            "No Azure account is connected yet. Open Manage profiles, add a profile, enter its tenant ID/domain, and SKYFALL will open Microsoft sign-in."
                        )
                elif auth.get("authenticated"):
                    self.azure_status_label.setText(
                        f"Authenticated: {auth.get('user') or 'Microsoft account'} · "
                        f"Current subscription: {auth.get('subscription_name') or 'Not selected'} · "
                        f"Profile: {auth.get('profile')} · "
                        f"Subscriptions discovered: {subscriptions.get('count', 0)}"
                    )
                else:
                    try:
                        selected_profile = self.azure_profile_manager.store.get_profile(str(data.get("profile_id") or self.azure_profile_combo.currentData()))
                    except Exception:
                        selected_profile = {}
                    if selected_profile.get("profile_id") == "azure-cli-default":
                        status_text = (
                            "Default Azure CLI is not signed in. To add another account without changing your existing CLI context, "
                            "open Manage profiles and create a named SKYFALL profile."
                        )
                    else:
                        status_text = (
                            f"Not signed in to {selected_profile.get('name', 'this profile')}. "
                            "Open Manage profiles → Sign in selected to launch Microsoft sign-in and detect its home tenant."
                        )
                    self.azure_status_label.setText(status_text)
            if self.azure_tenant_label:
                tenant_ids = [
                    f"{item.get('tenant_id', '')} ({', '.join(item.get('profile_ids', []))})" if item.get("profile_ids") else str(item.get("tenant_id", ""))
                    for item in tenants.get("tenants", [])
                ]
                if auth.get("profile_id") == "all":
                    label = "Tenant IDs represented in connected profiles: "
                else:
                    label = "Tenant IDs for selected profile: "
                self.azure_tenant_label.setText(label + (", ".join(tenant_ids) if tenant_ids else "None discovered yet"))
            if self.azure_subscriptions_table:
                rows = subscriptions.get("subscriptions", []) if subscriptions.get("success") else []
                self.azure_subscriptions_table.setRowCount(len(rows))
                for row_index, item in enumerate(rows):
                    values = [item.get("profile") or item.get("profile_id") or "", item.get("name", ""), item.get("subscription_id", ""), item.get("tenant_id", ""), item.get("state", ""), "Yes" if item.get("is_default") else ""]
                    for column, value in enumerate(values):
                        self.azure_subscriptions_table.setItem(row_index, column, QTableWidgetItem(str(value)))
                # A signed-out profile is a normal first-run state. Do not append
                # Azure CLI's low-level "Please run az login" message to the UI.
                # Surface subscription errors only for profiles that are already
                # authenticated, where the error represents a real discovery issue.
                if auth.get("authenticated") and self.azure_status_label:
                    if not subscriptions.get("success"):
                        detail = subscriptions.get("error") or "Subscription discovery failed."
                        self.azure_status_label.setText(f"{self.azure_status_label.text()} · {detail}")
                    elif auth.get("profile_id") == "all" and subscriptions.get("partial_success"):
                        authenticated_ids = {
                            str(item.get("profile_id"))
                            for item in auth.get("profiles", [])
                            if item.get("authenticated")
                        }
                        relevant_errors = [
                            str(item.get("error", ""))
                            for item in subscriptions.get("failed_profiles", [])
                            if str(item.get("profile_id", "")) in authenticated_ids and item.get("error")
                        ]
                        if relevant_errors:
                            self.azure_status_label.setText(
                                f"{self.azure_status_label.text()} · Some authenticated profiles need attention: "
                                + "; ".join(relevant_errors[:2])
                            )
        elif action == "azure_function_apps":
            if self.azure_inventory_button:
                self.azure_inventory_button.setEnabled(True)
            if data.get("success"):
                report = data.get("report") or {}
                report_path = report.get("path")
                self.azure_inventory_report_path = str(report_path) if report_path else None
                if self.azure_inventory_report_label:
                    self.azure_inventory_report_label.setText(
                        f"Excel report ready: {Path(self.azure_inventory_report_path).name} · SKYFALL / Reports / Azure"
                        if self.azure_inventory_report_path
                        else "Inventory completed without an Excel report."
                    )
                if self.azure_inventory_open_button:
                    self.azure_inventory_open_button.setEnabled(bool(self.azure_inventory_report_path))
                if self.azure_inventory_status_label:
                    prefix = "Inventory completed" if data.get("status") == "success" else "Inventory completed with partial results"
                    self.azure_inventory_status_label.setText(
                        f"{prefix}: {data.get('function_app_count', 0)} Function Apps across "
                        f"{data.get('subscription_count', 0)} subscriptions and "
                        f"{data.get('profile_count', 0)} authenticated profiles. "
                        f"Hosting plans: {data.get('hosting_plan_count', 0)}. "
                        f"Discovery errors: {len(data.get('errors') or [])}."
                    )
                rows = data.get("preview") or []
                if self.azure_inventory_table:
                    self.azure_inventory_table.setRowCount(min(len(rows), 100))
                    for row_index, item in enumerate(rows[:100]):
                        values = [
                            item.get("profiles", ""),
                            item.get("subscription", ""),
                            item.get("resource_group", ""),
                            item.get("name", ""),
                            item.get("runtime", ""),
                            item.get("hosting_plan_sku", ""),
                            item.get("region", ""),
                            item.get("state", ""),
                        ]
                        for column, value in enumerate(values):
                            self.azure_inventory_table.setItem(row_index, column, QTableWidgetItem(str(value)))
            else:
                if self.azure_inventory_status_label:
                    self.azure_inventory_status_label.setText(
                        f"Function App inventory failed: {data.get('error', 'Unknown Azure inventory error.')}"
                    )

        elif action == "azure_function_app_lookup":
            if self.azure_lookup_button:
                self.azure_lookup_button.setEnabled(True)
            if self.azure_lookup_input:
                self.azure_lookup_input.setEnabled(True)
            if self.azure_lookup_result_label:
                self.azure_lookup_result_label.setText(
                    str(data.get("summary") or "Function App lookup completed without a summary.")
                )

        elif action == "powerplatform_flow_inventory":
            if self.pp_flow_inventory_button:
                self.pp_flow_inventory_button.setEnabled(True)
            if data.get("success"):
                report = data.get("report") or {}
                self.pp_flow_report_path = str(report.get("path") or "") or None
                flow_count = int(data.get("flow_count", 0) or 0)
                enabled_count = int(data.get("enabled_count", 0) or 0)
                environment_name = data.get("environment", {}).get("name") or "Selected environment"
                if self.pp_flow_open_button:
                    self.pp_flow_open_button.setEnabled(bool(self.pp_flow_report_path))
                if self.pp_flow_status_label:
                    self.pp_flow_status_label.setText(
                        f"Inventory complete for {environment_name}. {flow_count:,} cloud flows discovered; "
                        f"{enabled_count:,} enabled and {int(data.get('disabled_or_suspended_count', 0) or 0):,} disabled or suspended. "
                        f"Workbook: {report.get('file_name') or 'not generated'}."
                    )
                metrics = getattr(self, "pp_flow_metric_values", {})
                if "environment" in metrics:
                    metrics["environment"].setText(environment_name)
                if "flows" in metrics:
                    metrics["flows"].setText(f"{flow_count:,}")
                if "enabled" in metrics:
                    metrics["enabled"].setText(f"{enabled_count:,}")
                if "report" in metrics:
                    metrics["report"].setText("Ready" if self.pp_flow_report_path else "Not generated")
                rows = data.get("preview") or []
                if self.pp_flow_preview_count:
                    self.pp_flow_preview_count.setText(f"Showing {len(rows)} of {flow_count:,} flows")
                if self.pp_flow_empty_state:
                    self.pp_flow_empty_state.hide()
                if self.pp_flow_table:
                    self.pp_flow_table.setRowCount(min(len(rows), 100))
                    for row_index, item in enumerate(rows[:100]):
                        values = [item.get("name", ""), item.get("status", ""), item.get("type", ""), item.get("owner", ""), item.get("modified_on", "")]
                        for column, value in enumerate(values):
                            self.pp_flow_table.setItem(row_index, column, QTableWidgetItem(str(value)))
                    self.pp_flow_table.setVisible(bool(rows))
                if not rows and self.pp_flow_empty_state:
                    self.pp_flow_empty_title.setText("No cloud flows were returned")
                    self.pp_flow_empty_message.setText(
                        "The inventory completed, but the selected Microsoft account returned no visible cloud flows for this environment."
                    )
                    self.pp_flow_empty_state.show()
            else:
                error = data.get("error") or "Unknown Power Platform inventory error."
                if self.pp_flow_status_label:
                    self.pp_flow_status_label.setText(f"Inventory could not be completed: {error}")
                if self.pp_flow_preview_count:
                    self.pp_flow_preview_count.setText("No results")
                if self.pp_flow_empty_state:
                    self.pp_flow_empty_title.setText("Inventory needs attention")
                    self.pp_flow_empty_message.setText(str(error))
                    self.pp_flow_empty_state.show()
                if self.pp_flow_table:
                    self.pp_flow_table.hide()
                metrics = getattr(self, "pp_flow_metric_values", {})
                if "report" in metrics:
                    metrics["report"].setText("Not generated")

            if self._execution_orchestration_active:
                self._execution_orchestration_active = False
                profile, environment = self._refresh_execution_context()
                if self.exec_run_button:
                    self.exec_run_button.setEnabled(bool(self._execution_plan_prepared and profile and environment))
                if self.exec_progress:
                    self.exec_progress.setRange(0, 100)
                    self.exec_progress.setValue(100 if data.get("success") else 60)
                if data.get("success"):
                    report_path = str((data.get("report") or {}).get("path") or "")
                    if report_path and Path(report_path).is_file():
                        for index in range(6, 10):
                            self._set_execution_stage(index, "complete")
                        if self.exec_progress_label:
                            self.exec_progress_label.setText("Complete · Report validated and ready")
                        if self.exec_candidate_detail:
                            self.exec_candidate_detail.setText(f"Excel report ready: {report_path}")
                    else:
                        self._set_execution_stage(6, "complete")
                        self._set_execution_stage(7, "attention")
                        if self.exec_progress:
                            self.exec_progress.setValue(80)
                        if self.exec_progress_label:
                            self.exec_progress_label.setText("Inventory returned, but the report file could not be validated")
                else:
                    self._set_execution_stage(6, "attention")
                    if self.exec_progress_label:
                        self.exec_progress_label.setText(
                            f"Run needs attention · {data.get('error') or 'See Flow Inventory details'}"
                        )

        elif action.startswith("powerplatform"):
            if action == "powerplatform_environments" and self.pp_refresh_environments_button:
                self.pp_refresh_environments_button.setEnabled(True)
            profiles = data.get("profiles", {})
            auth = data.get("auth", {})
            active = auth.get("active_profile") or {}
            if auth.get("authenticated"):
                self._pending_auth_refresh_targets.discard("powerplatform")
                if not self._pending_auth_refresh_targets:
                    self._auth_refresh_queue.clear()
                    self._auth_refresh_attempts = 0
            if self.pp_status_label:
                if active and auth.get("authenticated"):
                    self.pp_status_label.setText(
                        f"Selected account: {active.get('name') or 'Microsoft account'} ? "
                        f"{active.get('username') or 'identity unavailable'} ? "
                        f"{auth.get('profile_count', 0)} saved profile(s)"
                    )
                elif active:
                    self.pp_status_label.setText("This profile is signed out. Add a profile to open Microsoft sign-in again.")
                else:
                    self.pp_status_label.setText("No account selected. Add a profile to sign in and discover environments.")
            if self.pp_profile_combo:
                rows_for_combo = profiles.get("profiles", [])
                active_id = active.get("profile_id")
                self.pp_profile_combo.blockSignals(True)
                self.pp_profile_combo.clear()
                for profile in rows_for_combo:
                    label = profile.get("name") or "Microsoft account"
                    user = profile.get("username") or "unknown account"
                    self.pp_profile_combo.addItem(f"{label} ? {user}", profile.get("profile_id"))
                if active_id:
                    index = self.pp_profile_combo.findData(active_id)
                    if index >= 0:
                        self.pp_profile_combo.setCurrentIndex(index)
                self.pp_profile_combo.blockSignals(False)
                self._pp_active_profile_id = active_id
            if self.pp_profiles_table:
                rows = profiles.get("profiles", [])
                self.pp_profiles_table.setRowCount(len(rows))
                for row_index, item in enumerate(rows):
                    values = [
                        "Azure CLI / browser" if item.get("azure_profile_id") else "OAuth / MSAL",
                        "Yes" if item.get("active") else "", item.get("tenant_id", ""),
                        item.get("name", ""), item.get("selected_environment_id", ""), item.get("username", ""),
                    ]
                    for column, value in enumerate(values):
                        self.pp_profiles_table.setItem(row_index, column, QTableWidgetItem(str(value)))
            if action in {"powerplatform_environments", "powerplatform_profiles", "powerplatform_login", "powerplatform_azure_login", "powerplatform_select"} and self.pp_environments_table:
                env_result = data.get("environments", {})
                rows = env_result.get("environments", []) if env_result.get("success") else []
                self.pp_environments_table.setRowCount(len(rows))
                for row_index, item in enumerate(rows):
                    values = [item.get("name", ""), item.get("type", ""), item.get("environment_id", ""), item.get("environment_url", ""), item.get("organization_id", ""), item.get("region", ""), item.get("tenant_id", "")]
                    for column, value in enumerate(values):
                        self.pp_environments_table.setItem(row_index, column, QTableWidgetItem(str(value)))
                if self.pp_resource_environment_combo is not None:
                    previous = self.pp_resource_environment_combo.currentData()
                    previous_id = (
                        previous.get("environment_id")
                        if isinstance(previous, dict)
                        and getattr(self, "_pp_environment_profile_id", None) == active.get("profile_id")
                        else active.get("selected_environment_id")
                    )
                    self.pp_resource_environment_combo.blockSignals(True)
                    self.pp_resource_environment_combo.clear()
                    for item in rows:
                        environment_id = str(item.get("environment_id") or "").strip()
                        environment_url = str(item.get("environment_url") or "").rstrip("/")
                        if not environment_id or not environment_url:
                            continue
                        environment_name = str(item.get("name") or environment_id)
                        environment_type = str(item.get("type") or "Environment")
                        self.pp_resource_environment_combo.addItem(
                            f"{environment_name} ? {environment_type}",
                            {
                                "environment_id": environment_id,
                                "name": environment_name,
                                "environment_url": environment_url,
                            },
                        )
                    self.pp_resource_environment_combo.setCurrentIndex(-1)
                    if previous_id:
                        for combo_index in range(self.pp_resource_environment_combo.count()):
                            data_item = self.pp_resource_environment_combo.itemData(combo_index)
                            if isinstance(data_item, dict) and data_item.get("environment_id") == previous_id:
                                self.pp_resource_environment_combo.setCurrentIndex(combo_index)
                                break
                    self.pp_resource_environment_combo.blockSignals(False)
                    self._pp_environment_profile_id = active.get("profile_id")
                if env_result.get("success"):
                    summary = f"Environments discovered: {len(rows)} through the Power Platform API"
                    flow_environment_count = sum(1 for item in rows if item.get("environment_url"))
                    if self.pp_status_label:
                        self.pp_status_label.setText(f"{self.pp_status_label.text()} ? {summary}")
                    if self.pp_flow_metric_values.get("environment"):
                        self.pp_flow_metric_values["environment"].setText(f"{flow_environment_count} Dataverse-ready")
                    if self.pp_flow_status_label and flow_environment_count:
                        self.pp_flow_status_label.setText("Environments are ready. Your last selection is restored automatically.")
                    elif self.pp_flow_status_label and rows:
                        self.pp_flow_status_label.setText(
                            f"Found {len(rows)} accessible environments, but none has a Dataverse URL for flow inventory."
                        )
                    elif not rows and self.pp_flow_empty_state:
                        self.pp_flow_empty_title.setText("No environments were returned")
                        self.pp_flow_empty_message.setText("This account did not return any environments. Check the account and its Power Platform access.")
                        self.pp_flow_empty_state.show()
                    if self.pp_flow_retry_environment_button:
                        self.pp_flow_retry_environment_button.setVisible(False)
                else:
                    friendly_error = env_result.get("error", "Environment discovery could not be completed.")
                    if self.pp_status_label:
                        self.pp_status_label.setText(f"{self.pp_status_label.text()} ? {friendly_error}")
                    guidance = friendly_error if auth.get("authenticated") else "Add a profile and sign in through Microsoft to discover environments."
                    if self.pp_flow_status_label:
                        self.pp_flow_status_label.setText(guidance)
                    if self.pp_flow_empty_state:
                        self.pp_flow_empty_title.setText("Power Platform connection needs attention")
                        self.pp_flow_empty_message.setText(guidance)
                        self.pp_flow_empty_state.show()
                    if self.pp_flow_retry_environment_button:
                        self.pp_flow_retry_environment_button.setVisible(bool(auth.get("authenticated")))

        expected_action = {
            "azure": {"azure", "azure_login"},
            "powerplatform": {"powerplatform_profiles", "powerplatform_login", "powerplatform_select", "powerplatform_environments"},
        }.get(self._auth_refresh_target_in_flight or "", set())
        if action in expected_action:
            self._auth_refresh_target_in_flight = None
            if self._auth_refresh_queue:
                QTimer.singleShot(500, self._run_next_auth_refresh)

        if getattr(self, "exec_identity_label", None):
            profile, environment = self._refresh_execution_context()
            if self.exec_run_button and self._execution_plan_prepared:
                self.exec_run_button.setEnabled(bool(profile and environment))

    def _on_microsoft_discovery_failed(self, action: str, error: str) -> None:
        if action == "azure_function_apps":
            if self.azure_inventory_button:
                self.azure_inventory_button.setEnabled(True)
            if self.azure_inventory_status_label:
                self.azure_inventory_status_label.setText(f"Azure Function App inventory failed: {error}")
        elif action == "azure_function_app_lookup":
            if self.azure_lookup_button:
                self.azure_lookup_button.setEnabled(True)
            if self.azure_lookup_input:
                self.azure_lookup_input.setEnabled(True)
            if self.azure_lookup_result_label:
                self.azure_lookup_result_label.setText(f"Function App lookup failed: {error}")
        elif action == "powerplatform_flow_inventory":
            if self.pp_flow_inventory_button:
                self.pp_flow_inventory_button.setEnabled(True)
            if self.pp_flow_status_label:
                self.pp_flow_status_label.setText(f"Power Automate flow inventory failed: {error}")
        elif action == "powerplatform_environments":
            if self.pp_refresh_environments_button:
                self.pp_refresh_environments_button.setEnabled(True)
            if self.pp_status_label:
                self.pp_status_label.setText(f"Environment discovery failed: {error}")
        elif action in {"azure", "azure_login"} and self.azure_status_label:
            self.azure_status_label.setText(f"Azure discovery failed: {error}")
        elif self.pp_status_label:
            self.pp_status_label.setText(f"Power Platform discovery failed: {error}")
        if action == "powerplatform_flow_inventory" and self._execution_orchestration_active:
            self._execution_orchestration_active = False
            profile, environment = self._refresh_execution_context()
            if self.exec_run_button:
                self.exec_run_button.setEnabled(bool(self._execution_plan_prepared and profile and environment))
            self._set_execution_stage(6, "attention")
            if self.exec_progress:
                self.exec_progress.setRange(0, 100)
                self.exec_progress.setValue(60)
            if self.exec_progress_label:
                self.exec_progress_label.setText(f"Run failed · {error}")
        expected_action = {
            "azure": {"azure", "azure_login"},
            "powerplatform": {"powerplatform_profiles", "powerplatform_login", "powerplatform_select", "powerplatform_environments"},
        }.get(self._auth_refresh_target_in_flight or "", set())
        if action in expected_action:
            self._auth_refresh_target_in_flight = None
            if self._auth_refresh_queue:
                QTimer.singleShot(500, self._run_next_auth_refresh)

    def _build_execution_page(self) -> QWidget:
        """Task-first orchestration surface with explicit identity and progress."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 26, 30, 28)
        layout.setSpacing(16)

        eyebrow = QLabel("SKYFALL  /  ORCHESTRATION")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Execution Center")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Turn an engineering request into a visible, reviewed workflow. SKYFALL shows each step, "
            "the account context, and the report destination before you start."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        request_panel = QFrame()
        request_panel.setObjectName("orchestrationHero")
        request_layout = QVBoxLayout(request_panel)
        request_layout.setContentsMargins(20, 18, 20, 18)
        request_layout.setSpacing(11)
        request_title = QLabel("What do you want SKYFALL to do?")
        request_title.setObjectName("sectionTitle")
        request_layout.addWidget(request_title)
        request_row = QHBoxLayout()
        self.exec_search_input = QLineEdit()
        self.exec_search_input.setObjectName("orchestrationInput")
        self.exec_search_input.setPlaceholderText("Example: Power Automate flow inventory script")
        self.exec_search_input.setText("Power Automate flow inventory")
        self.exec_search_input.returnPressed.connect(self._prepare_execution_plan)
        request_row.addWidget(self.exec_search_input, 1)
        prepare_button = QPushButton("Prepare plan")
        prepare_button.setObjectName("primaryButton")
        prepare_button.setMinimumHeight(42)
        prepare_button.clicked.connect(self._prepare_execution_plan)
        request_row.addWidget(prepare_button)
        request_layout.addLayout(request_row)
        hint = QLabel("Planning searches your enabled local workspaces. Only extracted metadata is used.")
        hint.setObjectName("muted")
        request_layout.addWidget(hint)
        layout.addWidget(request_panel)

        context_row = QHBoxLayout()
        identity_panel = QFrame()
        identity_panel.setObjectName("contextCard")
        identity_layout = QVBoxLayout(identity_panel)
        identity_layout.setContentsMargins(17, 15, 17, 15)
        identity_layout.setSpacing(7)
        identity_head = QLabel("MICROSOFT IDENTITY")
        identity_head.setObjectName("eyebrow")
        identity_layout.addWidget(identity_head)
        self.exec_identity_label = QLabel("No Power Platform account selected")
        self.exec_identity_label.setObjectName("contextValue")
        self.exec_identity_label.setWordWrap(True)
        identity_layout.addWidget(self.exec_identity_label)
        identity_note = QLabel("Account name, username and tenant only. Tokens and secrets are never displayed.")
        identity_note.setObjectName("muted")
        identity_note.setWordWrap(True)
        identity_layout.addWidget(identity_note)
        context_row.addWidget(identity_panel, 1)

        environment_panel = QFrame()
        environment_panel.setObjectName("contextCard")
        environment_layout = QVBoxLayout(environment_panel)
        environment_layout.setContentsMargins(17, 15, 17, 15)
        environment_layout.setSpacing(7)
        environment_head = QLabel("TARGET ENVIRONMENT")
        environment_head.setObjectName("eyebrow")
        environment_layout.addWidget(environment_head)
        self.exec_environment_label = QLabel("Select an environment in Flow Inventory")
        self.exec_environment_label.setObjectName("contextValue")
        self.exec_environment_label.setWordWrap(True)
        environment_layout.addWidget(self.exec_environment_label)
        environment_note = QLabel("The selected environment is checked again before the run starts.")
        environment_note.setObjectName("muted")
        environment_note.setWordWrap(True)
        environment_layout.addWidget(environment_note)
        context_row.addWidget(environment_panel, 1)
        layout.addLayout(context_row)

        run_panel = QFrame()
        run_panel.setObjectName("panel")
        run_layout = QVBoxLayout(run_panel)
        run_layout.setContentsMargins(18, 16, 18, 16)
        run_layout.setSpacing(10)
        progress_header = QHBoxLayout()
        progress_name = QLabel("RUN PROGRESS")
        progress_name.setObjectName("eyebrow")
        progress_header.addWidget(progress_name)
        progress_header.addStretch(1)
        self.exec_progress_label = QLabel("Waiting for a request")
        self.exec_progress_label.setObjectName("muted")
        progress_header.addWidget(self.exec_progress_label)
        run_layout.addLayout(progress_header)
        self.exec_progress = QProgressBar()
        self.exec_progress.setObjectName("orchestrationProgress")
        self.exec_progress.setRange(0, 100)
        self.exec_progress.setValue(0)
        self.exec_progress.setTextVisible(False)
        self.exec_progress.setFixedHeight(9)
        run_layout.addWidget(self.exec_progress)
        self.exec_stage_labels = []
        stage_rows = [
            "Search approved workspaces",
            "Inspect script requirements",
            "Resolve target environment",
            "Validate Microsoft sign-in",
            "Prepare execution plan",
            "Review and approve",
            "Run controlled inventory",
            "Validate generated output",
            "Save Excel report",
            "Deliver report and summary",
        ]
        stage_grid = QGridLayout()
        stage_grid.setHorizontalSpacing(12)
        stage_grid.setVerticalSpacing(7)
        for index, label_text in enumerate(stage_rows):
            step = QLabel(f"{index + 1:02d}")
            step.setObjectName("stepNumber")
            label = QLabel(label_text)
            label.setObjectName("stepLabel")
            state = QLabel("WAITING")
            state.setObjectName("stepState")
            stage_grid.addWidget(step, index, 0)
            stage_grid.addWidget(label, index, 1)
            stage_grid.addWidget(state, index, 2, Qt.AlignmentFlag.AlignRight)
            self.exec_stage_labels.append(state)
        stage_grid.setColumnStretch(1, 1)
        run_layout.addLayout(stage_grid)
        self.exec_candidate_detail = QLabel(
            "No run plan yet. Prepare a plan to search workspace metadata and check the selected account context."
        )
        self.exec_candidate_detail.setObjectName("muted")
        self.exec_candidate_detail.setWordWrap(True)
        run_layout.addWidget(self.exec_candidate_detail)
        self.exec_candidates = QComboBox()
        self.exec_candidates.setObjectName("orchestrationCandidate")
        self.exec_candidates.setPlaceholderText("Matching scripts appear here")
        self.exec_candidates.currentIndexChanged.connect(self._show_execution_candidate)
        self.exec_candidates.setVisible(False)
        run_layout.addWidget(self.exec_candidates)
        self.exec_run_button = QPushButton("Review and run read-only Flow Inventory")
        self.exec_run_button.setObjectName("primaryButton")
        self.exec_run_button.setMinimumHeight(42)
        self.exec_run_button.setEnabled(False)
        self.exec_run_button.clicked.connect(self._approve_and_run_orchestration)
        run_layout.addWidget(self.exec_run_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(run_panel)

        note = QLabel(
            "v1.0 is introducing supervised orchestration in stages. This first task route uses SKYFALL's "
            "read-only Dataverse inventory API to create the workbook; workspace scripts are inspected as "
            "metadata and are not executed by this route. Every run requires a separate confirmation."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    def _execution_context(self) -> tuple[dict | None, dict | None]:
        profile_id = self.powerplatform_account_store.get_active_profile_id()
        profile = self.powerplatform_account_store.get_profile(profile_id) if profile_id else None
        selected = self.pp_resource_environment_combo.currentData() if self.pp_resource_environment_combo else None
        return profile, selected if isinstance(selected, dict) else None

    def _refresh_execution_context(self) -> tuple[dict | None, dict | None]:
        profile, environment = self._execution_context()
        if self.exec_identity_label:
            if profile:
                identity = " · ".join(str(profile.get(key) or "") for key in ("name", "username", "tenant_id") if profile.get(key))
                self.exec_identity_label.setText(identity or "Saved Microsoft account selected")
            else:
                self.exec_identity_label.setText("No Power Platform account selected")
        if self.exec_environment_label:
            if environment:
                self.exec_environment_label.setText(f"{environment.get('name') or 'Environment'} · {environment.get('environment_id', '')}")
            else:
                selected_id = str((profile or {}).get("selected_environment_id") or "")
                self.exec_environment_label.setText(
                    f"Saved environment {selected_id}; choose it on Flow Inventory to confirm its URL."
                    if selected_id else "Select an environment in Flow Inventory"
                )
        return profile, environment

    def _set_execution_stage(self, index: int, state: str) -> None:
        if not self.exec_stage_labels or index < 0 or index >= len(self.exec_stage_labels):
            return
        label = self.exec_stage_labels[index]
        label.setText(state.upper())
        label.setProperty("stageState", state.lower())
        label.style().unpolish(label)
        label.style().polish(label)

    def _prepare_execution_plan(self) -> None:
        self._execution_plan_prepared = False
        if self.exec_run_button:
            self.exec_run_button.setEnabled(False)
        query = self.exec_search_input.text().strip() if self.exec_search_input else ""
        if not query:
            if self.exec_candidate_detail:
                self.exec_candidate_detail.setText("Describe a script or task to prepare a plan.")
            return
        if self.exec_progress:
            self.exec_progress.setRange(0, 100)
            self.exec_progress.setValue(0)
        if self.exec_progress_label:
            self.exec_progress_label.setText("Searching local metadata…")
        for index in range(10):
            self._set_execution_stage(index, "waiting")
        try:
            matches = self.workspace_manager.search_local(query, file_type="scripts", limit=40)
        except Exception as exc:
            if self.exec_candidate_detail:
                self.exec_candidate_detail.setText(f"Workspace search failed: {type(exc).__name__}: {exc}")
            if self.exec_progress_label:
                self.exec_progress_label.setText("Plan could not be prepared")
            return
        self._exec_candidate_rows = matches
        self._execution_plan_prepared = True
        self._set_execution_stage(0, "complete")
        self._set_execution_stage(1, "complete" if matches else "attention")
        profile, environment = self._refresh_execution_context()
        self._set_execution_stage(2, "complete" if environment else "attention")
        self._set_execution_stage(3, "pending")
        self._set_execution_stage(4, "complete")
        self._set_execution_stage(5, "pending")
        if self.exec_progress:
            completed = 2 + int(bool(matches)) + int(bool(environment))
            self.exec_progress.setValue(completed * 10)
        if self.exec_progress_label:
            self.exec_progress_label.setText(f"Plan prepared · {len(matches)} candidate(s) · account check on run")
        if self.exec_candidates:
            self.exec_candidates.blockSignals(True)
            self.exec_candidates.clear()
            for item in matches:
                self.exec_candidates.addItem(
                    f"{item.get('name')}  ·  {item.get('workspace_name')} / {item.get('relative_path')}",
                    item.get("file_id"),
                )
            self.exec_candidates.setVisible(bool(matches))
            self.exec_candidates.blockSignals(False)
        if self.exec_candidate_detail:
            if matches:
                self._show_execution_candidate(self.exec_candidates.currentIndex())
            else:
                self.exec_candidate_detail.setText(
                    "No matching indexed script was found. Add or scan the approved workspace, or use the built-in read-only Flow Inventory directly."
                )
        can_run = bool(self._execution_plan_prepared and profile and environment)
        if self.exec_run_button:
            self.exec_run_button.setEnabled(can_run)
        if not profile:
            self._set_execution_stage(3, "attention")

    def _show_execution_candidate(self, index: int) -> None:
        if not self.exec_candidate_detail or index < 0 or index >= len(self._exec_candidate_rows):
            return
        item = self._exec_candidate_rows[index]
        params = ", ".join(item.get("parameters") or []) or "No parameters detected"
        imports = ", ".join(item.get("imports") or []) or "No imports detected"
        self.exec_candidate_detail.setText(
            f"{item.get('summary', '')}\nRequirements: {imports}\nParameters: {params}\n"
            "Static metadata only; the source file has not been opened or executed."
        )

    def _approve_and_run_orchestration(self) -> None:
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            QMessageBox.information(
                self, "Microsoft task in progress",
                "Wait for the current Microsoft account or inventory task to finish before starting this run.",
            )
            return
        profile, environment = self._refresh_execution_context()
        if not profile or not environment:
            QMessageBox.information(
                self, "Complete the run context",
                "Select a saved Microsoft account and an exact environment in Flow Inventory first.",
            )
            return
        account = str(profile.get("username") or profile.get("name") or "Microsoft account")
        environment_name = str(environment.get("name") or "selected environment")
        answer = QMessageBox.question(
            self,
            "Approve read-only inventory?",
            f"Generate a Power Automate cloud-flow report from {environment_name} using {account}?\n\n"
            "This uses SKYFALL's read-only Dataverse metadata inventory and creates a local Excel file. "
            "It does not execute the workspace script or modify cloud resources.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._execution_orchestration_active = True
        if self.exec_run_button:
            self.exec_run_button.setEnabled(False)
        self._set_execution_stage(5, "complete")
        self._set_execution_stage(6, "running")
        if self.exec_progress:
            self.exec_progress.setRange(0, 0)
        if self.exec_progress_label:
            self.exec_progress_label.setText("Retrieving flow metadata and preparing the workbook…")
        self._start_powerplatform_flow_inventory()

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
            line.setStyleSheet("color:#B7AFC0;font-size:13px;padding:5px 0;")
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
            "Power Platform reuses isolated Azure CLI sign-in profiles for environment discovery and the Dataverse Web API. Azure Function App and Power Automate inventories are read-only and can generate local Excel reports. Cloud changes and script execution are disabled in v0.9.2."
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
        panel_layout.addWidget(self._status_row("Version", "0.9.2", "good"))
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
        val.setStyleSheet("font-size:19px;font-weight:750;color:#F4EFF8;")
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
        heading.setStyleSheet("font-size:13px;font-weight:700;color:#E8E1EC;")
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
        name.setStyleSheet("color:#A69EAD;font-size:11px;")
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

        self._track_microsoft_auth_intent(message)
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

    def _track_microsoft_auth_intent(self, message: str) -> None:
        """Remember that a chat sign-in flow should refresh the corresponding UI page.

        The MCP server is a separate process, so the desktop polls its own
        read-only CLI discovery after the user completes the browser flow.
        """
        text = re.sub(r"\s+", " ", (message or "").casefold())
        auth_words = ("login", "log in", "sign in", "signin", "authenticate", "connect", "add account")
        if not any(word in text for word in auth_words):
            return
        if any(word in text for word in ("azure", "subscription", "az cli")):
            self._pending_auth_refresh_targets.add("azure")
            self._auth_refresh_queue.clear()
            self._auth_refresh_attempts = 0
        if any(word in text for word in ("power platform", "powerplatform", "pac cli", "dataverse")):
            self._pending_auth_refresh_targets.add("powerplatform")
            self._auth_refresh_queue.clear()
            self._auth_refresh_attempts = 0

    def _refresh_pending_auth_targets(self) -> None:
        """Queue one read-only refresh for each platform involved in a chat login."""
        if not self._pending_auth_refresh_targets:
            return
        self._auth_refresh_attempts += 1
        if self._auth_refresh_attempts > 10:
            self._pending_auth_refresh_targets.clear()
            self._auth_refresh_queue.clear()
            self._auth_refresh_attempts = 0
            return
        self._auth_refresh_queue = sorted(self._pending_auth_refresh_targets)
        self._run_next_auth_refresh()

    def _run_next_auth_refresh(self) -> None:
        if not self._auth_refresh_queue:
            return
        if self._microsoft_worker is not None and self._microsoft_worker.isRunning():
            QTimer.singleShot(1200, self._run_next_auth_refresh)
            return
        target = self._auth_refresh_queue.pop(0)
        self._auth_refresh_target_in_flight = target
        if target == "azure":
            self._start_microsoft_worker("azure", "all")
        elif target == "powerplatform":
            self._start_microsoft_worker("powerplatform_profiles")
        else:
            self._auth_refresh_target_in_flight = None
            QTimer.singleShot(0, self._run_next_auth_refresh)

    def _on_ai_status_changed(self, status: str) -> None:
        self.statusBar().showMessage(f"SKYFALL AI runtime: {status}")

    def _on_ai_connected(self) -> None:
        self._set_status_value("AI RUNTIME", "Connected")
        self._set_status_value("SKYFALL AI runtime", "Connected", "good")
        self._set_status_value("AI provider", "GitHub Copilot connected", "good")
        self._set_status_value("MCP Tools", "36 tools — read-only + sign-in", "good")
        self._set_status_value("MCP integration", "Core + workspace + Microsoft accounts + Azure lookup + Power Platform + unified cloud intelligence", "good")
        self.top_state.setText("●  COPILOT + MCP CONNECTED")
        self.top_state.setObjectName("statusGood")
        self.top_state.style().unpolish(self.top_state)
        self.top_state.style().polish(self.top_state)
        self.chat_subtitle.setText(
            "Connected to GitHub Copilot and SKYFALL's local MCP server. Thirty-six tools are registered for "
            "core status, approved workspace metadata, Azure account/subscription discovery, Power Platform "
            "profile/environment discovery, Azure Function App name lookup and inventory, Power Automate flow inventory, "
            "unified cloud intelligence, cross-platform correlation, monitoring, reporting, plan-only operations, and "
            "plan-only execution resolution/simulation history. Ask which subscription contains a Function App by name. "
            "Explicitly requested Microsoft sign-in is available; resource changes and script execution are not enabled."
        )
        self.chat_input.setEnabled(True)
        self.chat_send_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.history_list.setEnabled(True)
        self._refresh_conversation_list(select_id=self.current_conversation.id)
        self.statusBar().showMessage("SKYFALL AI connected — 36 MCP tools available — general script execution disabled")

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
        if self._pending_auth_refresh_targets:
            QTimer.singleShot(1200, self._refresh_pending_auth_targets)

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

    def _delete_selected_conversation(self) -> None:
        """Delete the selected local transcript and continue in a fresh chat."""
        if self._request_active or (self.copilot_worker and self.copilot_worker.is_busy):
            QMessageBox.information(
                self, "Conversation in progress",
                "Wait for the current response to finish before deleting a conversation.",
            )
            return
        current = self.history_list.currentItem() if self.history_list else None
        conversation_id = str(current.data(Qt.ItemDataRole.UserRole)) if current else self.current_conversation.id
        conversation = self.conversation_store.get_conversation(conversation_id)
        if conversation is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete conversation?",
            f"Delete “{conversation.title}” and its locally stored messages? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        was_current = conversation_id == self.current_conversation.id
        self.conversation_store.delete_conversation(conversation_id)
        if was_current:
            replacement = self.conversation_store.create_conversation()
            self.conversation_store.set_active_conversation(replacement.id)
            self.current_conversation = replacement
            self._pending_conversation_id = replacement.id
            self._refresh_conversation_list(select_id=replacement.id)
            self._render_conversation(replacement.id)
            if self.copilot_worker and self.copilot_worker.is_connected:
                accepted = self.copilot_worker.switch_conversation(
                    replacement.copilot_session_id, resume=False
                )
                if not accepted:
                    self._pending_conversation_id = None
            else:
                self.conversation_store.set_active_conversation(replacement.id)
        else:
            self._refresh_conversation_list(select_id=self.current_conversation.id)


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
        if getattr(self, "chat_page_title", None) is not None:
            self.chat_page_title.setText(conversation.title or "New conversation")
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
        if self.delete_chat_button is not None:
            self.delete_chat_button.setEnabled(self.history_list.count() > 0)
        if self.history_search_input is not None:
            self._filter_conversation_list(self.history_search_input.text())

    def _filter_conversation_list(self, query: str) -> None:
        if self.history_list is None:
            return
        needle = query.strip().casefold()
        for index in range(self.history_list.count()):
            item = self.history_list.item(index)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

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
