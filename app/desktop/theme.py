"""Shared visual theme for the SKYFALL desktop application."""

APP_STYLESHEET = r"""
* {
    font-family: "Segoe UI", "Arial", sans-serif;
    color: #E8ECF5;
}
QMainWindow, QWidget#appRoot, QWidget#contentHost {
    background: #0B1020;
}
QFrame#sidebar {
    background: #0E1528;
    border-right: 1px solid #202B43;
}
QFrame#brandMark {
    background: #172642;
    border: 1px solid #31517B;
    border-radius: 13px;
}
QLabel#brandLetter {
    color: #8BC5FF;
    font-size: 22px;
    font-weight: 800;
}
QLabel#brandName {
    color: #F4F7FD;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 3px;
}
QLabel#brandCaption {
    color: #8291AA;
    font-size: 9px;
    letter-spacing: 1.5px;
}
QPushButton#navButton {
    background: transparent;
    color: #9AA8BE;
    border: 1px solid transparent;
    border-radius: 9px;
    text-align: left;
    padding: 10px 12px;
    font-size: 13px;
}
QPushButton#navButton:hover {
    background: #17233A;
    color: #F2F6FC;
}
QPushButton#navButton:checked {
    background: #192B46;
    color: #A9D4FF;
    border: 1px solid #2C4B70;
    font-weight: 650;
}
QFrame#accountPanel, QFrame#panel, QFrame#metricCard, QFrame#quickCard {
    background: #111B2F;
    border: 1px solid #24324A;
    border-radius: 13px;
}
QLabel#muted {
    color: #8291AA;
    font-size: 11px;
}
QLabel#pageTitle {
    color: #F4F7FD;
    font-size: 23px;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #E7ECF6;
    font-size: 14px;
    font-weight: 700;
}
QLabel#metricValue {
    color: #F6F8FC;
    font-size: 22px;
    font-weight: 750;
}
QLabel#metricLabel {
    color: #8E9CB2;
    font-size: 11px;
}
QLabel#statusGood {
    color: #75D6B0;
    background: #12352F;
    border: 1px solid #205B4E;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 650;
}
QLabel#statusPending {
    color: #F0C77D;
    background: #392D1D;
    border: 1px solid #64502C;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 650;
}
QLabel#statusOffline {
    color: #A0AEC2;
    background: #202B3E;
    border: 1px solid #34445D;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 650;
}
QPushButton#primaryButton {
    background: #3478C8;
    color: white;
    border: 1px solid #4B91E0;
    border-radius: 9px;
    padding: 10px 15px;
    font-weight: 650;
}
QPushButton#primaryButton:hover { background: #4389DA; }
QPushButton#primaryButton:pressed { background: #2865AD; }
QPushButton#secondaryButton {
    background: #17243A;
    color: #C9D5E7;
    border: 1px solid #2D405C;
    border-radius: 9px;
    padding: 9px 12px;
}
QPushButton#secondaryButton:hover { background: #21334E; }
QLineEdit#chatInput {
    background: #101A2D;
    border: 1px solid #30425E;
    border-radius: 10px;
    padding: 12px 14px;
    color: #F1F5FB;
    selection-background-color: #3478C8;
    font-size: 13px;
}
QLineEdit#chatInput:focus { border: 1px solid #5796D8; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #33445F;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QFrame#userMessage {
    background: #1A3555;
    border: 1px solid #31577F;
    border-radius: 12px;
}
QFrame#assistantMessage {
    background: #121E32;
    border: 1px solid #293A55;
    border-radius: 12px;
}
QLabel#messageText { font-size: 13px; }
QLabel#eyebrow {
    color: #7F9ABB;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.3px;
}
QFrame#topBar {
    background: #0B1020;
    border-bottom: 1px solid #202B43;
}
QLabel#connectionDot { color: #F0C77D; font-size: 12px; }
QTextBrowser#placeholderText {
    background: transparent;
    border: none;
    color: #AAB7CA;
    font-size: 13px;
}
"""

APP_STYLESHEET += r"""
QFrame#chatHistoryPanel {
    background: #0E1528;
    border: 1px solid #202B43;
    border-radius: 13px;
}
QListWidget#conversationList {
    background: transparent;
    border: none;
    outline: none;
    color: #B8C5D8;
    font-size: 12px;
}
QListWidget#conversationList::item {
    padding: 10px 9px;
    margin: 2px 0;
    border: 1px solid transparent;
    border-radius: 8px;
}
QListWidget#conversationList::item:hover {
    background: #17233A;
    color: #F2F6FC;
}
QListWidget#conversationList::item:selected {
    background: #192B46;
    color: #A9D4FF;
    border: 1px solid #2C4B70;
}
"""

