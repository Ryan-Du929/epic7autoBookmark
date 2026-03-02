import os
import sys
import json
import random
from PyQt6 import QtCore, QtGui, QtWidgets
from adbutils import adb, AdbDevice
from numpy import asarray
import aircv

# ==========================================
# 1. 資源路徑處理
# ==========================================

def resource_path(relative_path):
    """ 取得資源的絕對路徑 (用於內建圖片、Icon) """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ==========================================
# 2. Worker 執行緒 (強化統計與回報邏輯)
# ==========================================

class worker(QtCore.QThread):
    isStart = QtCore.pyqtSignal()
    isFinish = QtCore.pyqtSignal(str) # 改為傳回結算字串
    isError = QtCore.pyqtSignal(str)
    emitLog = QtCore.pyqtSignal(str)
    emitMoney = QtCore.pyqtSignal(str)
    emitStone = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.reset_stats()

    def reset_stats(self):
        """ 重置統計數據 """
        self.refreshTime = 0
        self.covenantFoundCount = 0
        self.mysticFoundCount = 0
        self.totalMoneySpent = 0

    def setVariable(self, startMode, expectNum, moneyNum, stoneNum, config):
        self.startMode = startMode
        self.expectNum = expectNum
        self.moneyNum = moneyNum
        self.stoneNum = stoneNum
        self.config = config
        self.reset_stats()

    def handle_buy_button(self, device, buyButton, money_cost, type_name):
        QtCore.QThread.msleep(1200) # 等待視窗動畫
        buy_screenshot = asarray(device.screenshot())
        buyLoc = aircv.find_template(buy_screenshot, buyButton, 0.8)
        
        if buyLoc:
            res = buyLoc["result"]
            device.click(res[0], res[1]) # 使用單擊減少延遲
            QtCore.QThread.msleep(800)
            
            self.moneyNum -= money_cost
            self.totalMoneySpent += money_cost
            self.emitMoney.emit(str(self.moneyNum))
            
            if type_name == "聖約": self.covenantFoundCount += 1
            else: self.mysticFoundCount += 1

            if self.startMode in [1, 2]:
                self.expectNum -= 1
            
            self.emitLog.emit(f"✅ 買入【{type_name}】，累計: 聖約x{self.covenantFoundCount}, 神秘x{self.mysticFoundCount}")
            return True
        return False

    def handle_refresh_button(self, device, refreshButton, refreshYesButton):
        screenshot = asarray(device.screenshot())
        refreshLoc = aircv.find_template(screenshot, refreshButton, 0.9)
        if refreshLoc:
            res = refreshLoc["result"]
            device.click(res[0], res[1])
            QtCore.QThread.msleep(800)
            
            confirm_screenshot = asarray(device.screenshot())
            yesLoc = aircv.find_template(confirm_screenshot, refreshYesButton, 0.9)
            if yesLoc:
                device.click(yesLoc["result"][0], yesLoc["result"][1])
                self.stoneNum -= 3
                self.refreshTime += 1
                self.emitStone.emit(str(self.stoneNum))
                
                if self.startMode == 3:
                    self.expectNum -= 3
                
                self.emitLog.emit(f"🔄 第 {self.refreshTime} 次更新商店...")
                return True
        return False

    def run(self):
        self.isStart.emit()
        try:
            adb_addr = self.config.get("adb_addr", "127.0.0.1:5555")
            e7_lang = self.config.get("e7_language", "tw")
            
            adb.connect(adb_addr, timeout=10)
            device = adb.device(serial=adb_addr)
            
            covenant_img = aircv.imread(resource_path("img/covenantLocation.png"))
            mystic_img = aircv.imread(resource_path("img/mysticLocation.png"))
            buy_img = aircv.imread(resource_path(f"img/buyButton-{e7_lang}.png"))
            re_img = aircv.imread(resource_path(f"img/refreshButton-{e7_lang}.png"))
            re_yes_img = aircv.imread(resource_path(f"img/refreshYesButton-{e7_lang}.png"))

            needRefresh = False

            while self.expectNum > 0 and self.moneyNum > 280000 and self.stoneNum >= 3:
                screenshot = asarray(device.screenshot())
                
                # 檢查聖約
                if aircv.find_template(screenshot, covenant_img, 0.9):
                    loc = aircv.find_template(screenshot, covenant_img, 0.9)["result"]
                    device.click(loc[0] + 800, loc[1] + 40)
                    self.handle_buy_button(device, buy_img, 184000, "聖約")

                # 檢查神秘
                screenshot = asarray(device.screenshot())
                if aircv.find_template(screenshot, mystic_img, 0.9):
                    loc = aircv.find_template(screenshot, mystic_img, 0.9)["result"]
                    device.click(loc[0] + 800, loc[1] + 40)
                    self.handle_buy_button(device, buy_img, 280000, "神秘")

                if needRefresh:
                    if self.handle_refresh_button(device, re_img, re_yes_img):
                        needRefresh = False
                        QtCore.QThread.msleep(1000)
                else:
                    device.swipe(1400, 500, 1400, 200, 0.1)
                    needRefresh = True
                    QtCore.QThread.msleep(800)

            # 計算期望值
            total_stones = self.refreshTime * 3
            exp_cov = total_stones / self.covenantFoundCount if self.covenantFoundCount > 0 else 0
            exp_mys = total_stones / self.mysticFoundCount if self.mysticFoundCount > 0 else 0

            summary = (
                f"===== 結算統計 =====\n"
                f"🔹 商店刷新總數: {self.refreshTime} 次\n"
                f"💎 消耗天空石: {total_stones} 個\n"
                f"💰 消耗金幣: {self.totalMoneySpent:,} 元\n"
                f"--------------------\n"
                f"🔖 獲得聖約書籤: {self.covenantFoundCount} 次\n"
                f"🔖 獲得神秘書籤: {self.mysticFoundCount} 次\n"
                f"--------------------\n"
                f"📈 聖約期望值: {exp_cov:.2f} 石/次\n"
                f"📈 神秘期望值: {exp_mys:.2f} 石/次"
            )
            self.isFinish.emit(summary)

        except Exception as e:
            self.isError.emit(str(e))

