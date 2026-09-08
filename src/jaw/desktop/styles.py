"""Qt stylesheet for the native JAW desktop window."""

STYLESHEET = """
QMainWindow, QWidget { background: #17191d; color: #e7eaf0; font: 10pt "Segoe UI"; }
QFrame#panel { background: transparent; border: none; border-radius: 0; }
QFrame#workExperiencePanel { background: transparent; border: none; border-radius: 0; }
QFrame#matrixPanel { background: transparent; border: none; }
QFrame#paneMatrixDivider { background: #3d4651; border: none; }
QLabel#eyebrow { color: #7d8798; font-size: 9pt; font-weight: 600; }
QLabel#heading { color: #f5f7fa; font-size: 15pt; font-weight: 650; }
QFrame#settingsPanel { background: transparent; border: none; }
QFrame#settingsSection { background: transparent; border: none; }
QPushButton#settingsSectionHeader { background: transparent; color: #65a6e8; border: none; border-left: 2px solid #3b82c4; border-radius: 4px; padding: 4px 9px; text-align: left; font-weight: 650; }
QPushButton#settingsSectionHeader:hover { background: #292e36; border: none; border-left: 2px solid #65a6e8; }
QPushButton#analysisMethod {
  background: #22262c; color: #aab2bf; border: 1px solid #3a414b;
  border-radius: 4px; padding: 5px 10px;
}
QPushButton#analysisMethod:hover { background: #2b3139; border-color: #527aa3; }
QPushButton#analysisMethod:checked {
  background: #214e78; color: #f4f8fc; border-color: #65a6e8; font-weight: 650;
}
QScrollArea#settingsScroll { background: transparent; border: none; }
QScrollArea#settingsScroll > QWidget > QWidget { background: transparent; }
QScrollArea#settingsScroll QScrollBar:vertical {
  width: 4px; margin: 0; background: transparent; border: none;
}
QScrollArea#settingsScroll QScrollBar::handle:vertical {
  min-height: 22px; background: #66717e; border-radius: 2px;
}
QScrollArea#settingsScroll QScrollBar::handle:vertical:hover { background: #8b98a7; }
QScrollArea#settingsScroll QScrollBar::add-line:vertical,
QScrollArea#settingsScroll QScrollBar::sub-line:vertical { height: 0; border: none; background: transparent; }
QScrollArea#settingsScroll QScrollBar::add-page:vertical,
QScrollArea#settingsScroll QScrollBar::sub-page:vertical { background: transparent; }
QLabel#value { color: #f5f7fa; font: 13pt "Consolas"; }
QLabel#status { color: #85d6b5; }
QPushButton {
  background: #2b2f36; border: 1px solid #3a3f48; border-radius: 5px;
  padding: 8px 10px; color: #e7eaf0;
}
QToolButton {
  background: #2b2f36; border: 1px solid #3a3f48; border-radius: 5px;
  padding: 8px 10px; color: #e7eaf0;
}
QToolButton:hover { background: #353a43; border-color: #4d86c6; }
QToolButton#settingsGear { background: #17191d; border: none; border-radius: 0; padding: 0; }
QToolButton#settingsGear:hover { background: #17191d; border: none; }
QToolButton#paneMenuButton { background: transparent; border: none; border-radius: 0; padding: 2px; }
QToolButton#paneMenuButton:hover { background: transparent; border: none; }
QToolButton#statusCapabilitySet { border-radius: 0; border: none; padding: 0 8px; }
QToolButton#statusDate, QToolButton#statusName, QToolButton#statusWorkExperience, QToolButton#statusUser { border-radius: 0; border: 1px solid #4d5663; padding: 0 8px; }
QToolButton#statusLayer { border-radius: 0; border: 1px solid #4d5663; padding: 0 8px; color: #65a6e8; font-weight: 650; }
QToolButton#statusLayer[disabledState="true"] { color: #d8666a; }
QFrame#statusCycleStack { background: transparent; border: none; }
QStatusBar { border: none; }
QMenu { background: #202329; border: 1px solid #3a3f48; color: #e7eaf0; }
QMenu::item { padding: 7px 28px 7px 10px; }
QMenu::item:selected { background: #214e78; }
QPushButton:hover { background: #353a43; border-color: #4d86c6; }
QPushButton:pressed { background: #4179b5; }
QPushButton:checked { background: #214e78; border-color: #65a6e8; }
QPushButton[childIterator="true"] { padding: 2px 8px 3px 8px; }
QPushButton[childIterator="true"]:hover { background: #2b2f36; border-color: #3a3f48; }
QPushButton[childIterator="true"]:checked,
QPushButton[childIterator="true"]:checked:hover { background: #2b2f36; border-color: #65a6e8; }
QPushButton[childIterator="true"][childDisabled="true"] { background: transparent; border-color: #754447; color: #8d929a; }
QPushButton[childIterator="true"][childDisabled="true"]:hover,
QPushButton[childIterator="true"][childDisabled="true"]:checked { background: transparent; border-color: #8b5054; color: #8d929a; }
QPushButton#primary { background: #2f72b7; border-color: #438bd3; font-weight: 650; }
QPushButton#primary:hover { background: #3981c9; }
QPushButton.matrix, QToolButton.matrix { min-width: 74px; min-height: 33px; text-align: center; padding: 14px 7px 5px 7px; }
QPushButton.matrix[assigned="true"], QToolButton.matrix[assigned="true"] { background: #344353; border-color: #49647d; }
QLabel#matrixKey { background: transparent; border: none; color: #e7eaf0; font-size: 9pt; }
QComboBox {
  background: #292d34; border: 1px solid #3c424c; border-radius: 5px;
  padding: 7px; color: #eef1f5;
}
/* Flat content surfaces are the desktop default. Interactive controls opt into borders. */
QListWidget { background: transparent; border: none; border-radius: 0; padding: 0; }
QScrollArea { background: transparent; border: none; }
QListWidget#workExperienceList QScrollBar:vertical {
  width: 4px; margin: 0; background: transparent; border: none;
}
QListWidget#workExperienceList { background: transparent; border: none; padding: 0; }
QListWidget#workExperienceList::item { padding: 0 6px 0 10px; }
QListWidget#workExperienceList QScrollBar::handle:vertical {
  min-height: 22px; background: #66717e; border-radius: 2px;
}
QListWidget#workExperienceList QScrollBar::handle:vertical:hover { background: #8b98a7; }
QListWidget#workExperienceList QScrollBar::add-line:vertical,
QListWidget#workExperienceList QScrollBar::sub-line:vertical { height: 0; border: none; background: transparent; }
QListWidget#workExperienceList QScrollBar::add-page:vertical,
QListWidget#workExperienceList QScrollBar::sub-page:vertical { background: transparent; }
QLabel#captureCompany { color: #9aa6b5; font-size: 9pt; font-weight: 650; padding: 1px 6px 0 6px; }
QLabel#captureTitle { color: #f4f7fa; font-size: 12pt; font-weight: 700; padding: 0 6px 3px 6px; }
QLabel#captureAnalysisStatus { color: #7f8997; font-size: 9pt; padding: 1px 6px 0 6px; }
QTabBar#captureTabs { background: transparent; border: none; }
QTabBar#captureTabs::tab {
  background: transparent; color: #8f9aaa; border: none;
  border-bottom: 2px solid transparent; padding: 5px 9px 4px 9px;
}
QTabBar#captureTabs::tab:hover { color: #c8d7e6; }
QTabBar#captureTabs::tab:selected {
  color: #65a6e8; border: none; border-bottom: 2px solid #65a6e8;
}
QStackedWidget#captureTabPages { background: transparent; border: none; }
QListWidget#captureFieldsList { background: transparent; border: none; border-radius: 0; padding: 2px; }
QListWidget#captureFieldsList::item,
QListWidget#captureReviewList::item,
QListWidget#captureFixtureList::item { padding: 3px 6px; }
QListWidget#captureList::item, QListWidget#captureQuestionsList::item { padding: 3px 6px; }
QListWidget#smartCaptureFieldList { background: transparent; border: none; }
QListWidget#smartCaptureFieldList::item { padding: 2px 4px; }
QListWidget#captureFieldsList QScrollBar:vertical,
QListWidget#captureReviewList QScrollBar:vertical,
QListWidget#captureFixtureList QScrollBar:vertical,
QListWidget#captureList QScrollBar:vertical,
QListWidget#captureQuestionsList QScrollBar:vertical,
QListWidget#smartCaptureFieldList QScrollBar:vertical {
  width: 4px; margin: 0; background: transparent; border: none;
}
QListWidget#captureFieldsList QScrollBar::handle:vertical,
QListWidget#captureReviewList QScrollBar::handle:vertical,
QListWidget#captureFixtureList QScrollBar::handle:vertical,
QListWidget#captureList QScrollBar::handle:vertical,
QListWidget#captureQuestionsList QScrollBar::handle:vertical,
QListWidget#smartCaptureFieldList QScrollBar::handle:vertical {
  min-height: 22px; background: #66717e; border-radius: 2px;
}
QListWidget#captureFieldsList QScrollBar::handle:vertical:hover,
QListWidget#captureReviewList QScrollBar::handle:vertical:hover,
QListWidget#captureFixtureList QScrollBar::handle:vertical:hover,
QListWidget#captureList QScrollBar::handle:vertical:hover,
QListWidget#captureQuestionsList QScrollBar::handle:vertical:hover,
QListWidget#smartCaptureFieldList QScrollBar::handle:vertical:hover { background: #8b98a7; }
QListWidget#captureFieldsList QScrollBar::add-line:vertical,
QListWidget#captureFieldsList QScrollBar::sub-line:vertical,
QListWidget#captureReviewList QScrollBar::add-line:vertical,
QListWidget#captureReviewList QScrollBar::sub-line:vertical,
QListWidget#captureFixtureList QScrollBar::add-line:vertical,
QListWidget#captureFixtureList QScrollBar::sub-line:vertical,
QListWidget#captureList QScrollBar::add-line:vertical,
QListWidget#captureList QScrollBar::sub-line:vertical,
QListWidget#captureQuestionsList QScrollBar::add-line:vertical,
QListWidget#captureQuestionsList QScrollBar::sub-line:vertical,
QListWidget#smartCaptureFieldList QScrollBar::add-line:vertical,
QListWidget#smartCaptureFieldList QScrollBar::sub-line:vertical { height: 0; border: none; background: transparent; }
QFrame#answersPanel { background: transparent; border: none; }
QFrame#answersHeader { background: transparent; border: none; }
QLabel#answersHeading { color: #f4f6f9; font-size: 12pt; font-weight: 700; }
QLabel#answersCount { color: #9fcaf0; background: #214e78; border-radius: 9px; padding: 2px 7px; font-size: 9pt; font-weight: 650; }
QLabel#answersHint { color: #7f8997; font-size: 9pt; }
QLabel#answersSectionLabel { color: #8f9aaa; font-size: 9pt; font-weight: 650; }
QListWidget#answerTitlesList { background: transparent; border: none; border-radius: 0; padding: 0; }
QListWidget#answerTitlesList::item { padding: 7px 9px; border-radius: 4px; }
QListWidget#answerTitlesList::item:hover { background: #242a32; }
QListWidget#answerTitlesList::item:selected { background: #214e78; color: #f4f8fc; }
QTextEdit#answerText { background: #1b1e23; border: 1px solid #303640; border-radius: 7px; padding: 10px; selection-background-color: #2f72b7; }
"""
