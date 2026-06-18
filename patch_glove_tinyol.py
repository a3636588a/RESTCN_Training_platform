from pathlib import Path
import re

root = Path(r"D:\Qt\QT6.6.3\Examples\glove")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing {label}")
    return text.replace(old, new, 1)


def regex_replace(text: str, pattern: str, replacement: str, label: str) -> str:
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"missing {label}")
    return new_text


pro_path = root / "TEST.pro"
pro = read_text(pro_path)
pro = pro.replace("    uartsettingdialog.cpp`r`n    tinyoldialog.cpp", "    uartsettingdialog.cpp\n    tinyoldialog.cpp")
pro = pro.replace("    uartsettingdialog.h`r`n    tinyoldialog.h", "    uartsettingdialog.h\n    tinyoldialog.h")
if "tinyoldialog.cpp" not in pro:
    pro = replace_once(pro, "    uartsettingdialog.cpp", "    uartsettingdialog.cpp\n    tinyoldialog.cpp", "TEST.pro source list")
if "tinyoldialog.h" not in pro:
    pro = replace_once(pro, "    uartsettingdialog.h", "    uartsettingdialog.h\n    tinyoldialog.h", "TEST.pro header list")
write_text(pro_path, pro)

h_path = root / "mainwindow.h"
h = read_text(h_path)
if "#include <QPointer>" not in h:
    h = replace_once(h, "#include <QCheckBox>", "#include <QCheckBox>\n#include <QPointer>", "mainwindow.h pointer include")
if "class TinyOlDialog;" not in h:
    h = regex_replace(h, r"QT_END_NAMESPACE\s*", "QT_END_NAMESPACE\n\nclass TinyOlDialog;\n\n", "mainwindow.h forward decl")
if "serialLineReceived" not in h:
    h = regex_replace(
        h,
        r"public:\s*explicit MainWindow\(QWidget \*parent = nullptr\);\s*~MainWindow\(\);",
        "public:\n    explicit MainWindow(QWidget *parent = nullptr);\n    ~MainWindow();\n\nsignals:\n    void serialLineReceived(const QString &line);",
        "mainwindow.h signal block",
    )
if "onTinyOlCheckboxToggled" not in h:
    h = re.sub(
        r"(?m)^(\s*void on_BTN_UART_SETTING_clicked\(\);\s*)$",
        r"\1    void onTinyOlCheckboxToggled(bool checked);",
        h,
        count=1,
        flags=re.M,
    )
    if "onTinyOlCheckboxToggled" not in h:
        raise RuntimeError("missing mainwindow.h tinyol slot")
if "updateTinyOlConnectionState" not in h:
    h = re.sub(
        r"(?m)^(\s*void appendLog\(const QString &s\);\s*)$",
        r"\1    void updateTinyOlConnectionState();",
        h,
        count=1,
        flags=re.M,
    )
    if "updateTinyOlConnectionState" not in h:
        raise RuntimeError("missing mainwindow.h tinyol helper")
if "tinyolBox_" not in h:
    h = re.sub(
        r"(?ms)(\s*QCheckBox \*sumBox_ = nullptr;\s*QCheckBox \*chBox_\[6\] = \{nullptr, nullptr, nullptr, nullptr, nullptr, nullptr\};)",
        r"\1    QCheckBox *chBox_[6] = {nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};\n    QCheckBox *tinyolBox_ = nullptr;\n    QPointer<TinyOlDialog> tinyolDialog_;",
        h,
        count=1,
    )
    if "tinyolBox_" not in h:
        raise RuntimeError("missing mainwindow.h tinyol members")
write_text(h_path, h)

cpp_path = root / "mainwindow.cpp"
cpp = read_text(cpp_path)
if '#include "tinyoldialog.h"' not in cpp:
    cpp = replace_once(
        cpp,
        '#include "uartsettingdialog.h"',
        '#include "uartsettingdialog.h"\n#include "tinyoldialog.h"',
        "mainwindow.cpp tinyol include",
    )
if "emit serialLineReceived" not in cpp:
    cpp = cpp.replace(
        "    const QString s = QString::fromLatin1(line).trimmed();\n    if (s.isEmpty())\n      continue;",
        "    const QString s = QString::fromLatin1(line).trimmed();\n    if (s.isEmpty())\n      continue;\n    emit serialLineReceived(s);",
        1,
    )
    if "emit serialLineReceived" not in cpp:
        cpp = cpp.replace(
            "    const QString s = QString::fromLatin1(line).trimmed();\r\n    if (s.isEmpty())\r\n      continue;",
            "    const QString s = QString::fromLatin1(line).trimmed();\r\n    if (s.isEmpty())\r\n      continue;\r\n    emit serialLineReceived(s);",
            1,
        )
    if "emit serialLineReceived" not in cpp:
        raise RuntimeError("missing mainwindow.cpp emit line")

