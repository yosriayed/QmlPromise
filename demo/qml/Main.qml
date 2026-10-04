import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QmlPromiseDemo

ApplicationWindow {
    id: root
    visible: true
    width: 720
    height: 640
    title: "QFuture to JS Promise Demo"
    color: "#1e1e2e"

    AsyncBackend {
        id: backend
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        // Title and Description
        Label {
            text: "QFuture / QPromise as JavaScript Promises in QML"
            font.pixelSize: 20
            font.bold: true
            color: "#cdd6f4"
        }

        Label {
            text: "C++ QtConcurrent::run and QFuture bridged to standard JS Promises (.then, .catch, .finally, Promise.all)."
            font.pixelSize: 13
            color: "#a6adc8"
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        // Live Animation to prove non-blocking UI
        Rectangle {
            Layout.fillWidth: true
            height: 48
            color: "#313244"
            radius: 8

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                Label {
                    text: "UI Animation Check (Non-blocking):"
                    color: "#cdd6f4"
                    font.bold: true
                }

                Rectangle {
                    id: pulseBox
                    width: 22
                    height: 22
                    radius: 4
                    color: "#89b4fa"

                    RotationAnimation on rotation {
                        from: 0
                        to: 360
                        duration: 1200
                        loops: Animation.Infinite
                        running: true
                    }
                }

                Label {
                    text: "Smoothly spinning while heavy C++ threads execute"
                    color: "#9399b2"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }
        }

        // Action Buttons Grid
        GridLayout {
            columns: 2
            rowSpacing: 12
            columnSpacing: 12
            Layout.fillWidth: true

            // Test 1: Fetch with .then()
            Button {
                id: btnGreeting
                text: "1. fetchGreeting() [.then]"
                Layout.fillWidth: true
                onClicked: {
                    btnGreeting.enabled = false;
                    outputLabel.text = "Fetching greeting from background thread (1.5s)...";

                    backend.fetchGreeting("Qt Developer", 1500)
                        .then(function(response) {
                            outputLabel.text = "Result:\n" + response;
                        })
                        .catch(function(err) {
                            outputLabel.text = "Error: " + err;
                        })
                        .finally(function() {
                            btnGreeting.enabled = true;
                        });
                }
            }

            // Test 2: Heavy CPU computation
            Button {
                id: btnFib
                text: "2. computeFibonacci(42) [.then]"
                Layout.fillWidth: true
                onClicked: {
                    btnFib.enabled = false;
                    outputLabel.text = "Computing Fibonacci(42) on C++ thread pool...";

                    backend.computeFibonacci(42)
                        .then(function(result) {
                            outputLabel.text = "Success!\nFibonacci(42) = " + result;
                        })
                        .catch(function(err) {
                            outputLabel.text = "Failed: " + err;
                        })
                        .finally(function() {
                            btnFib.enabled = true;
                        });
                }
            }

            // Test 3: Failure / Rejection handling
            Button {
                id: btnFail
                text: "3. failingOperation() [.catch]"
                Layout.fillWidth: true
                onClicked: {
                    btnFail.enabled = false;
                    outputLabel.text = "Calling operation that throws a C++ exception...";

                    backend.failingOperation()
                        .then(function(res) {
                            outputLabel.text = "Unexpected success: " + res;
                        })
                        .catch(function(error) {
                            outputLabel.text = "Successfully caught C++ exception in JS .catch():\n" + error;
                        })
                        .finally(function() {
                            btnFail.enabled = true;
                        });
                }
            }

            // Test 4: Void task
            Button {
                id: btnVoid
                text: "4. runVoidTask() [.then]"
                Layout.fillWidth: true
                onClicked: {
                    btnVoid.enabled = false;
                    outputLabel.text = "Executing void background task (1.2s)...";

                    backend.runVoidTask(1200)
                        .then(function() {
                            outputLabel.text = "Void background task completed successfully!";
                        })
                        .catch(function(err) {
                            outputLabel.text = "Error: " + err;
                        })
                        .finally(function() {
                            btnVoid.enabled = true;
                        });
                }
            }

            // Test 5: Promise.all parallel composition
            Button {
                id: btnAll
                text: "5. Promise.all([task1, task2])"
                Layout.fillWidth: true
                Layout.columnSpan: 2
                onClicked: {
                    btnAll.enabled = false;
                    outputLabel.text = "Starting 2 parallel tasks with Promise.all()...";

                    var p1 = backend.fetchGreeting("Task 1", 1000);
                    var p2 = backend.computeFibonacci(35);

                    Promise.all([p1, p2])
                        .then(function(results) {
                            outputLabel.text = "Promise.all resolved both!\n"
                                             + "Task 1: " + results[0] + "\n"
                                             + "Task 2 (Fib 35): " + results[1];
                        })
                        .catch(function(err) {
                            outputLabel.text = "One of the tasks failed: " + err;
                        })
                        .finally(function() {
                            btnAll.enabled = true;
                        });
                }
            }
        }

        // Output Display Box
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#181825"
            radius: 8
            border.color: "#45475a"
            border.width: 1

            ScrollView {
                anchors.fill: parent
                anchors.margins: 12

                Label {
                    id: outputLabel
                    text: "Ready. Click any button above to execute C++ QFuture via JavaScript Promises."
                    color: "#a6e3a1"
                    font.family: "Monospace"
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    width: parent.width
                }
            }
        }
    }
}