# ==========================================
# 3. UI 介面
# ==========================================

class Ui_Main(object):
    def setupUi(self, Main):
        Main.setObjectName("Main")
        Main.resize(320, 550)
        font = QtGui.QFont("微軟正黑體", 10)
        Main.setFont(font)

        self.layout = QtWidgets.QVBoxLayout(Main)
        self.tabWidget = QtWidgets.QTabWidget(Main)

        # 功能分頁
        self.functionTab = QtWidgets.QWidget()
        self.fLayout = QtWidgets.QVBoxLayout(self.functionTab)

        # 檔案選取區
        self.pathLayout = QtWidgets.QHBoxLayout()
        self.configPathEdit = QtWidgets.QLineEdit()
        self.configPathEdit.setPlaceholderText("請選取 config.json")
        self.configPathEdit.setReadOnly(True)
        self.btnSelectFile = QtWidgets.QPushButton("選取設定檔")
        self.btnSelectFile.clicked.connect(self.selectConfigFile)
        self.pathLayout.addWidget(self.configPathEdit)
        self.pathLayout.addWidget(self.btnSelectFile)
        self.fLayout.addLayout(self.pathLayout)

        # 資源顯示
        self.resLayout = QtWidgets.QGridLayout()
        self.resLayout.addWidget(QtWidgets.QLabel("金幣:"), 0, 0)
        self.moneyEdit = QtWidgets.QLineEdit("0")
        self.resLayout.addWidget(self.moneyEdit, 0, 1)
        self.resLayout.addWidget(QtWidgets.QLabel("天空石:"), 1, 0)
        self.stoneEdit = QtWidgets.QLineEdit("0")
        self.resLayout.addWidget(self.stoneEdit, 1, 1)
        self.fLayout.addLayout(self.resLayout)

        # 停止條件
        self.stopGroupBox = QtWidgets.QGroupBox("停止條件")
        self.sLayout = QtWidgets.QVBoxLayout(self.stopGroupBox)
        self.radioCov = QtWidgets.QRadioButton("達到聖約次數")
        self.radioCov.setChecked(True)
        self.inputCov = QtWidgets.QLineEdit("0")
        self.radioMys = QtWidgets.QRadioButton("達到神秘次數")
        self.inputMys = QtWidgets.QLineEdit("0")
        self.radioStone = QtWidgets.QRadioButton("消耗天空石數量")
        self.inputStone = QtWidgets.QLineEdit("0")
        self.sLayout.addWidget(self.radioCov)
        self.sLayout.addWidget(self.inputCov)
        self.sLayout.addWidget(self.radioMys)
        self.sLayout.addWidget(self.inputMys)
        self.sLayout.addWidget(self.radioStone)
        self.sLayout.addWidget(self.inputStone)
        self.fLayout.addWidget(self.stopGroupBox)

        # 日誌
        self.logBox = QtWidgets.QTextBrowser()
        self.fLayout.addWidget(self.logBox)

        # 按鈕
        self.btnStart = QtWidgets.QPushButton("開始執行")
        self.btnStart.setMinimumHeight(40)
        self.btnStart.clicked.connect(self.toggleStart)
        self.fLayout.addWidget(self.btnStart)

        self.tabWidget.addTab(self.functionTab, "功能")

        # 說明頁面
        self.introTab = QtWidgets.QTextBrowser()
        self.introTab.setHtml("""
            <h3>使用說明</h3>
            <ul>
                <li><b>第一步：</b>選取正確的 <code>config.json</code>，內含 ADB 位址。</li>
                <li><b>第二步：</b>輸入當前遊戲中的金幣與天空石餘額。</li>
                <li><b>第三步：</b>選擇要停止的條件（例如刷到 10 次聖約後停止）。</li>
            </ul>
            <p>期望值計算公式：$$E = \\frac{\\text{總消耗天空石}}{\\text{獲得書籤次數}}$$</p>
            <p><i>注意：請確保模擬器解析度符合圖片規格。</i></p>
        """)
        self.tabWidget.addTab(self.introTab, "說明")
        
        self.layout.addWidget(self.tabWidget)

        # 初始化 Worker
        self.worker = worker()
        self.worker.isStart.connect(lambda: self.logBox.append("🚀 啟動腳本..."))
        self.worker.isFinish.connect(self.onFinish)
        self.worker.isError.connect(lambda e: self.logBox.append(f"❌ 錯誤: {e}"))
        self.worker.emitLog.connect(lambda t: self.logBox.append(t))
        self.worker.emitMoney.connect(lambda v: self.moneyEdit.setText(v))
        self.worker.emitStone.connect(lambda v: self.stoneEdit.setText(v))

        self.running = False
        self.currentConfig = None

    def selectConfigFile(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(None, "選取設定檔", "", "JSON Files (*.json)")
        if file_path:
            self.configPathEdit.setText(file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                self.currentConfig = json.load(f)
            self.logBox.append(f"📂 已載入設定: {os.path.basename(file_path)}")

    def toggleStart(self):
        if not self.running:
            if not self.currentConfig:
                self.logBox.append("⚠️ 請先選取 config.json 檔案！")
                return
            
            mode = 1 if self.radioCov.isChecked() else (2 if self.radioMys.isChecked() else 3)
            num = int(self.inputCov.text()) if mode==1 else (int(self.inputMys.text()) if mode==2 else int(self.inputStone.text()))
            
            self.worker.setVariable(
                mode, num, 
                int(self.moneyEdit.text()), 
                int(self.stoneEdit.text()),
                self.currentConfig
            )
            self.worker.start()
            self.btnStart.setText("停止執行")
            self.running = True
        else:
            self.worker.terminate()
            self.onFinish("🛑 使用者手動停止執行")

    def onFinish(self, msg):
        self.logBox.append("\n" + msg)
        self.btnStart.setText("開始執行")
        self.running = False

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(resource_path("main.ico")))
    window = QtWidgets.QWidget()
    ui = Ui_Main()
    ui.setupUi(window)
    window.show()
    sys.exit(app.exec())