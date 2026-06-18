$ErrorActionPreference = 'Stop'

$root = 'D:\Qt\QT6.6.3\Examples\glove'
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Read-All([string]$Path) {
    [System.IO.File]::ReadAllText($Path, $utf8)
}

function Write-All([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

$tinyolH = @'
#ifndef TINYOLDIALOG_H
#define TINYOLDIALOG_H

#include <QDialog>
#include <QPointer>
#include <QSerialPort>

class QLabel;
class QTextEdit;
class QComboBox;
class QSpinBox;
class QDoubleSpinBox;
class QCloseEvent;

class TinyOlDialog : public QDialog
{
    Q_OBJECT

public:
    explicit TinyOlDialog(QSerialPort *serial, QWidget *parent = nullptr);
    void setConnectionInfo(const QString &portName, int baudRate, bool connected);

signals:
    void requestUncheck();

public slots:
    void handleSerialLine(const QString &line);

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void onEnterTinyOl();
    void onGetInfo();
    void onGetLabels();
    void onGetActiveHead();
    void onUseCurrentBaseHold();
    void onRecalibrate();
    void onCreateSession();
    void onRequestRecord();
    void onStartRecord();
    void onStopRecord();
    void onBuildReplay();
    void onRunOl();
    void onRunValidation();
    void onGetResult();
    void onApplyHead();
    void onRollbackHead();
    void onBackToCnn();

private:
    void appendLog(const QString &msg);
    bool ensureConnected();
    void sendLine(const QString &coreOrFullLine);
    QWidget *buildStepBox(const QString &title, const QList<QWidget *> &widgets);

private:
    QPointer<QSerialPort> serial_;
    QLabel *labelPort_ = nullptr;
    QLabel *labelBaud_ = nullptr;
    QLabel *labelState_ = nullptr;
    QLabel *labelLastAck_ = nullptr;
    QTextEdit *textLog_ = nullptr;
    QComboBox *comboTargetLabel_ = nullptr;
    QSpinBox *spinEpochs_ = nullptr;
    QSpinBox *spinCaptureCount_ = nullptr;
    QSpinBox *spinRecordSamples_ = nullptr;
    QSpinBox *spinWindowOffset_ = nullptr;
    QSpinBox *spinBatchSize_ = nullptr;
    QDoubleSpinBox *spinLearningRate_ = nullptr;
    QSpinBox *spinConfusableCount_ = nullptr;
    QSpinBox *spinConfusableWindows_ = nullptr;
    QSpinBox *spinAnchorWindows_ = nullptr;
};

#endif // TINYOLDIALOG_H
'@

$tinyolCpp = @'
#include "tinyoldialog.h"

#include <QCloseEvent>
#include <QComboBox>
#include <QDateTime>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QSerialPort>
#include <QSpinBox>
#include <QTextEdit>
#include <QVBoxLayout>

namespace {
QString ensurePacket(QString text)
{
    QString out = text.trimmed();
    if (!out.startsWith('$')) {
        out.prepend('$');
    }
    if (!out.endsWith("\r\n")) {
        out += "\r\n";
    }
    return out;
}
}

TinyOlDialog::TinyOlDialog(QSerialPort *serial, QWidget *parent)
    : QDialog(parent)
    , serial_(serial)
{
    setWindowTitle(QStringLiteral("TinyOL"));
    resize(980, 760);
    setAttribute(Qt::WA_DeleteOnClose, true);

    auto *root = new QVBoxLayout(this);

    auto *connBox = new QGroupBox(QStringLiteral("Shared UART"), this);
    auto *connGrid = new QGridLayout(connBox);
    labelPort_ = new QLabel(QStringLiteral("--"), connBox);
    labelBaud_ = new QLabel(QStringLiteral("--"), connBox);
    labelState_ = new QLabel(QStringLiteral("Disconnected"), connBox);
    labelLastAck_ = new QLabel(QStringLiteral("--"), connBox);
    connGrid->addWidget(new QLabel(QStringLiteral("Port:"), connBox), 0, 0);
    connGrid->addWidget(labelPort_, 0, 1);
    connGrid->addWidget(new QLabel(QStringLiteral("Baud:"), connBox), 0, 2);
    connGrid->addWidget(labelBaud_, 0, 3);
    connGrid->addWidget(new QLabel(QStringLiteral("State:"), connBox), 1, 0);
    connGrid->addWidget(labelState_, 1, 1);
    connGrid->addWidget(new QLabel(QStringLiteral("Last Ack:"), connBox), 1, 2);
    connGrid->addWidget(labelLastAck_, 1, 3);
    root->addWidget(connBox);

    comboTargetLabel_ = new QComboBox(this);
    for (int i = 0; i <= 15; ++i) {
        comboTargetLabel_->addItem(QString::number(i), i);
    }

    spinEpochs_ = new QSpinBox(this);
    spinEpochs_->setRange(1, 500);
    spinEpochs_->setValue(8);

    spinCaptureCount_ = new QSpinBox(this);
    spinCaptureCount_->setRange(1, 200);
    spinCaptureCount_->setValue(5);

    spinRecordSamples_ = new QSpinBox(this);
    spinRecordSamples_->setRange(1, 1000);
    spinRecordSamples_->setValue(150);

    spinWindowOffset_ = new QSpinBox(this);
    spinWindowOffset_->setRange(0, 500);
    spinWindowOffset_->setValue(30);

    spinBatchSize_ = new QSpinBox(this);
    spinBatchSize_->setRange(1, 64);
    spinBatchSize_->setValue(4);

    spinLearningRate_ = new QDoubleSpinBox(this);
    spinLearningRate_->setDecimals(6);
    spinLearningRate_->setRange(0.000001, 1.0);
    spinLearningRate_->setSingleStep(0.0001);
    spinLearningRate_->setValue(0.0005);

    spinConfusableCount_ = new QSpinBox(this);
    spinConfusableCount_->setRange(0, 10);
    spinConfusableCount_->setValue(3);

    spinConfusableWindows_ = new QSpinBox(this);
    spinConfusableWindows_->setRange(0, 100);
    spinConfusableWindows_->setValue(8);

    spinAnchorWindows_ = new QSpinBox(this);
    spinAnchorWindows_->setRange(0, 100);
    spinAnchorWindows_->setValue(2);

    auto *step1 = buildStepBox(QStringLiteral("Step 1 - Enter TinyOL"), {
        new QLabel(QStringLiteral("切到 TinyOL mode，進入這個專用流程。"), this),
        new QPushButton(QStringLiteral("Enter TinyOL Mode"), this)
    });
    connect(step1->findChild<QPushButton *>(), &QPushButton::clicked, this, &TinyOlDialog::onEnterTinyOl);

    auto *step2 = buildStepBox(QStringLiteral("Step 2 - Read Info"), {
        new QLabel(QStringLiteral("先讀 TinyOL 能力、label table、active head。"), this),
        new QPushButton(QStringLiteral("Get TinyOL Info"), this),
        new QPushButton(QStringLiteral("Get Label Table"), this),
        new QPushButton(QStringLiteral("Get Active Head Info"), this)
    });
    {
        auto buttons = step2->findChildren<QPushButton *>();
        connect(buttons.at(0), &QPushButton::clicked, this, &TinyOlDialog::onGetInfo);
        connect(buttons.at(1), &QPushButton::clicked, this, &TinyOlDialog::onGetLabels);
        connect(buttons.at(2), &QPushButton::clicked, this, &TinyOlDialog::onGetActiveHead);
    }

    auto *step3Box = new QGroupBox(QStringLiteral("Step 3 - Calibration"), this);
    auto *step3Layout = new QVBoxLayout(step3Box);
    step3Layout->addWidget(new QLabel(QStringLiteral("base / hold 可沿用目前值，或在 TinyOL 內重校。"), step3Box));
    auto *step3Btns = new QHBoxLayout();
    auto *btnUseBase = new QPushButton(QStringLiteral("Use Current Base/Hold"), step3Box);
    auto *btnRecal = new QPushButton(QStringLiteral("Re-Calibrate Base/Hold"), step3Box);
    step3Btns->addWidget(btnUseBase);
    step3Btns->addWidget(btnRecal);
    step3Layout->addLayout(step3Btns);
    connect(btnUseBase, &QPushButton::clicked, this, &TinyOlDialog::onUseCurrentBaseHold);
    connect(btnRecal, &QPushButton::clicked, this, &TinyOlDialog::onRecalibrate);

    auto *step4Box = new QGroupBox(QStringLiteral("Step 4 - Session Config"), this);
    auto *step4Layout = new QFormLayout(step4Box);
    step4Layout->addRow(QStringLiteral("Target Label"), comboTargetLabel_);
    step4Layout->addRow(QStringLiteral("Epochs"), spinEpochs_);
    step4Layout->addRow(QStringLiteral("Capture Count"), spinCaptureCount_);
    step4Layout->addRow(QStringLiteral("Record Samples"), spinRecordSamples_);
    step4Layout->addRow(QStringLiteral("Window Start Offset"), spinWindowOffset_);
    step4Layout->addRow(QStringLiteral("Batch Size"), spinBatchSize_);
    step4Layout->addRow(QStringLiteral("Learning Rate"), spinLearningRate_);
    step4Layout->addRow(QStringLiteral("Confusable Count"), spinConfusableCount_);
    step4Layout->addRow(QStringLiteral("Confusable Windows/Class"), spinConfusableWindows_);
    step4Layout->addRow(QStringLiteral("Anchor Windows/Class"), spinAnchorWindows_);
    auto *btnCreateSession = new QPushButton(QStringLiteral("Create Session"), step4Box);
    step4Layout->addRow(btnCreateSession);
    connect(btnCreateSession, &QPushButton::clicked, this, &TinyOlDialog::onCreateSession);

    auto *step5 = buildStepBox(QStringLiteral("Step 5 - Recording"), {
        new QLabel(QStringLiteral("由 MCU 發起錄製請求，PC 再送 Start / Stop。"), this),
        new QPushButton(QStringLiteral("Request Record"), this),
        new QPushButton(QStringLiteral("Start Record"), this),
        new QPushButton(QStringLiteral("Stop Record"), this)
    });
    {
        auto buttons = step5->findChildren<QPushButton *>();
        connect(buttons.at(0), &QPushButton::clicked, this, &TinyOlDialog::onRequestRecord);
        connect(buttons.at(1), &QPushButton::clicked, this, &TinyOlDialog::onStartRecord);
        connect(buttons.at(2), &QPushButton::clicked, this, &TinyOlDialog::onStopRecord);
    }

    auto *step6 = buildStepBox(QStringLiteral("Step 6 - Replay"), {
        new QLabel(QStringLiteral("建立 target / confusable / anchor replay。"), this),
        new QPushButton(QStringLiteral("Build Replay"), this)
    });
    connect(step6->findChild<QPushButton *>(), &QPushButton::clicked, this, &TinyOlDialog::onBuildReplay);

    auto *step7 = buildStepBox(QStringLiteral("Step 7 - Train / Validate"), {
        new QLabel(QStringLiteral("執行 head-only OL，並讀 validation / result。"), this),
        new QPushButton(QStringLiteral("Run OL"), this),
        new QPushButton(QStringLiteral("Run Validation"), this),
        new QPushButton(QStringLiteral("Get Result"), this)
    });
    {
        auto buttons = step7->findChildren<QPushButton *>();
        connect(buttons.at(0), &QPushButton::clicked, this, &TinyOlDialog::onRunOl);
        connect(buttons.at(1), &QPushButton::clicked, this, &TinyOlDialog::onRunValidation);
        connect(buttons.at(2), &QPushButton::clicked, this, &TinyOlDialog::onGetResult);
    }

    auto *step8 = buildStepBox(QStringLiteral("Step 8 - Apply / Rollback / Exit"), {
        new QLabel(QStringLiteral("訓練完成後套用 active head，需要時 rollback，再切回 CNN。"), this),
        new QPushButton(QStringLiteral("Apply Active Head"), this),
        new QPushButton(QStringLiteral("Rollback Head"), this),
        new QPushButton(QStringLiteral("Back To CNN Mode"), this)
    });
    {
        auto buttons = step8->findChildren<QPushButton *>();
        connect(buttons.at(0), &QPushButton::clicked, this, &TinyOlDialog::onApplyHead);
        connect(buttons.at(1), &QPushButton::clicked, this, &TinyOlDialog::onRollbackHead);
        connect(buttons.at(2), &QPushButton::clicked, this, &TinyOlDialog::onBackToCnn);
    }

    root->addWidget(step1);
    root->addWidget(step2);
    root->addWidget(step3Box);
    root->addWidget(step4Box);
    root->addWidget(step5);
    root->addWidget(step6);
    root->addWidget(step7);
    root->addWidget(step8);

    auto *logBox = new QGroupBox(QStringLiteral("TinyOL UART Log"), this);
    auto *logLayout = new QVBoxLayout(logBox);
    textLog_ = new QTextEdit(logBox);
    textLog_->setReadOnly(true);
    logLayout->addWidget(textLog_);
    root->addWidget(logBox, 1);
}

void TinyOlDialog::setConnectionInfo(const QString &portName, int baudRate, bool connected)
{
    labelPort_->setText(portName.isEmpty() ? QStringLiteral("--") : portName);
    labelBaud_->setText(baudRate > 0 ? QString::number(baudRate) : QStringLiteral("--"));
    labelState_->setText(connected ? QStringLiteral("Connected") : QStringLiteral("Disconnected"));
}

void TinyOlDialog::handleSerialLine(const QString &line)
{
    if (line.startsWith("$SILOL") || line.startsWith("$SILAPP") || line.startsWith("$ACK") || line.startsWith("$NACK")) {
        appendLog(QStringLiteral("[RX] %1").arg(line));
        labelLastAck_->setText(line.left(80));
    }
}

void TinyOlDialog::closeEvent(QCloseEvent *event)
{
    emit requestUncheck();
    QDialog::closeEvent(event);
}

void TinyOlDialog::appendLog(const QString &msg)
{
    const QString stamp = QDateTime::currentDateTime().toString("HH:mm:ss");
    textLog_->append(QStringLiteral("[%1] %2").arg(stamp, msg));
}

bool TinyOlDialog::ensureConnected()
{
    if (!serial_ || !serial_->isOpen()) {
        QMessageBox::warning(this, QStringLiteral("TinyOL"), QStringLiteral("目前沒有共用中的 COM 連線。"));
        return false;
    }
    return true;
}

void TinyOlDialog::sendLine(const QString &coreOrFullLine)
{
    if (!ensureConnected()) {
        return;
    }
    const QString packet = ensurePacket(coreOrFullLine);
    if (serial_->write(packet.toLatin1()) == -1) {
        appendLog(QStringLiteral("[TX ERROR] %1").arg(serial_->errorString()));
        return;
    }
    appendLog(QStringLiteral("[TX] %1").arg(packet.trimmed()));
}

QWidget *TinyOlDialog::buildStepBox(const QString &title, const QList<QWidget *> &widgets)
{
    auto *box = new QGroupBox(title, this);
    auto *layout = new QVBoxLayout(box);
    for (QWidget *w : widgets) {
        layout->addWidget(w);
    }
    return box;
}

void TinyOlDialog::onEnterTinyOl() { sendLine("$SILAPP,TINYOL"); }
void TinyOlDialog::onGetInfo() { sendLine("$SILOLINFO?"); }
void TinyOlDialog::onGetLabels() { sendLine("$SILOLLABELS?"); }
void TinyOlDialog::onGetActiveHead() { sendLine("$SILOLHEAD?"); }
void TinyOlDialog::onUseCurrentBaseHold() { sendLine("$SILOLCAL,USE_CURRENT"); }
void TinyOlDialog::onRecalibrate() { sendLine("$SILOLCAL,RECAL"); }

void TinyOlDialog::onCreateSession()
{
    const int target = comboTargetLabel_->currentData().toInt();
    const QString cmd = QString("$SILOLCFG,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10")
                            .arg(target)
                            .arg(spinEpochs_->value())
                            .arg(spinCaptureCount_->value())
                            .arg(spinRecordSamples_->value())
                            .arg(spinWindowOffset_->value())
                            .arg(spinBatchSize_->value())
                            .arg(spinLearningRate_->value(), 0, 'f', 6)
                            .arg(spinConfusableCount_->value())
                            .arg(spinConfusableWindows_->value())
                            .arg(spinAnchorWindows_->value());
    sendLine(cmd);
}

void TinyOlDialog::onRequestRecord() { sendLine("$SILOLREC,REQ"); }
void TinyOlDialog::onStartRecord() { sendLine("$SILOLREC,START"); }
void TinyOlDialog::onStopRecord() { sendLine("$SILOLREC,STOP"); }
void TinyOlDialog::onBuildReplay() { sendLine("$SILOLREPLAY,BUILD"); }
void TinyOlDialog::onRunOl() { sendLine("$SILOLRUN,START"); }
void TinyOlDialog::onRunValidation() { sendLine("$SILOLVAL,RUN"); }
void TinyOlDialog::onGetResult() { sendLine("$SILOLRESULT?"); }
void TinyOlDialog::onApplyHead() { sendLine("$SILOLAPPLY"); }
void TinyOlDialog::onRollbackHead() { sendLine("$SILOLROLLBACK"); }
void TinyOlDialog::onBackToCnn() { sendLine("$SILAPP,CNN"); }
'@

Write-All (Join-Path $root 'tinyoldialog.h') $tinyolH
Write-All (Join-Path $root 'tinyoldialog.cpp') $tinyolCpp

# Patch TEST.pro.
$proPath = Join-Path $root 'TEST.pro'
$pro = Read-All $proPath
if ($pro -notmatch 'tinyoldialog\.cpp') {
    $pro = $pro.Replace("    uartsettingdialog.cpp", "    uartsettingdialog.cpp`r`n    tinyoldialog.cpp")
}
if ($pro -notmatch 'tinyoldialog\.h') {
    $pro = $pro.Replace("    uartsettingdialog.h", "    uartsettingdialog.h`r`n    tinyoldialog.h")
}
Write-All $proPath $pro

# Patch mainwindow.h.
$hPath = Join-Path $root 'mainwindow.h'
$h = Read-All $hPath
if ($h -notmatch '#include <QPointer>') {
    $h = $h.Replace("#include <QCheckBox>", "#include <QCheckBox>`r`n#include <QPointer>")
}
if ($h -notmatch 'class TinyOlDialog;') {
    $h = $h.Replace("QT_END_NAMESPACE`r`n", "QT_END_NAMESPACE`r`n`r`nclass TinyOlDialog;`r`n")
}
if ($h -notmatch 'serialLineReceived') {
    $h = $h.Replace("public:`r`n    explicit MainWindow(QWidget *parent = nullptr);`r`n    ~MainWindow();", "public:`r`n    explicit MainWindow(QWidget *parent = nullptr);`r`n    ~MainWindow();`r`n`r`nsignals:`r`n    void serialLineReceived(const QString &line);")
}
if ($h -notmatch 'onTinyOlCheckboxToggled') {
    $h = $h.Replace("    void on_BTN_UART_SETTING_clicked();", "    void on_BTN_UART_SETTING_clicked();`r`n    void onTinyOlCheckboxToggled(bool checked);")
}
if ($h -notmatch 'updateTinyOlConnectionState') {
    $h = $h.Replace("    void appendLog(const QString &s);", "    void appendLog(const QString &s);`r`n    void updateTinyOlConnectionState();")
}
if ($h -notmatch 'tinyolBox_') {
    $h = $h.Replace("    QCheckBox *sumBox_ = nullptr;`r`n    QCheckBox *chBox_[6] = {nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};", "    QCheckBox *sumBox_ = nullptr;`r`n    QCheckBox *chBox_[6] = {nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};`r`n    QCheckBox *tinyolBox_ = nullptr;`r`n    QPointer<TinyOlDialog> tinyolDialog_;")
}
Write-All $hPath $h

# Patch mainwindow.cpp.
$cppPath = Join-Path $root 'mainwindow.cpp'
$cpp = Read-All $cppPath
if ($cpp -notmatch '#include "tinyoldialog.h"') {
    $includePatch = @'
#include "uartsettingdialog.h"
#include "tinyoldialog.h"
'@
    $cpp = $cpp.Replace('#include "uartsettingdialog.h"', $includePatch)
}
if ($cpp -notmatch 'emit serialLineReceived') {
    $cpp = $cpp.Replace("        const QString s = QString::fromLatin1(line).trimmed();`r`n        if (s.isEmpty()) continue;", "        const QString s = QString::fromLatin1(line).trimmed();`r`n        if (s.isEmpty()) continue;`r`n        emit serialLineReceived(s);")
}

$insert = @'

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
'@
if ($cpp -notmatch 'onTinyOlCheckboxToggled') {
    $anchor = "void MainWindow::on_CKB_SUM_toggled(bool /*checked*/)"
    $idx = $cpp.IndexOf($anchor)
    if ($idx -lt 0) {
        throw 'Could not find on_CKB_SUM_toggled anchor.'
    }
    $cpp = $cpp.Insert($idx, $insert)
}

if ($cpp -notmatch 'CKB_TINYOL') {
    $marker = "  ui->textEdit_LOG->document()->setMaximumBlockCount(2000);"
    $checkbox = @'

  tinyolBox_ = new QCheckBox(QStringLiteral("TinyOL"), this);
  tinyolBox_->setObjectName(QStringLiteral("CKB_TINYOL"));
  if (ui->gridLayout_4) {
    ui->gridLayout_4->addWidget(tinyolBox_, 6, 0, 1, 2);
  }
  connect(tinyolBox_, &QCheckBox::toggled, this, &MainWindow::onTinyOlCheckboxToggled);
'@
    if ($cpp.Contains($marker)) {
        $cpp = $cpp.Replace($marker, $checkbox + "`r`n" + $marker)
    } else {
        throw 'Could not find log block marker for checkbox insertion.'
    }
}

$connectedPatch = @'
    appendLog(tr("Connected: %1, %2 bps").arg(portName).arg(serial_.baudRate()));
    statusBar()->showMessage(tr("Connected: %1").arg(portName), 2000);
    updateTinyOlConnectionState();
    startCsvRecording();
'@
$cpp = $cpp.Replace(@'
    appendLog(tr("Connected: %1, %2 bps").arg(portName).arg(serial_.baudRate()));
    statusBar()->showMessage(tr("Connected: %1").arg(portName), 2000);
    startCsvRecording();
'@, $connectedPatch)

$disconnectPatch = @'
        stopCsvRecording();
        if (sumBox_) sumBox_->setEnabled(true);
        updateSumPlotsVisibility();
        updateTinyOlConnectionState();
'@
$cpp = $cpp.Replace(@'
        stopCsvRecording();
        if (sumBox_) sumBox_->setEnabled(true);
        updateSumPlotsVisibility();
'@, $disconnectPatch)

$errorPatch = @'
        if (serial_.isOpen()) {
            suppressErrorOnClose_ = true;
            serial_.close();
            suppressErrorOnClose_ = false;
        }
        ui->BTN_CONNECT->setText(QStringLiteral("???"));
        updateTinyOlConnectionState();
'@
$cpp = $cpp.Replace(@'
        if (serial_.isOpen()) {
            suppressErrorOnClose_ = true;
            serial_.close();
            suppressErrorOnClose_ = false;
        }
        ui->BTN_CONNECT->setText(QStringLiteral("???"));
'@, $errorPatch)

Write-All $cppPath $cpp

Write-Output 'Prepared glove TinyOL patch script.'
