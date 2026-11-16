// SPDX-License-Identifier: LGPL-2.1-or-later
// Qt6 QML D-Bus bridge for org.opd2413.Face1 lockscreen feedback & gating.

#pragma once

#include <QObject>
#include <QQmlExtensionPlugin>
#include <QString>

class FaceBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool enrolled READ enrolled NOTIFY enrolledChanged)
    Q_PROPERTY(QString faceState READ faceState NOTIFY faceStateChanged)
    Q_PROPERTY(QString lastReason READ lastReason NOTIFY lastReasonChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool lidClosed READ lidClosed NOTIFY lidClosedChanged)

public:
    explicit FaceBridge(QObject *parent = nullptr);
    ~FaceBridge() override;

    bool enrolled() const { return m_enrolled; }
    QString faceState() const { return m_faceState; }
    QString lastReason() const { return m_lastReason; }
    bool busy() const { return m_busy; }
    bool lidClosed() const { return m_lidClosed; }

    Q_INVOKABLE void setLockscreenMode(bool controlled, bool armed);
    Q_INVOKABLE void armScan();
    Q_INVOKABLE void refreshEnrolled();
    Q_INVOKABLE void resetState();

Q_SIGNALS:
    void enrolledChanged();
    void faceStateChanged();
    void lastReasonChanged();
    void busyChanged();
    void lidClosedChanged();
    void scanArmed();

private Q_SLOTS:
    void onStatusChanged(const QString &state, const QString &detail);
    void onUPowerPropertiesChanged(const QString &iface, const QVariantMap &changed, const QStringList &invalidated);

private:
    void setStateInternal(const QString &state, const QString &reason);
    void setLidClosedInternal(bool closed);
    void refreshLidClosed();

    QString m_username;
    bool m_enrolled = false;
    bool m_controlled = false;
    QString m_faceState = QStringLiteral("ready");
    QString m_lastReason;
    bool m_busy = false;
    bool m_lidClosed = false;
};

class Opd2413FacePlugin : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)

public:
    void registerTypes(const char *uri) override;
};
