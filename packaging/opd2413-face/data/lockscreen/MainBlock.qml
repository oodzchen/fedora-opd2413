/*
    SPDX-FileCopyrightText: 2016 David Edmundson <davidedmundson@kde.org>

    SPDX-License-Identifier: LGPL-2.0-or-later
*/

import QtQuick

import QtQuick.Layouts
import QtQuick.Controls as QQC2

import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami
import org.kde.kscreenlocker as ScreenLocker

import org.kde.breeze.components
import org.opd2413.face

SessionManagementScreen {
    id: sessionManager

    property alias passwordInputVisible: passwordLayout.visible
    readonly property alias mainPasswordBox: passwordBox
    property bool lockScreenUiVisible: false
    property alias showPassword: passwordBox.showPassword
    signal faceRetryRequested()

    //the y position that should be ensured visible when the on screen keyboard is visible
    property int visibleBoundary: mapFromItem(loginButton, 0, 0).y
    onHeightChanged: visibleBoundary = mapFromItem(loginButton, 0, 0).y + loginButton.height + Kirigami.Units.smallSpacing
    /*
     * Login has been requested with the following username and password
     * If username field is visible, it will be taken from that, otherwise from the "name" property of the currentIndex
     */
    signal passwordResult(string password)

    onUserSelected: {
        const nextControl = (passwordBox.visible ? passwordBox : loginButton);
        // Don't startLogin() here, because the signal is connected to the
        // Escape key as well, for which it wouldn't make sense to trigger
        // login. Using TabFocusReason, so that the loginButton gets the
        // visual highlight.
        nextControl.forceActiveFocus(Qt.TabFocusReason);
    }

    function startLogin() {
        const password = passwordBox.text

        // This is partly because it looks nicer, but more importantly it
        // works round a Qt bug that can trigger if the app is closed with a
        // TextField focused.
        //
        // See https://bugreports.qt.io/browse/QTBUG-55460
        loginButton.forceActiveFocus();
        passwordResult(password);
    }

    RowLayout {
        id: passwordLayout
        Layout.fillWidth: true

        PlasmaExtras.PasswordField {
            id: passwordBox
            font.pointSize: Kirigami.Theme.defaultFont.pointSize + 1
            Layout.fillWidth: true
            text: PasswordSync.password

            placeholderText: i18ndc("plasma_shell_org.kde.plasma.desktop", "@info:placeholder in text field", "Password")
            focus: true

            // In Qt this is implicitly active based on focus rather than visibility
            // in any other application having a focussed invisible object would be weird
            // but here we are using to wake out of screensaver mode
            // We need to explicitly disable cursor flashing to avoid unnecessary renders
            cursorVisible: visible

            onAccepted: {
                if (sessionManager.lockScreenUiVisible) {
                    sessionManager.startLogin();
                }
            }

            //if empty and left or right is pressed change selection in user switch
            //this cannot be in keys.onLeftPressed as then it doesn't reach the password box
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Left && !text) {
                    sessionManager.userList.decrementCurrentIndex();
                    event.accepted = true
                }
                if (event.key === Qt.Key_Right && !text) {
                    sessionManager.userList.incrementCurrentIndex();
                    event.accepted = true
                }
            }

            Connections {
                target: root
                function onClearPassword() {
                    passwordBox.forceActiveFocus()
                    passwordBox.text = "";
                    passwordBox.text = Qt.binding(() => PasswordSync.password);
                }
                function onNotificationRepeated() {
                    sessionManager.playHighlightAnimation();
                }
            }
        }
        Binding {
            target: PasswordSync
            property: "password"
            value: passwordBox.text
        }

        PlasmaComponents3.Button {
            id: loginButton
            Accessible.name: i18ndc("plasma_shell_org.kde.plasma.desktop", "@action:button accessible only", "Unlock")
            Layout.preferredHeight: passwordBox.implicitHeight
            Layout.preferredWidth: loginButton.Layout.preferredHeight

            icon.name: LayoutMirroring.enabled ? "go-previous" : "go-next"

            onClicked: sessionManager.startLogin()
            Keys.onEnterPressed: clicked()
            Keys.onReturnPressed: clicked()
        }
    }

    component FailableLabel : PlasmaComponents3.Label {
        id: _failableLabel
        required property int kind
        required property string label

        visible: authenticator.authenticatorTypes & kind
        text: label
        textFormat: Text.PlainText
        horizontalAlignment: Text.AlignHCenter
        Layout.fillWidth: true

        RejectPasswordAnimation {
            id: _rejectAnimation
            target: _failableLabel
            onFinished: _timer.restart()
        }

        Connections {
            target: authenticator
            function onNoninteractiveError(kind, authenticator) {
                if (kind & _failableLabel.kind) {
                    _failableLabel.text = Qt.binding(() => authenticator.errorMessage)
                    _rejectAnimation.start()
                }
            }
        }
        Timer {
            id: _timer
            interval: Kirigami.Units.humanMoment
            onTriggered: {
                _failableLabel.text = Qt.binding(() => _failableLabel.label)
            }
        }
    }

    FailableLabel {
        kind: ScreenLocker.Authenticator.Fingerprint
        visible: (authenticator.authenticatorTypes & kind) && !FaceBridge.enrolled
        label: i18ndc("plasma_shell_org.kde.plasma.desktop", "@info:usagetip", "(or scan your fingerprint on the reader)")
    }
    FailableLabel {
        kind: ScreenLocker.Authenticator.Smartcard
        label: i18ndc("plasma_shell_org.kde.plasma.desktop", "@info:usagetip", "(or scan your smartcard)")
    }

    QQC2.AbstractButton {
        id: faceStatusPill
        visible: FaceBridge.enrolled
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: Kirigami.Units.smallSpacing
        leftPadding: Kirigami.Units.largeSpacing
        rightPadding: Kirigami.Units.largeSpacing
        topPadding: Kirigami.Units.smallSpacing
        bottomPadding: Kirigami.Units.smallSpacing
        focusPolicy: Qt.NoFocus
        enabled: FaceBridge.faceState === "failed" || FaceBridge.faceState === "ready"
        hoverEnabled: true

        readonly property bool isScanning: FaceBridge.faceState === "scanning"
        readonly property bool isMatched: FaceBridge.faceState === "matched"
        readonly property bool isFailed: FaceBridge.faceState === "failed"

        function statusLabel() {
            if (isScanning) {
                return "Verifying face...";
            }
            if (isMatched) {
                return "Face recognized";
            }
            if (isFailed) {
                const r = FaceBridge.lastReason;
                if (r === "no-face" || r === "timeout") {
                    return "No face detected — tap to retry";
                }
                if (r.startsWith("mismatch:")) {
                    return "Face not recognized — tap to retry";
                }
                if (r === "busy") {
                    return "Camera in use — tap to retry";
                }
                if (r === "lid-closed") {
                    return "Lid closed — enter password";
                }
                if (r.startsWith("camera-error") || r === "service-unavailable") {
                    return "Camera unavailable — enter password";
                }
                return "Face unlock paused — tap to retry";
            }
            return "Preparing face unlock...";
        }

        function iconSource() {
            if (isMatched) {
                return "object-unlocked-symbolic";
            }
            if (isScanning) {
                return "edit-image-face-recognize-symbolic";
            }
            return "edit-image-face-detect-symbolic";
        }

        onClicked: sessionManager.faceRetryRequested()

        background: Rectangle {
            radius: height / 2
            color: {
                if (faceStatusPill.isMatched) {
                    return Qt.rgba(0.16, 0.72, 0.38, 0.24);
                }
                if (faceStatusPill.isScanning) {
                    return Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.22);
                }
                if (faceStatusPill.hovered && faceStatusPill.enabled) {
                    return Qt.rgba(1, 1, 1, 0.16);
                }
                return Qt.rgba(0, 0, 0, 0.28);
            }
            border.width: 1
            border.color: {
                if (faceStatusPill.isMatched) {
                    return Kirigami.Theme.positiveTextColor;
                }
                if (faceStatusPill.isScanning) {
                    return Kirigami.Theme.highlightColor;
                }
                if (faceStatusPill.isFailed) {
                    return Qt.rgba(1, 1, 1, 0.32);
                }
                return Qt.rgba(1, 1, 1, 0.22);
            }
            Behavior on color {
                ColorAnimation { duration: 180 }
            }
            Behavior on border.color {
                ColorAnimation { duration: 180 }
            }
        }

        contentItem: RowLayout {
            id: faceStatusRow
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                id: faceIcon
                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                source: faceStatusPill.iconSource()
                isMask: true
                color: {
                    if (faceStatusPill.isMatched) {
                        return Kirigami.Theme.positiveTextColor;
                    }
                    if (faceStatusPill.isScanning) {
                        return Kirigami.Theme.highlightColor;
                    }
                    if (faceStatusPill.isFailed) {
                        return Kirigami.Theme.neutralTextColor;
                    }
                    return Kirigami.Theme.textColor;
                }

                onVisibleChanged: {
                    if (!faceStatusPill.isScanning) {
                        opacity = 1.0;
                        scale = 1.0;
                    }
                }

                SequentialAnimation {
                    running: faceStatusPill.visible && faceStatusPill.isScanning
                    loops: Animation.Infinite
                    onStopped: {
                        faceIcon.opacity = 1.0;
                        faceIcon.scale = 1.0;
                    }
                    ParallelAnimation {
                        NumberAnimation {
                            target: faceIcon
                            property: "opacity"
                            from: 1.0
                            to: 0.38
                            duration: 620
                            easing.type: Easing.InOutQuad
                        }
                        NumberAnimation {
                            target: faceIcon
                            property: "scale"
                            from: 1.0
                            to: 1.14
                            duration: 620
                            easing.type: Easing.InOutQuad
                        }
                    }
                    ParallelAnimation {
                        NumberAnimation {
                            target: faceIcon
                            property: "opacity"
                            from: 0.38
                            to: 1.0
                            duration: 620
                            easing.type: Easing.InOutQuad
                        }
                        NumberAnimation {
                            target: faceIcon
                            property: "scale"
                            from: 1.14
                            to: 1.0
                            duration: 620
                            easing.type: Easing.InOutQuad
                        }
                    }
                }
            }

            PlasmaComponents3.Label {
                text: faceStatusPill.statusLabel()
                textFormat: Text.PlainText
                font.pointSize: Kirigami.Theme.smallFont.pointSize + 1
                color: Kirigami.Theme.textColor
                opacity: faceStatusPill.isFailed ? 0.9 : 1.0
            }
        }

        HoverHandler {
            cursorShape: faceStatusPill.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        }
    }
}