tinyol_methods = """

void MainWindow::onTinyOlCheckboxToggled(bool checked)
{
    if (!tinyolBox_) {
        return;
    }

    if (checked) {
        if (!tinyolDialog_) {
            tinyolDialog_ = new TinyOlDialog(&serial_, this);
            connect(this, &MainWindow::serialLineReceived, tinyolDialog_, &TinyOlDialog::handleSerialLine);
            connect(tinyolDialog_, &TinyOlDialog::requestUncheck, this, [this] {
                if (tinyolBox_) {
                    tinyolBox_->blockSignals(true);
                    tinyolBox_->setChecked(false);
                    tinyolBox_->blockSignals(false);
                }
            });
        }

        updateTinyOlConnectionState();
        tinyolDialog_->show();
        tinyolDialog_->raise();
        tinyolDialog_->activateWindow();
        return;
    }

    if (tinyolDialog_) {
        tinyolDialog_->close();
    }
}

void MainWindow::updateTinyOlConnectionState()
{
    if (!tinyolDialog_) {
        return;
    }

    QString portName = serial_.portName();
    if (portName.isEmpty()) {
        portName = uartCfg_.portName;
        if (portName.isEmpty()) {
            portName = ui->CB_COMPORT->currentData().toString();
            if (portName.isEmpty()) {
                portName = ui->CB_COMPORT->currentText();
            }
        }
    }

    tinyolDialog_->setConnectionInfo(portName, serial_.baudRate(), serial_.isOpen());
}
""".lstrip("\n")
if "onTinyOlCheckboxToggled" not in cpp:
    cpp = regex_replace(
        cpp,
        r"void MainWindow::on_CKB_SUM_toggled\(bool /\*checked\*/\) \{",
        tinyol_methods + "\nvoid MainWindow::on_CKB_SUM_toggled(bool /*checked*/) {",
        "mainwindow.cpp tinyol methods",
    )
if "CKB_TINYOL" not in cpp:
    cpp = replace_once(
        cpp,
        "  ui->textEdit_LOG->document()->setMaximumBlockCount(2000); // 你可改 5000/10000",
        '  tinyolBox_ = new QCheckBox(QStringLiteral("TinyOL"), this);\n'
        '  tinyolBox_->setObjectName(QStringLiteral("CKB_TINYOL"));\n'
        '  if (ui->gridLayout_4) {\n'
        '    ui->gridLayout_4->addWidget(tinyolBox_, 6, 0, 1, 2);\n'
        "  }\n"
        "  connect(tinyolBox_, &QCheckBox::toggled, this, &MainWindow::onTinyOlCheckboxToggled);\n"
        "  ui->textEdit_LOG->document()->setMaximumBlockCount(2000); // 你可改 5000/10000",
        "mainwindow.cpp tinyol checkbox",
    )

connected_old = """    appendLog(tr(\"Connected: %1, %2 bps\").arg(portName).arg(serial_.baudRate()));
    statusBar()->showMessage(tr(\"Connected: %1\").arg(portName), 2000);
    startCsvRecording();"""
connected_new = """    appendLog(tr(\"Connected: %1, %2 bps\").arg(portName).arg(serial_.baudRate()));
    statusBar()->showMessage(tr(\"Connected: %1\").arg(portName), 2000);
    updateTinyOlConnectionState();
    startCsvRecording();"""
if connected_old in cpp:
    cpp = cpp.replace(connected_old, connected_new, 1)

disconnect_old = """        stopCsvRecording();
        if (sumBox_) sumBox_->setEnabled(true);
        updateSumPlotsVisibility();"""
disconnect_new = """        stopCsvRecording();
        if (sumBox_) sumBox_->setEnabled(true);
        updateSumPlotsVisibility();
        updateTinyOlConnectionState();"""
if disconnect_old in cpp:
    cpp = cpp.replace(disconnect_old, disconnect_new, 1)

serial_err_old = """        if (serial_.isOpen()) {
            suppressErrorOnClose_ = true;
            serial_.close();
            suppressErrorOnClose_ = false;
        }
        ui->BTN_CONNECT->setText(QStringLiteral(\"???\"));"""
serial_err_new = """        if (serial_.isOpen()) {
            suppressErrorOnClose_ = true;
            serial_.close();
            suppressErrorOnClose_ = false;
        }
        ui->BTN_CONNECT->setText(QStringLiteral(\"???\"));
        updateTinyOlConnectionState();"""
if serial_err_old in cpp:
    cpp = cpp.replace(serial_err_old, serial_err_new, 1)

cpp = cpp.replace("}void MainWindow::on_CKB_SUM_toggled(bool /*checked*/) {", "}\n\nvoid MainWindow::on_CKB_SUM_toggled(bool /*checked*/) {")
write_text(cpp_path, cpp)

print("glove TinyOL patch applied")