APP_STYLESHEET += r"""
QCheckBox {
    color: #C9D5E7;
    spacing: 9px;
    font-size: 12px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #405777;
    border-radius: 4px;
    background: #101A2D;
}
QCheckBox::indicator:checked {
    background: #3478C8;
    border: 1px solid #6AA5E8;
}
"""


APP_STYLESHEET += r"""
QFrame#capabilityCard {
    background: #111D32;
    border: 1px solid #2A3B56;
    border-radius: 12px;
}
QFrame#capabilityCard:hover {
    background: #14223A;
    border: 1px solid #3C5D85;
}
QLabel#capabilityTitle {
    color: #F4F7FD;
    font-size: 14px;
    font-weight: 700;
}
QLabel#capabilityDescription {
    color: #A9B8CE;
    font-size: 12px;
}
QLabel#capabilityCategory {
    color: #91BCEB;
    background: #192C47;
    border: 1px solid #304C70;
    border-radius: 7px;
    padding: 4px 7px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#capabilityRisk {
    color: #AABBD1;
    background: #19263A;
    border: 1px solid #31435E;
    border-radius: 7px;
    padding: 4px 7px;
    font-size: 9px;
    font-weight: 700;
}
"""


APP_STYLESHEET += r"""
QLabel#readOnlyBadge {
    color: #8FE0BF;
    background: #12352F;
    border: 1px solid #276452;
    border-radius: 9px;
    padding: 7px 11px;
    font-size: 9px;
    font-weight: 750;
    letter-spacing: 1px;
}
QLabel#operationStatus {
    color: #B9CBE3;
    background: #14223A;
    border: 1px solid #2A4567;
    border-radius: 9px;
    padding: 11px 13px;
    font-size: 11px;
}
QFrame#emptyStateCard {
    background: #0F1A2D;
    border: 1px dashed #354B69;
    border-radius: 12px;
}
QLabel#emptyStateTitle {
    color: #EAF1FB;
    font-size: 15px;
    font-weight: 700;
}
QFrame#capabilityCard {
    background-color: #111D32;
}
QFrame#metricCard {
    background-color: #111B2F;
}
"""

# Keep the v0.9.2 palette overrides last so widget-specific rules above cannot
# repaint the chat canvas or sidebar controls with the older navy colors.
APP_STYLESHEET += r"""
QMainWindow, QWidget#appRoot, QWidget#contentHost { background: #121821; }
QFrame#sidebar, QFrame#chatHistoryPanel { background: #171F2A; border-color: #2A3543; }
QFrame#topBar { background: #121821; border-color: #2A3543; }
QFrame#panel, QFrame#metricCard, QFrame#quickCard { background: #1B2531; border-color: #303D4D; }
QFrame#assistantMessage { background: #1C2733; border-color: #354454; }
QFrame#userMessage { background: #25384B; border-color: #3B5873; }
QLineEdit#chatInput { background: #1B2531; border-color: #3A4859; }
QListWidget#conversationList::item:selected { background: #283B50; color: #D7E7F7; border-color: #496782; }
QPushButton#navButton:checked { background: #283B50; color: #D7E7F7; border-color: #496782; }
QComboBox {
    background: #1B2531; color: #E6EBF1; border: 1px solid #3A4859;
    border-radius: 8px; padding: 7px 10px;
}
QComboBox:hover { border-color: #617991; }
QComboBox QAbstractItemView {
    background: #202B37; color: #E6EBF1; selection-background-color: #344B61;
    selection-color: #FFFFFF; border: 1px solid #3A4859; outline: 0;
}
QScrollArea#chatScroll { background: #171F2A; border: 1px solid #2D3947; border-radius: 12px; }
QWidget#chatMessageCanvas { background: #171F2A; }
QScrollArea#sidebarNavigationScroll { background: transparent; border: none; }
QFrame#accountPanel { background: #1B2531; border-color: #303D4D; border-radius: 11px; }
QPushButton#dangerButton {
    background: #33252A; color: #F0D9DC; border: 1px solid #61434A;
    border-radius: 9px; padding: 9px 12px;
}
QPushButton#dangerButton:hover { background: #493038; border-color: #80565E; }
QPushButton#dangerButton:disabled { color: #78818B; background: #20262D; border-color: #303942; }
"""

