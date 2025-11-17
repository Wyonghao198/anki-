import os
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, tooltip
from anki.notes import Note
import codecs
import re


class DeckSelectionDialog(QDialog):
    """牌组选择对话框，按层级结构显示牌组"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_deck = None
        self.setup_ui()
        self.load_decks()

    def setup_ui(self):
        self.setWindowTitle("选择牌组")
        self.setMinimumSize(400, 500)

        layout = QVBoxLayout(self)

        # 搜索框
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索牌组...")
        self.search_box.textChanged.connect(self.filter_decks)
        layout.addWidget(QLabel("搜索牌组:"))
        layout.addWidget(self.search_box)

        # 牌组树形视图
        layout.addWidget(QLabel("选择牌组:"))
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["牌组名称"])
        self.tree_widget.itemDoubleClicked.connect(self.accept_selection)
        layout.addWidget(self.tree_widget)

        # 按钮
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("确定")
        self.ok_button.clicked.connect(self.accept_selection)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def load_decks(self):
        """加载所有牌组并按层级结构显示"""
        self.tree_widget.clear()

        # 获取所有牌组
        all_decks = mw.col.decks.all()

        # 创建根节点和层级结构
        root_decks = {}  # 存储根级牌组
        child_decks = {}  # 存储子牌组，按父牌组分组

        # 首先分离根级牌组和子牌组
        for deck in all_decks:
            deck_name = deck['name']

            if "::" in deck_name:
                # 子牌组
                parts = deck_name.split("::")
                parent_name = parts[0]

                if parent_name not in child_decks:
                    child_decks[parent_name] = []

                child_decks[parent_name].append({
                    'name': deck_name,
                    'display_name': "::".join(parts[1:]),
                    'id': deck['id']
                })
            else:
                # 根级牌组
                root_decks[deck_name] = {
                    'name': deck_name,
                    'id': deck['id']
                }

        # 按字母顺序排序根级牌组
        sorted_root_decks = sorted(root_decks.keys())

        # 创建树形结构
        for deck_name in sorted_root_decks:
            deck_info = root_decks[deck_name]

            # 创建父牌组项
            parent_item = QTreeWidgetItem([deck_name])
            parent_item.deck_name = deck_info['name']
            parent_item.deck_id = deck_info['id']
            self.tree_widget.addTopLevelItem(parent_item)

            # 如果有子牌组，添加到父牌组下
            if deck_name in child_decks:
                # 按字母顺序排序子牌组
                sorted_children = sorted(child_decks[deck_name], key=lambda x: x['display_name'])

                for child_info in sorted_children:
                    child_item = QTreeWidgetItem([child_info['display_name']])
                    child_item.deck_name = child_info['name']
                    child_item.deck_id = child_info['id']
                    parent_item.addChild(child_item)

        # 默认展开所有节点
        self.tree_widget.expandAll()

    def filter_decks(self, text):
        """根据搜索文本过滤牌组"""
        if not text:
            # 如果搜索框为空，显示所有牌组
            for i in range(self.tree_widget.topLevelItemCount()):
                item = self.tree_widget.topLevelItem(i)
                self.set_item_visible(item, True)
            return

        search_text = text.lower()

        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            self.filter_item(item, search_text)

    def filter_item(self, item, search_text):
        """递归过滤树形项目"""
        item_text = item.text(0).lower()
        matches = search_text in item_text

        # 检查子项目是否匹配
        child_matches = False
        for i in range(item.childCount()):
            child = item.child(i)
            if self.filter_item(child, search_text):
                child_matches = True

        # 如果本项目或任何子项目匹配，则显示
        visible = matches or child_matches
        item.setHidden(not visible)

        # 如果匹配，展开父项目
        if matches or child_matches:
            parent = item.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()

        return visible

    def set_item_visible(self, item, visible):
        """递归设置项目可见性"""
        item.setHidden(not visible)
        for i in range(item.childCount()):
            child = item.child(i)
            self.set_item_visible(child, visible)

    def accept_selection(self):
        """接受当前选择的牌组"""
        current_item = self.tree_widget.currentItem()
        if current_item and hasattr(current_item, 'deck_name'):
            self.selected_deck = current_item.deck_name
            self.accept()
        else:
            showInfo("请选择一个牌组")


def bulk_import_flashcards():
    """批量导入基于#flashcard分隔符的文本文件"""

    # 获取文件路径
    file_path, _ = QFileDialog.getOpenFileName(
        mw, "选择要导入的文本文件", "", "文本文件 (*.txt);;所有文件 (*)"
    )

    if not file_path:
        return

    try:
        # 检测文件编码并读取内容
        content = read_file_with_encoding(file_path)
        if not content:
            showInfo("无法读取文件或文件为空")
            return

        # 解析卡片
        cards = parse_cards_from_content(content)
        if not cards:
            showInfo("未找到任何卡片。请确保使用 #flashcard 作为分隔符")
            return

        # 选择牌组 - 使用新的树形选择对话框
        deck_name = select_deck()
        if not deck_name:
            return

        # 选择笔记类型
        note_type = select_note_type()
        if not note_type:
            return

        # 确认导入
        if not confirm_import(len(cards)):
            return

        # 执行导入
        imported_count = import_cards_to_collection(cards, deck_name, note_type)

        # 显示结果
        showInfo(f"成功导入 {imported_count} 张卡片到牌组 '{deck_name}'")

    except Exception as e:
        showInfo(f"导入过程中发生错误: {str(e)}")


