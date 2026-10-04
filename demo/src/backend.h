#pragma once

#include <QObject>
#include <QtQml/qqmlregistration.h>
#include <QtConcurrent/QtConcurrent>
#include <QThread>
#include <QJSValue>
#include <QmlPromise/QmlPromise>

class AsyncBackend : public QObject
{
    Q_OBJECT
    QML_ELEMENT

public:
    explicit AsyncBackend(QObject *parent = nullptr) : QObject(parent) {}

    // 1. Asynchronous task returning QString
    Q_INVOKABLE QJSValue fetchGreeting(const QString &name, int delayMs = 1500)
    {
        QFuture<QString> future = QtConcurrent::run([name, delayMs]() {
            QThread::msleep(delayMs);
            return QString("Hello, %1! (Processed asynchronously on thread %2)")
                .arg(name)
                .arg(reinterpret_cast<quintptr>(QThread::currentThreadId()));
        });

        return QmlPromise::fromFuture(this, future);
    }

    // 2. Asynchronous CPU-bound computation
    Q_INVOKABLE QJSValue computeFibonacci(int n)
    {
        QFuture<qint64> future = QtConcurrent::run([n]() -> qint64 {
            int count = n;
            if (count < 0) return 0;
            if (count > 45) count = 45;

            auto fib = [](auto self, int val) -> qint64 {
                if (val <= 1) return val;
                return self(self, val - 1) + self(self, val - 2);
            };

            return fib(fib, count);
        });

        return QmlPromise::fromFuture(this, future);
    }

    // 3. Asynchronous task that intentionally fails to test rejection
    Q_INVOKABLE QJSValue failingOperation()
    {
        QFuture<QString> future = QtConcurrent::run([]() -> QString {
            QThread::msleep(1000);
            throw std::runtime_error("Simulated failure: Database connection timed out!");
        });

        return QmlPromise::fromFuture(this, future);
    }

    // 4. Asynchronous void task
    Q_INVOKABLE QJSValue runVoidTask(int delayMs = 1200)
    {
        QFuture<void> future = QtConcurrent::run([delayMs]() {
            QThread::msleep(delayMs);
        });

        return QmlPromise::fromFuture(this, future);
    }
};
