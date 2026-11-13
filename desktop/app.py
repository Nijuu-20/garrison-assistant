import os
import sys
import traceback
from pathlib import Path

def main():
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GarrisonAssistant.Desktop.0.1')
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QLockFile
    from garrison.storage import user_dir
    app=QApplication(sys.argv);app.setApplicationName('GarrisonAssistant');app.setOrganizationName('GarrisonAssistant');app.setQuitOnLastWindowClosed(False)
    lock=QLockFile(str(user_dir()/'app.lock'));lock.setStaleLockTime(30000)
    if not lock.tryLock(100):
        QMessageBox.information(None,'卫戍协议助手','助手已经运行，请通过托盘图标或主窗口快捷键恢复。');return 0
    def exception_hook(tp,value,tb):
        (user_dir()/'last_error.log').write_text(''.join(traceback.format_exception(tp,value,tb)),encoding='utf-8')
        QMessageBox.warning(None,'卫戍协议助手','发生错误：'+str(value)+'\n详细记录已写入本机数据目录。')
    sys.excepthook=exception_hook
    from garrison.ui import MainWindow
    window=MainWindow();window.show()
    return app.exec()

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-check':
        from garrison.diagnostics import run
        raise SystemExit(run(sys.argv[2]))
    raise SystemExit(main())
