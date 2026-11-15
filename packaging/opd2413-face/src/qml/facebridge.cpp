// SPDX-License-Identifier: LGPL-2.1-or-later
// Qt6 QML D-Bus bridge for org.opd2413.Face1 lockscreen feedback & gating.

#include "facebridge.h"

#include <pwd.h>
#include <unistd.h>

#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCall>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QJSEngine>
#include <QQmlEngine>

namespace {

constexpr const char *kBusName = "org.opd2413.Face1";
constexpr const char *kBusPath = "/org/opd2413/Face1";
constexpr const char *kBusIface = "org.opd2413.Face1";

QString currentUsername()
{
    if (const struct passwd *pw = getpwuid(getuid())) {
        if (pw->pw_name && pw->pw_name[0] != '\0')
            return QString::fromLocal8Bit(pw->pw_name);
    }
    return qEnvironmentVariable("USER");
}

} // namespace

FaceBridge::FaceBridge(QObject *parent)
    : QObject(parent)
    , m_username(currentUsername())
{
    QDBusConnection::systemBus().connect(
        QString::fromLatin1(kBusName),
        QString::fromLatin1(kBusPath),
        QString::fromLatin1(kBusIface),
        QStringLiteral("StatusChanged"),
        this,
        SLOT(onStatusChanged(QString, QString)));

    refreshEnrolled();
}

FaceBridge::~FaceBridge()
{
    if (m_controlled && !m_username.isEmpty()) {
        QDBusMessage msg = QDBusMessage::createMethodCall(
            QString::fromLatin1(kBusName),
            QString::fromLatin1(kBusPath),
            QString::fromLatin1(kBusIface),
            QStringLiteral("SetLockscreenMode"));
        msg << m_username << false << false;
        QDBusConnection::systemBus().asyncCall(msg);
    }
}

void FaceBridge::setLockscreenMode(bool controlled, bool armed)
{
    if (m_username.isEmpty())
        return;

    m_controlled = controlled;
    QDBusMessage msg = QDBusMessage::createMethodCall(
        QString::fromLatin1(kBusName),
        QString::fromLatin1(kBusPath),
        QString::fromLatin1(kBusIface),
        QStringLiteral("SetLockscreenMode"));
    msg << m_username << controlled << armed;
    QDBusConnection::systemBus().asyncCall(msg, 1500);
}

void FaceBridge::armScan()
{
    if (m_username.isEmpty())
        return;

    m_controlled = true;
    setStateInternal(QStringLiteral("scanning"), QString());

    QDBusMessage msg = QDBusMessage::createMethodCall(
        QString::fromLatin1(kBusName),
        QString::fromLatin1(kBusPath),
        QString::fromLatin1(kBusIface),
        QStringLiteral("SetLockscreenMode"));
    msg << m_username << true << true;

    QDBusPendingCall call = QDBusConnection::systemBus().asyncCall(msg, 1500);
    auto *watcher = new QDBusPendingCallWatcher(call, this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [this](QDBusPendingCallWatcher *w) {
        QDBusPendingReply<bool> reply(*w);
        const bool ok = !reply.isError() && reply.value();
        w->deleteLater();
        if (ok) {
            Q_EMIT scanArmed();
        } else {
            setStateInternal(QStringLiteral("failed"), QStringLiteral("service-unavailable"));
        }
    });
}

void FaceBridge::refreshEnrolled()
{
    if (m_username.isEmpty())
        return;

    QDBusMessage msg = QDBusMessage::createMethodCall(
        QString::fromLatin1(kBusName),
        QString::fromLatin1(kBusPath),
        QString::fromLatin1(kBusIface),
        QStringLiteral("HasEnrolled"));
    msg << m_username;

    QDBusPendingCall call = QDBusConnection::systemBus().asyncCall(msg, 1500);
    auto *watcher = new QDBusPendingCallWatcher(call, this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [this](QDBusPendingCallWatcher *w) {
        QDBusPendingReply<bool> reply(*w);
        if (!reply.isError()) {
            const bool val = reply.value();
            if (m_enrolled != val) {
                m_enrolled = val;
                Q_EMIT enrolledChanged();
            }
        }
        w->deleteLater();
    });
}

void FaceBridge::resetState()
{
    if (m_faceState != QLatin1String("matched"))
        setStateInternal(QStringLiteral("ready"), QString());
}

void FaceBridge::onStatusChanged(const QString &state, const QString &detail)
{
    QString mapped = state;
    if (mapped == QLatin1String("idle"))
        mapped = QStringLiteral("ready");
    else if (mapped != QLatin1String("scanning") &&
             mapped != QLatin1String("matched") &&
             mapped != QLatin1String("failed"))
        mapped = QStringLiteral("ready");

    setStateInternal(mapped, detail);
}

void FaceBridge::setStateInternal(const QString &state, const QString &reason)
{
    if (m_faceState != state) {
        m_faceState = state;
        Q_EMIT faceStateChanged();
    }
    if (m_lastReason != reason) {
        m_lastReason = reason;
        Q_EMIT lastReasonChanged();
    }
    const bool nowBusy = (state == QLatin1String("scanning"));
    if (m_busy != nowBusy) {
        m_busy = nowBusy;
        Q_EMIT busyChanged();
    }
}

void Opd2413FacePlugin::registerTypes(const char *uri)
{
    qmlRegisterSingletonType<FaceBridge>(
        uri, 1, 0, "FaceBridge",
        [](QQmlEngine *engine, QJSEngine *scriptEngine) -> QObject * {
            Q_UNUSED(engine)
            Q_UNUSED(scriptEngine)
            return new FaceBridge();
        });
}