def read_file_with_encoding(file_path):
    """尝试用不同编码读取文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']

    for encoding in encodings:
        try:
            with codecs.open(file_path, 'r', encoding=encoding) as f:
                # 不进行strip()，保留原始格式
                content = f.read()
                if content:
                    return content
        except UnicodeDecodeError:
            continue

    # 如果常见编码都失败，尝试使用系统默认编码
    try:
        with open(file_path, 'r', encoding='latin-1') as f:
            # 不进行strip()，保留原始格式
            return f.read()
    except Exception as e:
        showInfo(f"无法读取文件: {str(e)}")
        return None


def parse_cards_from_content(content):
    """从内容中解析卡片，保留原始格式"""
    # 使用 #flashcard 作为分隔符
    raw_cards = content.split('#flashcard')

    cards = []
    for raw_card in raw_cards:
        # 只去除开头和结尾的空白字符，保留内部的格式
        card_content = raw_card.strip()
        if card_content and not card_content.isspace():
            cards.append(card_content)

    return cards


def select_deck():
    """选择要导入的牌组 - 使用树形对话框"""
    dialog = DeckSelectionDialog(mw)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selected_deck
    return None


def select_note_type():
    """选择笔记类型"""
    note_types = mw.col.models.all()
    note_type_names = [model['name'] for model in note_types]

    # 按名称排序
    note_type_names.sort()

    # 优先选择 Basic 类型
    default_index = 0
    for i, name in enumerate(note_type_names):
        if "basic" in name.lower():
            default_index = i
            break

    selected_note_type, ok = QInputDialog.getItem(
        mw, "选择笔记类型", "请选择笔记类型:", note_type_names, default_index, False
    )

    if ok and selected_note_type:
        return selected_note_type
    return None


def confirm_import(card_count):
    """确认导入对话框"""
    reply = QMessageBox.question(
        mw,
        "确认导入",
        f"即将导入 {card_count} 张卡片。是否继续？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes
    )
    return reply == QMessageBox.StandardButton.Yes


def preserve_text_formatting(text):
    """保留文本格式，确保换行符和空格正确显示"""
    # 将换行符转换为HTML换行标签
    text = text.replace('\n', '<br>')

    # 保留连续空格
    text = text.replace('  ', ' &nbsp;')

    # 保留制表符
    text = text.replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')

    return text


def import_cards_to_collection(cards, deck_name, note_type_name):
    """将卡片导入到集合中，保留原始格式"""
    imported_count = 0

    # 获取牌组ID
    deck_id = mw.col.decks.id(deck_name)

    # 获取笔记类型
    note_type = mw.col.models.by_name(note_type_name)
    if not note_type:
        showInfo(f"未找到笔记类型: {note_type_name}")
        return 0

    # 设置牌组使用的笔记类型
    mw.col.decks.select(deck_id)
    mw.col.decks.get(deck_id)['mid'] = note_type['id']

    for card_content in cards:
        try:
            # 创建新笔记
            note = Note(mw.col, note_type)
            note.tags = []  # 可以在这里添加标签

            # 保留文本格式
            formatted_content = preserve_text_formatting(card_content)

            # 根据字段数量分配内容
            fields = note.fields
            if len(fields) >= 2:
                # 如果有多个字段，将内容放在第一个字段，第二个字段留空
                fields[0] = formatted_content
                fields[1] = ""  # 答案字段留空，用户可以后续填写
            else:
                # 如果只有一个字段，使用全部内容
                fields[0] = formatted_content

            note.fields = fields

            # 设置牌组并添加笔记
            note.model()['did'] = deck_id
            mw.col.add_note(note, deck_id)

            imported_count += 1

        except Exception as e:
            print(f"导入卡片时出错: {str(e)}")
            continue

    # 保存更改
    mw.col.save()
    return imported_count


def setup_menu():
    """设置菜单项"""
    action = QAction("批量导入文本卡片", mw)
    action.triggered.connect(bulk_import_flashcards)
    mw.form.menuTools.addAction(action)


# 在Anki启动时安装菜单
setup_menu()