# v1.0 visual direction: calm light surfaces with a restrained blue/teal accent,
# clear hierarchy and generous spacing for long engineering sessions.
APP_STYLESHEET += r"""
* { color: #1E2934; }
QMainWindow, QWidget#appRoot, QWidget#contentHost { background: #F3F6F8; }
QFrame#sidebar, QFrame#chatHistoryPanel { background: #FFFFFF; border-color: #DCE4EA; }
QFrame#topBar { background: #FFFFFF; border-color: #E1E7EC; }
QFrame#panel, QFrame#metricCard, QFrame#quickCard, QFrame#accountPanel,
QFrame#contextCard, QFrame#orchestrationHero {
    background: #FFFFFF; border: 1px solid #E0E6EB; border-radius: 13px;
}
QFrame#capabilityCard { background: #FFFFFF; border: 1px solid #E0E6EB; border-radius: 13px; }
QFrame#capabilityCard:hover { background: #F8FBFC; border-color: #C7DCE3; }
QLabel#brandLetter { color: #226B83; }
QFrame#brandMark { background: #E9F3F6; border-color: #BFD8E1; }
QLabel#brandName, QLabel#pageTitle, QLabel#sectionTitle,
QLabel#contextValue, QLabel#emptyStateTitle { color: #17232E; }
QLabel#brandCaption, QLabel#muted, QLabel#metricLabel { color: #647585; }
QLabel#eyebrow, QLabel#stepNumber { color: #557589; }
QLabel#capabilityTitle { color: #17232E; }
QLabel#capabilityDescription { color: #526373; }
QLabel#capabilityCategory { color: #23637A; background: #EAF3F6; border-color: #D3E4E9; }
QLabel#capabilityRisk { color: #526373; background: #F0F4F6; border-color: #DCE4E9; }
QLabel#stepLabel { color: #344655; font-size: 12px; }
QLabel#stepState { color: #82909B; font-size: 9px; font-weight: 750; letter-spacing: .8px; }
QLabel#stepState[stageState="complete"] { color: #16745B; }
QLabel#stepState[stageState="running"] { color: #226B9A; }
QLabel#stepState[stageState="ready"] { color: #16745B; }
QLabel#stepState[stageState="attention"] { color: #A15C16; }
QPushButton#navButton { color: #526373; }
QPushButton#navButton:hover { background: #F0F5F7; color: #17232E; }
QPushButton#navButton:checked { background: #E7F1F4; color: #1E6177; border-color: #BFD7E0; }
QPushButton#primaryButton { background: #236F89; border-color: #236F89; color: #FFFFFF; }
QPushButton#primaryButton:hover { background: #1D6077; }
QPushButton#secondaryButton { background: #F4F7F9; color: #344655; border-color: #D9E1E7; }
QPushButton#secondaryButton:hover { background: #EAF0F3; }
QPushButton#dangerButton { background: #FFF4F3; color: #9D3F3A; border-color: #E7C7C4; }
QPushButton#dangerButton:hover { background: #FBE8E6; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: #FFFFFF; color: #1E2934; border: 1px solid #CFD9E0;
    border-radius: 9px; selection-background-color: #CBE3EA; selection-color: #153B4A;
}
QLineEdit#chatInput, QLineEdit#orchestrationInput {
    background: #FFFFFF; color: #1E2934; border-color: #CFD9E0;
    padding: 11px 13px; font-size: 13px;
}
QLineEdit#chatInput:focus, QLineEdit#orchestrationInput:focus { border-color: #438BA2; }
QCheckBox { color: #344655; }
QCheckBox::indicator { background: #FFFFFF; border-color: #BAC9D2; }
QCheckBox::indicator:checked { background: #2B8193; border-color: #2B8193; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #1E2934; selection-background-color: #E1EFF3; selection-color: #153B4A; }
QListWidget#conversationList { color: #344655; }
QListWidget#conversationList::item:hover { background: #F0F5F7; color: #17232E; }
QListWidget#conversationList::item:selected { background: #E7F1F4; color: #1E6177; border-color: #BFD7E0; }
QScrollArea#chatScroll { background: #F8FAFB; border-color: #E0E6EB; }
QWidget#chatMessageCanvas { background: #F8FAFB; }
QFrame#assistantMessage { background: #FFFFFF; border-color: #DFE6EA; }
QFrame#userMessage { background: #EAF3F7; border-color: #D0E2E9; }
QLabel#messageText { color: #243441; }
QFrame#emptyStateCard { background: #F7FAFB; border-color: #CBD9E0; }
QLabel#statusGood { background: #E8F5F0; color: #187252; border-color: #C5E6D8; }
QLabel#statusPending { background: #FFF5E6; color: #8A5B1B; border-color: #F1D9B4; }
QLabel#statusOffline { background: #F0F3F5; color: #5B6A77; border-color: #DCE3E8; }
QProgressBar#orchestrationProgress { background: #E8EEF1; border: none; border-radius: 4px; }
QProgressBar#orchestrationProgress::chunk { background: #2B8193; border-radius: 4px; }
QTableWidget { background: #FFFFFF; alternate-background-color: #F6F9FA; color: #243441; border-color: #DDE5EA; }
QHeaderView::section { background: #F0F4F6; color: #455A69; border: 0; padding: 8px; }
"""
