#!/usr/bin/python3 -B
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Desktop GUI wizard for OPD2413 native face enrollment and live test."""

import json
import os
import pwd
import subprocess
import sys

if "--worker" in sys.argv:
    # Privileged root worker invoked once via pkexec to execute D-Bus enroll/test calls.
    from gi.repository import Gio, GLib
    import time

    idx = sys.argv.index("--worker")
    if idx + 1 >= len(sys.argv):
        sys.exit(2)
    target_user = sys.argv[idx + 1]
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def call_face(method: str, sig: str, args: tuple, ret_sig: str, timeout_ms: int):
        res = bus.call_sync(
            "org.opd2413.Face1",
            "/org/opd2413/Face1",
            "org.opd2413.Face1",
            method,
            GLib.Variant(sig, args) if sig else None,
            GLib.VariantType(ret_sig),
            Gio.DBusCallFlags.NONE,
            timeout_ms,
            None,
        )
        return res.unpack()

    print(json.dumps({"ready": True}), flush=True)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            cmd = req.get("cmd")
            if cmd == "enroll":
                replace = bool(req.get("replace", False))
                ok, count, msg = call_face(
                    "EnrollSample", "(sbu)", (target_user, replace, 10000), "(bus)", 12000
                )
                print(json.dumps({"cmd": "enroll", "ok": ok, "count": count, "msg": msg}), flush=True)
            elif cmd == "test":
                t0 = time.monotonic()
                matched, reason, score = call_face(
                    "Verify", "(ssu)", (target_user, "opd-face-gui", 5000), "(bsd)", 8000
                )
                ms = round((time.monotonic() - t0) * 1000.0)
                print(
                    json.dumps(
                        {"cmd": "test", "ok": matched, "reason": reason, "score": score, "ms": ms}
                    ),
                    flush=True,
                )
            elif cmd == "quit":
                break
        except Exception as exc:
            print(json.dumps({"cmd": "error", "ok": False, "msg": str(exc)}), flush=True)
    sys.exit(0)


if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "wayland"

from gi.repository import Gio, GLib
from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

STEPS = [
    ("正视前置摄像头", "请让头部居于屏幕上方镜头正前方，保持正常室内光线与日常阅读距离", True),
    ("头微微向左转", "眼神尽量靠近镜头方向，头部轻轻向左偏转约 10°–15°", False),
    ("头微微向右转", "眼神尽量靠近镜头方向，头部轻轻向右偏转约 10°–15°", False),
    ("头微微向上抬", "保持自然阅读距离，下巴轻轻向上抬起约 10°", False),
]

REASON_HINTS = {
    "no-face": "未检测到清晰正脸 — 请面向顶部摄像头并保持充足光线",
    "pose": "头部偏转角度过大 — 请稍微回正一点（眼神靠近镜头）",
    "blurry": "画面略模糊 — 采集中请暂时保持头部稳定",
    "static-frame": "检测到静止帧 — 请自然轻微眨眼或微动一下再试",
    "timeout": "等待超时（10 秒）— 请确认镜头未被遮挡且面向屏幕",
    "camera-missing": "前置摄像头暂时被占用或不可用 — 请先关闭相机软件",
    "busy": "相机正在被占用，请稍候再试",
    "lid-closed": "系统报告处于合盖状态，无法验证",
}


def explain_reason(msg: str) -> str:
    for key, text in REASON_HINTS.items():
        if key in msg:
            return f"{text} ({msg})"
    return msg


class EnrollWindow(QMainWindow):
    def __init__(self, target_user: str):
        super().__init__()
        self.target_user = target_user
        self.worker = None
        self.worker_buf = ""
        self.step_idx = 0
        self.phase = "idle"  # idle | countdown | capturing | testing | done
        self.countdown_ms = 0
        self.countdown_total_ms = 2800

        self.setWindowTitle("OPD2413 人脸解锁录入向导")
        self.setWindowIcon(QIcon.fromTheme("face-smile"))
        self.setMinimumSize(760, 520)
        self.setStyleSheet(
            """
            QMainWindow { background-color: #12161f; color: #eef2f7; }
            QLabel { color: #eef2f7; }
            QFrame#card {
                background-color: #1b2230;
                border: 1px solid #2b364d;
                border-radius: 16px;
            }
            QPushButton {
                background-color: #2f7df6;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #468df8; }
            QPushButton:disabled { background-color: #2b364d; color: #7f8da6; }
            QPushButton#secondary { background-color: #283246; color: #dbe4f3; }
            QPushButton#secondary:hover { background-color: #34415b; }
            QProgressBar {
                background-color: #0e131b;
                border: 1px solid #2b364d;
                border-radius: 8px;
                height: 16px;
                text-align: center;
                color: #dbe4f3;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 7px;
            }
            """
        )

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        title = QLabel(f"OPD2413 原生人脸录入向导（用户：{self.target_user}）")
        title.setFont(QFont("Sans Serif", 20, QFont.Weight.Bold))
        lay.addWidget(title)

        self.env_banner = QLabel("正在检测前置摄像头与服务状态...")
        self.env_banner.setWordWrap(True)
        self.env_banner.setStyleSheet(
            "background-color: #1f293a; border-radius: 10px; padding: 10px 14px; font-size: 14px;"
        )
        lay.addWidget(self.env_banner)

        # Progress pills
        pills_row = QHBoxLayout()
        pills_row.setSpacing(10)
        self.pills = []
        for idx in range(5):
            lbl = QLabel(f"第 {idx + 1} 步" if idx < 4 else "识别验证")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "background-color: #1e2636; border: 1px solid #303d56; border-radius: 8px; padding: 8px; font-size: 14px;"
            )
            pills_row.addWidget(lbl)
            self.pills.append(lbl)
        lay.addLayout(pills_row)

        # Center instruction card
        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(28, 28, 28, 28)
        card_lay.setSpacing(14)

        self.step_title = QLabel("准备开始人脸录入")
        self.step_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_title.setFont(QFont("Sans Serif", 24, QFont.Weight.Bold))
        card_lay.addWidget(self.step_title)

        self.step_desc = QLabel(
            "点击下方“开始录入”后将弹出一次密码授权窗，随后共采集 4 组角度并自动进行实测验证。"
        )
        self.step_desc.setWordWrap(True)
        self.step_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_desc.setStyleSheet("font-size: 16px; color: #c4d0e3;")
        card_lay.addWidget(self.step_desc)

        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setFont(QFont("Sans Serif", 34, QFont.Weight.Bold))
        self.countdown_label.setStyleSheet("color: #38bdf8;")
        card_lay.addWidget(self.countdown_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        card_lay.addWidget(self.progress)

        self.status_msg = QLabel("")
        self.status_msg.setWordWrap(True)
        self.status_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_msg.setStyleSheet("font-size: 15px; color: #9ec5fe;")
        card_lay.addWidget(self.status_msg)

        lay.addWidget(card, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_start = QPushButton("开始全新录入（4组）")
        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_retry = QPushButton("重试当前步骤")
        self.btn_retry.setObjectName("secondary")
        self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self.on_retry_clicked)
        self.btn_test = QPushButton("立即测试识别")
        self.btn_test.setObjectName("secondary")
        self.btn_test.clicked.connect(self.on_test_clicked)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setObjectName("secondary")
        self.btn_close.clicked.connect(self.close)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_retry)
        btn_row.addWidget(self.btn_test)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_close)
        lay.addLayout(btn_row)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_env_status)
        self.poll_timer.start(1200)
        self.refresh_env_status()

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_countdown_tick)

    def _update_pills(self, active_idx: int, completed_up_to: int, failed_idx: int = -1):
        for i, pill in enumerate(self.pills):
            if i == failed_idx:
                pill.setStyleSheet(
                    "background-color: #5b2029; border: 1px solid #ef4444; color: #fecaca; border-radius: 8px; padding: 8px; font-weight: 700;"
                )
            elif i < completed_up_to:
                pill.setStyleSheet(
                    "background-color: #164e36; border: 1px solid #22c55e; color: #dcfce7; border-radius: 8px; padding: 8px; font-weight: 700;"
                )
            elif i == active_idx:
                pill.setStyleSheet(
                    "background-color: #1d3c6e; border: 1px solid #38bdf8; color: #ffffff; border-radius: 8px; padding: 8px; font-weight: 700;"
                )
            else:
                pill.setStyleSheet(
                    "background-color: #1e2636; border: 1px solid #303d56; color: #94a3b8; border-radius: 8px; padding: 8px;"
                )

    def refresh_env_status(self):
        busy_apps = []
        for proc in ("kamoso", "snapshot", "cheese", "qcam", "cam"):
            res = subprocess.run(["pgrep", "-x", proc], capture_output=True)
            if res.returncode == 0:
                busy_apps.append(proc)

        enrolled = False
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            res = bus.call_sync(
                "org.opd2413.Face1",
                "/org/opd2413/Face1",
                "org.opd2413.Face1",
                "HasEnrolled",
                GLib.Variant("(s)", (self.target_user,)),
                GLib.VariantType("(b)"),
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            enrolled = bool(res.unpack()[0])
        except Exception as exc:
            self.env_banner.setText(f"❌ 人脸守护服务未响应：{exc}")
            self.env_banner.setStyleSheet(
                "background-color: #4c1d24; border-radius: 10px; padding: 10px 14px; font-size: 14px;"
            )
            return

        if busy_apps:
            self.env_banner.setText(
                f"⚠ 检测到相机应用（{', '.join(busy_apps)}）正在占用镜头，请先关闭后再点击开始！"
            )
            self.env_banner.setStyleSheet(
                "background-color: #5c3d12; color: #fde68a; border-radius: 10px; padding: 10px 14px; font-size: 14px; font-weight: 600;"
            )
        else:
            st = "已存在旧模板（重新录入将覆盖）" if enrolled else "尚未录入"
            self.env_banner.setText(f"✅ 前置摄像头与服务就绪 | 用户 {self.target_user} 当前状态：{st}")
            self.env_banner.setStyleSheet(
                "background-color: #163b2d; color: #bbf7d0; border-radius: 10px; padding: 10px 14px; font-size: 14px;"
            )

    def ensure_worker(self, pending_action):
        if self.worker is not None and self.worker.state() == QProcess.ProcessState.Running:
            pending_action()
            return
        self.pending_after_ready = pending_action
        self.worker_buf = ""
        self.worker = QProcess(self)
        self.worker.readyReadStandardOutput.connect(self.on_worker_stdout)
        self.worker.finished.connect(self.on_worker_finished)
        self.phase = "auth"
        self.status_msg.setText("正在请求管理员授权（请在弹窗中输入一次用户密码）...")
        self.worker.start(
            "pkexec",
            ["/usr/bin/python3", "-B", "/usr/libexec/opd2413/opd-face-enroll", "--worker", self.target_user],
        )

    def send_worker_cmd(self, payload: dict):
        line = (json.dumps(payload) + "\n").encode("utf-8")
        self.worker.write(line)

    def on_start_clicked(self):
        self.step_idx = 0
        self.btn_start.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_test.setEnabled(False)
        self.ensure_worker(self.start_step_countdown)

    def on_retry_clicked(self):
        self.btn_start.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_test.setEnabled(False)
        self.ensure_worker(self.start_step_countdown)

    def on_test_clicked(self):
        self.phase = "testing"
        self.btn_start.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_test.setEnabled(False)
        self._update_pills(4, 4 if self.step_idx >= 4 else self.step_idx)
        self.step_title.setText("正在测试实时人脸识别")
        self.step_desc.setText("请自然正对前置摄像头（超时 5 秒）...")
        self.countdown_label.setText("🔍 识别中")
        self.progress.setRange(0, 0)
        self.ensure_worker(lambda: self.send_worker_cmd({"cmd": "test"}))

    def start_step_countdown(self):
        title, desc, _ = STEPS[self.step_idx]
        self.phase = "countdown"
        self.countdown_total_ms = 2800
        self.countdown_ms = self.countdown_total_ms
        self._update_pills(self.step_idx, self.step_idx)
        self.step_title.setText(f"第 {self.step_idx + 1}/4 步：{title}")
        self.step_desc.setText(desc)
        self.status_msg.setText("请在倒计时结束前调整好头部姿态")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.countdown_label.setStyleSheet("color: #38bdf8;")
        self.countdown_label.setText("准备动作：3")
        self.tick_timer.start(100)

    def on_countdown_tick(self):
        self.countdown_ms -= 100
        if self.countdown_ms > 0:
            secs = (self.countdown_ms + 999) // 1000
            self.countdown_label.setText(f"准备动作：{secs}")
            pct = int(100 * (self.countdown_total_ms - self.countdown_ms) / self.countdown_total_ms)
            self.progress.setValue(max(0, min(100, pct)))
            return

        self.tick_timer.stop()
        self.phase = "capturing"
        _, _, replace_flag = STEPS[self.step_idx]
        # Preserve already-captured templates when retrying step 0 only after user explicitly chose restart.
        replace = replace_flag and (self.step_idx == 0)
        self.progress.setRange(0, 0)
        self.countdown_label.setStyleSheet("color: #fbbf24;")
        self.countdown_label.setText("📸 正在采集...")
        self.status_msg.setText("请保持当前姿势不动（最多等待 10 秒）...")
        self.send_worker_cmd({"cmd": "enroll", "replace": replace})

    def on_worker_stdout(self):
        self.worker_buf += bytes(self.worker.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self.worker_buf:
            line, self.worker_buf = self.worker_buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("ready"):
                if getattr(self, "pending_after_ready", None):
                    cb = self.pending_after_ready
                    self.pending_after_ready = None
                    cb()
                continue

            cmd = msg.get("cmd")
            if cmd == "enroll":
                self.progress.setRange(0, 100)
                self.progress.setValue(100)
                if msg.get("ok"):
                    completed = self.step_idx + 1
                    self._update_pills(completed, completed)
                    self.countdown_label.setStyleSheet("color: #4ade80;")
                    self.countdown_label.setText(f"✅ 第 {completed}/4 步成功")
                    self.status_msg.setText(f"已保存模板 #{msg.get('count', completed)}")
                    if completed < len(STEPS):
                        self.step_idx = completed
                        QTimer.singleShot(1100, self.start_step_countdown)
                    else:
                        self.step_idx = len(STEPS)
                        self.phase = "testing"
                        self.step_title.setText("4 组模板录入完成！")
                        self.step_desc.setText("1.5 秒后自动进行实时识别验证，请自然看向镜头...")
                        QTimer.singleShot(1500, self.on_test_clicked)
                else:
                    self._update_pills(self.step_idx, self.step_idx, failed_idx=self.step_idx)
                    self.countdown_label.setStyleSheet("color: #f87171;")
                    self.countdown_label.setText(f"❌ 第 {self.step_idx + 1} 步失败")
                    self.status_msg.setText(explain_reason(msg.get("msg", "unknown")))
                    self.phase = "idle"
                    self.btn_start.setEnabled(True)
                    self.btn_retry.setEnabled(True)
                    self.btn_test.setEnabled(True)
            elif cmd == "test":
                self.progress.setRange(0, 100)
                self.progress.setValue(100)
                self.phase = "done"
                score = float(msg.get("score", 0.0))
                ms = msg.get("ms", 0)
                reason = msg.get("reason", "")
                if msg.get("ok"):
                    self._update_pills(-1, 5)
                    self.step_title.setText("🎉 人脸识别验证通过！")
                    self.step_desc.setText("4 组姿态录入且实时验证已成功，现在可以直接关闭窗口并在锁屏或授权弹窗中使用人脸识别。")
                    self.countdown_label.setStyleSheet("color: #4ade80;")
                    self.countdown_label.setText(f"相似度 {score:.3f} · {ms} ms")
                    self.status_msg.setText(f"详情：{reason}")
                else:
                    self._update_pills(4, 4, failed_idx=4)
                    self.step_title.setText("识别未通过")
                    self.step_desc.setText("可以保持自然坐姿再点一次“立即测试识别”，或重新录入 4 组。")
                    self.countdown_label.setStyleSheet("color: #f87171;")
                    self.countdown_label.setText(f"未匹配（{score:.3f}）")
                    self.status_msg.setText(explain_reason(reason))
                self.btn_start.setEnabled(True)
                self.btn_retry.setEnabled(self.step_idx < 4)
                self.btn_test.setEnabled(True)
            elif cmd == "error":
                self.progress.setRange(0, 100)
                self.countdown_label.setStyleSheet("color: #f87171;")
                self.countdown_label.setText("❌ 执行出错")
                self.status_msg.setText(msg.get("msg", "unknown error"))
                self.btn_start.setEnabled(True)
                self.btn_retry.setEnabled(self.step_idx < 4)
                self.btn_test.setEnabled(True)

    def on_worker_finished(self, code, _status):
        self.tick_timer.stop()
        if self.phase != "done":
            self.progress.setRange(0, 100)
            self.countdown_label.setStyleSheet("color: #f87171;")
            self.countdown_label.setText("授权已取消")
            self.status_msg.setText("未完成管理员密码授权或授权进程已退出，请点击按钮重试。")
            self.phase = "idle"
            self.btn_start.setEnabled(True)
            self.btn_retry.setEnabled(self.step_idx < 4)
            self.btn_test.setEnabled(True)
        self.worker = None

    def closeEvent(self, event):
        if self.worker is not None and self.worker.state() == QProcess.ProcessState.Running:
            try:
                self.send_worker_cmd({"cmd": "quit"})
                self.worker.waitForFinished(800)
            except Exception:
                pass
            if self.worker is not None and self.worker.state() == QProcess.ProcessState.Running:
                self.worker.kill()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setDesktopFileName("opd-face-enroll")
    target = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
    win = EnrollWindow(target)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
