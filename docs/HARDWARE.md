# 硬件清单与复用来源

器件清单来自 2026-11-10 在 ColorOS（`OPD2413_16.0.10.600(CN01)`，内核 6.6.118）下的只读采集
（I2C / SPI 设备、输入设备、传感器服务、固件目录）。

"Armada 结论"指 armada 仓库 `oneplus-pad-2-pro` 分支在 7.2.6 内核上的真机结果；
"erhai 结论"指 `onepluspad-2pro-mainline` v0.6.0 README 里声明的状态，在本机验证前只算线索。

Fedora 下的状态统一记在 [STATUS.md](STATUS.md)，这里只记器件和来源。

## 平台、显示与输入

| 功能 | 器件 | Armada 结论 | erhai 结论 | 来源选择 |
|---|---|---|---|---|
| 存储 | UFS，6 LUN | 真机通过（机内安装） | 可用 | Armada |
| 显示 | 双 DSI + DSC，3392×2400，NT36536 面板 | 真机通过；开机灰闪未解决 | 可用，120 Hz | Armada（含 `1404`–`1409` 启动交接修复） |
| 背光 | 2× KTZ8868（I2C 0x11） | 真机通过 | 部分 | Armada |
| 触控 | NT36536，SPI | 真机通过，需固件 `nt36536-xn242.bin` | 可用 | Armada |
| GPU | Adreno 830 | 真机通过（Mesa 26.2.5 带补丁，freedreno + turnip） | 部分 | 先试 Fedora 的 Mesa 26.2.6 |
| 键盘套 | Pogo 键盘 + 触控板，UART；脱离后可走蓝牙 | 键盘和触控板真机通过 | 键盘可用，手势待测 | Armada 驱动；休眠重连、顶排键、合盖参考 erhai |
| 合盖 | 霍尔 BU52053 | 未做 | 可用 | erhai |
| 电源键、音量键 | PMIC PON、GPIO | 未验收 | 可用 | Armada DTS + erhai 策略 |
| 手写笔 | NT36536 笔输入、CPS8601 无线充电（I2C 0x41）、`wireless_pen_glink` | — | 未实现 | **不做**（用户决定） |

## 无线与 USB

| 功能 | 器件 | Armada 结论 | erhai 结论 | 来源选择 |
|---|---|---|---|---|
| Wi-Fi | WCN7860，PCIe，ath12k | 真机通过 | 可用；5 GHz 仅被动扫描 | Armada 补丁 + erhai 的板级数据和 regdb |
| 蓝牙 | WCN7860，UART | 未验收 | 控制器和扫描通过 | erhai 的地址服务 |
| USB 2 | eUSB2 | 真机通过 | 部分 | Armada |
| USB 3 | QMP PHY + WCD939x USBSS | 只有一个插入方向 | 部分 | 待修：UCSI 方向传给 PHY |
| DP 外接 | USB-C Alt Mode | 未验收 | 出图已确认 | erhai |

## 音视频与传感器

| 功能 | 器件 | Armada 结论 | erhai 结论 | 来源选择 |
|---|---|---|---|---|
| 扬声器 | 6× AW88261（I2C 0x34–0x36 ×2），TDM，AudioReach | 真机通过（350 / −2.5 dB，无原厂保护） | 部分 | Armada `1408` + UCM + 拓扑 |
| 麦克风 | WCD939x | 增益未验收 | 部分 | erhai 的增益值 |
| 视频硬解 | Iris，`vpu35_4v.mbn` | 未验收 | H.264 / H.265 / VP9 | erhai |
| 摄像头 | 后 SC1300CS、前 SC820CS，camss + libcamera | 未做（DTS 有节点，序列里没有驱动） | 可预览拍照，画质有限 | erhai |
| 加速度 / 陀螺 | BMI3x0，经 SSC（ADSP） | 未做 | 自动旋转可用 | erhai 的传感器栈 |
| 磁力计 | MXG4300，经 SSC | 未做 | 部分 | erhai |
| 环境光 | STK37600，经 SSC | 未做 | 部分 | erhai |

## 电源

| 功能 | 器件 | Armada 结论 | erhai 结论 | 来源选择 |
|---|---|---|---|---|
| 电量 | `qcom_battmgr` | 未验收 | 可用 | Armada 补丁 + erhai 修复 |
| 充电 | PMIC Glink；2× SC8547A 电荷泵（I2C 0x6f） | 未做 | 9 V PD 18 W 可用；PPS 默认关 | erhai |
| 休眠 | s2idle | 真机失败（空闲挂起后挂死，已禁用） | 可用，最深态 98–99% | erhai |
| 温控、调频 | tsens、SCMI | 未验收 | 部分 | erhai |
| RTC | PMK8550 | 未验收 | 可用 | Armada DTS |
| 振动 | `qcom-hv-haptics` | 未验收 | — | Armada 有 SM8750 haptics 补丁，待调研 |

## 做不到或不做

| 功能 | 原因 |
|---|---|
| SUPERVOOC / UFCS 快充 | 专有协议，由 `oplus_chg_v2` 和充电 MCU 固件实现 |
| 指纹 | TEE 里的 trustlet 加专有 HAL |
| 原厂相机算法 | `CAMERA_ICP` 固件加 chi-cdk 调参，只有 Android HAL 能驱动 |
| Widevine / HDCP | TEE |
| NFC | ColorOS 里注册了 `oplus-nfc-chipset` 驱动，本机是否有该硬件未确认；不在范围内 |
| 手写笔 | 用户决定忽略 |
