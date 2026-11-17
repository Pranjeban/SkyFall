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

# v1.0 visual direction: Kiro-inspired graphite and plum surfaces with violet
# focus accents, translucent layered panels and restrained status colors.
APP_STYLESHEET += r"""
* { color: #F0ECF4; }
QMainWindow, QWidget#appRoot, QWidget#contentHost {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #15131A, stop:0.58 #17141D, stop:1 #211A29);
}
QFrame#sidebar { background: rgba(25,22,30,248); border-right: 1px solid #302A37; }
QWidget#sidebarNavigationContent { background: rgba(28,25,34,255); border-radius: 13px; }
QScrollArea#sidebarNavigationScroll { background: transparent; border: none; }
QFrame#chatHistoryPanel, QFrame#topBar { background: rgba(26,23,32,242); border-color: #342D3C; }
QFrame#panel, QFrame#metricCard, QFrame#quickCard, QFrame#accountPanel,
QFrame#contextCard, QFrame#orchestrationHero, QFrame#capabilityCard {
    background: rgba(35,31,42,236); border: 1px solid rgba(174,145,200,54); border-radius: 14px;
}
QFrame#capabilityCard:hover, QFrame#quickCard:hover { background: rgba(43,36,53,246); border-color: rgba(190,148,235,115); }
QFrame#brandMark { background: rgba(111,71,145,95); border: 1px solid rgba(191,144,235,135); border-radius: 13px; }
QLabel#brandLetter { color: #D7B6FF; }
QLabel#brandName, QLabel#pageTitle, QLabel#sectionTitle, QLabel#contextValue,
QLabel#capabilityTitle, QLabel#emptyStateTitle { color: #F4EFF8; }
QLabel#brandCaption, QLabel#muted, QLabel#metricLabel { color: #A69EAD; }
QLabel#eyebrow, QLabel#stepNumber { color: #B28CDD; }
QLabel#capabilityDescription { color: #C4BBCB; }
QLabel#capabilityCategory { color: #D3B3FF; background: rgba(115,72,151,62); border-color: rgba(190,146,236,92); }
QLabel#capabilityRisk { color: #C7BDCF; background: rgba(74,64,82,110); border-color: rgba(171,155,185,58); }
QLabel#stepLabel { color: #DED7E4; font-size: 12px; }
QLabel#stepState { color: #8E8696; font-size: 9px; font-weight: 750; letter-spacing: .8px; }
QLabel#stepState[stageState="complete"] { color: #6DD7B2; }
QLabel#stepState[stageState="running"] { color: #C79AFF; }
QLabel#stepState[stageState="ready"] { color: #6DD7B2; }
QLabel#stepState[stageState="attention"] { color: #F0B76B; }
QPushButton#navButton { background: transparent; color: #B4ACBA; border: 1px solid transparent; border-radius: 9px; }
QPushButton#navButton:hover { background: rgba(151,112,183,34); color: #F3ECFA; }
QPushButton#navButton:checked { background: rgba(142,86,186,61); color: #E4CAFF; border-color: rgba(192,143,238,119); }
QPushButton#primaryButton { background: #8751B5; border: 1px solid #A26AD0; color: #FFFFFF; border-radius: 10px; }
QPushButton#primaryButton:hover { background: #9862C7; border-color: #BC8BE4; }
QPushButton#secondaryButton { background: rgba(52,45,62,190); color: #E3DCE9; border: 1px solid rgba(183,163,199,77); border-radius: 10px; }
QPushButton#secondaryButton:hover { background: rgba(73,57,91,225); border-color: rgba(196,153,233,140); }
QPushButton#dangerButton { background: rgba(94,47,58,170); color: #FFD9E1; border: 1px solid rgba(214,121,145,110); border-radius: 10px; }
QPushButton#dangerButton:hover { background: rgba(118,53,70,210); border-color: #D985A0; }
QPushButton#dangerButton:disabled { color: #766E7A; background: rgba(45,41,49,160); border-color: #403946; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: rgba(29,26,35,238); color: #F0ECF4; border: 1px solid rgba(163,148,177,84);
    border-radius: 10px; selection-background-color: #765094; selection-color: #FFFFFF;
}
QLineEdit#chatInput, QLineEdit#orchestrationInput { background: rgba(32,29,39,245); color: #F0ECF4; border-color: #4C4058; padding: 11px 13px; font-size: 13px; }
QLineEdit#chatInput:focus, QLineEdit#orchestrationInput:focus { border-color: #B27DE1; }
QComboBox QAbstractItemView { background: #211D27; color: #F0ECF4; selection-background-color: #503665; selection-color: #FFFFFF; border: 1px solid #594769; }
QCheckBox { color: #D8D0DF; }
QCheckBox::indicator { background: #211D27; border: 1px solid #665675; border-radius: 4px; }
QCheckBox::indicator:checked { background: #9561C4; border-color: #C69AE9; }
QListWidget#conversationList { background: transparent; color: #C9C1D0; }
QListWidget#conversationList::item:hover { background: rgba(151,112,183,34); color: #F4EFF8; }
QListWidget#conversationList::item:selected { background: rgba(142,86,186,61); color: #E4CAFF; border-color: rgba(192,143,238,119); }
QScrollArea#chatScroll { background: rgba(24,22,29,238); border: 1px solid rgba(163,148,177,65); border-radius: 14px; }
QWidget#chatMessageCanvas { background: rgba(24,22,29,238); }
QFrame#assistantMessage { background: rgba(40,36,46,235); border: 1px solid rgba(171,155,185,62); border-radius: 14px; }
QFrame#userMessage { background: rgba(72,50,92,225); border: 1px solid rgba(184,135,222,100); border-radius: 14px; }
QLabel#messageText { color: #F0ECF4; }
QFrame#emptyStateCard { background: rgba(35,31,42,220); border: 1px dashed rgba(174,145,200,90); border-radius: 13px; }
QLabel#statusGood { background: rgba(35,93,73,155); color: #9BE9CD; border-color: rgba(93,193,154,105); }
QLabel#statusPending { background: rgba(104,74,36,155); color: #F5D095; border-color: rgba(206,160,89,115); }
QLabel#statusOffline { background: rgba(61,56,68,175); color: #C0B8C8; border-color: rgba(161,150,173,75); }
QProgressBar#orchestrationProgress { background: rgba(70,61,78,180); border: 1px solid rgba(180,154,205,55); border-radius: 5px; }
QProgressBar#orchestrationProgress::chunk { background: #A66BDB; border-radius: 4px; }
QTableWidget { background: rgba(30,27,36,242); alternate-background-color: rgba(40,36,47,235); color: #E8E1EC; border-color: #443B4D; gridline-color: #3B3442; selection-background-color: #503665; }
QHeaderView::section { background: #29242F; color: #C8B8D7; border: 0; padding: 8px; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(159,130,179,130); border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: rgba(192,146,225,185); }
"""
