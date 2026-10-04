#include <QCoreApplication>
#include <QTest>
#include <QJSEngine>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QtConcurrent/QtConcurrent>
#include "QmlPromise/QmlPromise"

struct NonDefaultResult
{
    explicit NonDefaultResult(int value) : value(value) {}
    int value;
};
Q_DECLARE_METATYPE(NonDefaultResult)

class TestQmlPromise : public QObject
{
    Q_OBJECT

public:
    Q_INVOKABLE QJSValue fetchAsyncGreeting(QJSEngine *engine = nullptr)
    {
        QFuture<QString> future = QtConcurrent::run([]() {
            QThread::msleep(20);
            return QString("QmlSuccess");
        });
        return QmlPromise::fromFuture(this, future, engine);
    }

private:
    template <typename T>
    void verifyIndependentObservers(int outcome)
    {
        QJSEngine engine;
        QObject context;
        QPromise<T> producer;
        producer.start();
        auto future = producer.future();
        auto continuation = future.then([](QFuture<T>) { return 123; });
        engine.globalObject().setProperty("p1", QmlPromise::fromFuture(&context, future, &engine));
        engine.globalObject().setProperty("p2", QmlPromise::fromPromise(&context, producer, &engine));
        QVERIFY(!engine.evaluate(
            "var first = 'pending', second = 'pending';"
            "p1.then(v => first = 'resolved', e => first = String(e));"
            "p2.then(v => second = 'resolved', e => second = String(e));"
        ).isError());

        if (outcome == 1) {
            producer.setException(std::make_exception_ptr(std::runtime_error("expected failure")));
        } else if (outcome == 2) {
            future.cancel();
        } else if (outcome == 3) {
            producer.setException(std::make_exception_ptr(42));
        } else if constexpr (!std::is_void_v<T>) {
            producer.addResult(42);
        }
        producer.finish();

        const QString expected = outcome == 0 ? QStringLiteral("resolved")
            : outcome == 1 ? QStringLiteral("expected failure")
            : outcome == 2 ? QStringLiteral("Operation was canceled.")
            : QStringLiteral("An unknown error occurred in the background task.");
        QTRY_COMPARE(engine.globalObject().property("first").toString(), expected);
        QTRY_COMPARE(engine.globalObject().property("second").toString(), expected);
        if (outcome == 0) {
            QTRY_VERIFY(continuation.isFinished());
            QCOMPARE(continuation.result(), 123);
        }
    }

    template <typename T>
    void verifyEngineDestruction()
    {
        QObject context;
        QPromise<T> producer;
        producer.start();
        auto *engine = new QJSEngine;
        auto promise = QmlPromise::fromPromise(&context, producer, engine);
        QVERIFY(promise.isObject());
        delete engine;
        if constexpr (!std::is_void_v<T>) {
            producer.addResult(QStringLiteral("completed after engine destruction"));
        }
        producer.finish();
        QCoreApplication::processEvents();
    }

private slots:
    void testIndependentObservers_data()
    {
        QTest::addColumn<int>("outcome");
        QTest::newRow("success") << 0;
        QTest::newRow("exception") << 1;
        QTest::newRow("cancellation") << 2;
        QTest::newRow("unknown exception") << 3;
    }

    void testIndependentObservers()
    {
        QFETCH(int, outcome);
        verifyIndependentObservers<int>(outcome);
        verifyIndependentObservers<void>(outcome);
    }

    void testEngineDestruction()
    {
        verifyEngineDestruction<QString>();
        verifyEngineDestruction<void>();
    }

    void testContextDestruction()
    {
        QJSEngine engine;
        auto *context = new QObject;
        QPromise<int> producer;
        producer.start();
        engine.globalObject().setProperty("promise", QmlPromise::fromPromise(context, producer, &engine));
        engine.evaluate("var settled = false; promise.then(() => settled = true, () => settled = true);");
        delete context;
        producer.addResult(42);
        producer.finish();
        QCoreApplication::processEvents();
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        QVERIFY(!engine.globalObject().property("settled").toBool());
        QVERIFY(engine.findChildren<QFutureWatcherBase *>().isEmpty());
    }

    void testNonDefaultConstructibleResult()
    {
        QJSEngine engine;
        QObject context;
        QPromise<NonDefaultResult> producer;
        producer.start();
        // Finish before observing to cover already-completed futures as well.
        producer.addResult(NonDefaultResult(73));
        producer.finish();
        engine.globalObject().setProperty("promise", QmlPromise::fromPromise(&context, producer, &engine));
        engine.evaluate("var done = false; var result; promise.then(v => { result = v; done = true; });");
        QTRY_VERIFY(engine.globalObject().property("done").toBool());
        const QVariant result = engine.globalObject().property("result").toVariant();
        QCOMPARE(result.metaType(), QMetaType::fromType<NonDefaultResult>());
        QCOMPARE(static_cast<const NonDefaultResult *>(result.constData())->value, 73);
    }

    void initTestCase() {}

    void testValuePromiseResolution()
    {
        QJSEngine engine;
        QObject context;

        QFuture<QString> future = QtConcurrent::run([]() {
            QThread::msleep(50);
            return QString("SuccessResult");
        });

        QJSValue promise = QmlPromise::fromFuture(&context, future, &engine);
        QVERIFY(!promise.isError());
        QVERIFY(promise.isObject());

        engine.globalObject().setProperty("myPromise", promise);
        engine.globalObject().setProperty("resolvedValue", "");
        engine.globalObject().setProperty("isDone", false);

        engine.evaluate(
            "myPromise.then(function(val) {"
            "    resolvedValue = val;"
            "    isDone = true;"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("isDone").toBool() == true, 2000);
        QCOMPARE(engine.globalObject().property("resolvedValue").toString(), QString("SuccessResult"));
    }

    void testVoidPromiseResolution()
    {
        QJSEngine engine;
        QObject context;

        QFuture<void> future = QtConcurrent::run([]() {
            QThread::msleep(50);
        });

        QJSValue promise = QmlPromise::toPromise(&context, future, &engine);
        QVERIFY(!promise.isError());

        engine.globalObject().setProperty("myPromise", promise);
        engine.globalObject().setProperty("isVoidDone", false);

        engine.evaluate(
            "myPromise.then(function() {"
            "    isVoidDone = true;"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("isVoidDone").toBool() == true, 2000);
    }

    void testPromiseRejectionOnException()
    {
        QJSEngine engine;
        QObject context;

        QFuture<QString> future = QtConcurrent::run([]() -> QString {
            QThread::msleep(50);
            throw std::runtime_error("Simulated Failure Message");
        });

        QJSValue promise = QmlPromise::fromFuture(&context, future, &engine);

        engine.globalObject().setProperty("myPromise", promise);
        engine.globalObject().setProperty("caughtError", "");
        engine.globalObject().setProperty("didFail", false);

        engine.evaluate(
            "myPromise.then(function(val) {"
            "    /* should not be called */"
            "}).catch(function(err) {"
            "    caughtError = String(err);"
            "    didFail = true;"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("didFail").toBool() == true, 2000);
        const QString errStr = engine.globalObject().property("caughtError").toString();
        QVERIFY(!errStr.isEmpty());
        QVERIFY(errStr.contains("std::exception") || errStr.contains("Simulated Failure Message"));
    }

    void testPromiseAllComposition()
    {
        QJSEngine engine;
        QObject context;

        QFuture<int> f1 = QtConcurrent::run([]() { return 10; });
        QFuture<int> f2 = QtConcurrent::run([]() { return 20; });

        QJSValue p1 = QmlPromise::fromFuture(&context, f1, &engine);
        QJSValue p2 = QmlPromise::fromFuture(&context, f2, &engine);

        engine.globalObject().setProperty("p1", p1);
        engine.globalObject().setProperty("p2", p2);
        engine.globalObject().setProperty("sumResult", 0);
        engine.globalObject().setProperty("allDone", false);

        engine.evaluate(
            "Promise.all([p1, p2]).then(function(values) {"
            "    sumResult = values[0] + values[1];"
            "    allDone = true;"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("allDone").toBool() == true, 2000);
        QCOMPARE(engine.globalObject().property("sumResult").toInt(), 30);
    }

    void testFinallyPropertyDescriptor()
    {
        QJSEngine engine;
        engine.evaluate("delete Promise.prototype.finally");
        QmlPromise::installPolyfills(&engine);
        const auto check = engine.evaluate(R"js(
            (() => {
                const descriptor = Object.getOwnPropertyDescriptor(Promise.prototype, 'finally');
                const promise = Promise.resolve(42);
                for (const key in promise) {
                    if (key === 'finally') return false;
                }
                return !descriptor.enumerable && descriptor.writable && descriptor.configurable;
            })()
        )js");
        QVERIFY2(!check.isError(), qPrintable(check.toString()));
        QVERIFY(check.toBool());
        const auto installed = engine.evaluate("Promise.prototype.finally");
        QmlPromise::installPolyfills(&engine);
        QVERIFY(installed.strictlyEquals(engine.evaluate("Promise.prototype.finally")));
    }

    void testFinallyIgnoresCustomResolve()
    {
        QJSEngine engine;
        engine.evaluate("delete Promise.prototype.finally");
        QmlPromise::installPolyfills(&engine);
        const auto setup = engine.evaluate(R"js(
            var outcome = 'pending';
            function CustomPromise(executor) { return new Promise(executor); }
            CustomPromise.resolve = function() { throw 'custom resolve must not run'; };
            var promise = Promise.resolve(42);
            promise.constructor = CustomPromise;
            // Changing the public intrinsic after installation must not affect finally either.
            Promise.resolve = CustomPromise.resolve;
            promise.finally(() => undefined).then(
                value => outcome = String(value), reason => outcome = String(reason));
        )js");
        QVERIFY2(!setup.isError(), qPrintable(setup.toString()));
        QTRY_COMPARE(engine.globalObject().property("outcome").toString(), QStringLiteral("42"));
    }

    void testFinallySpecies()
    {
        QJSEngine engine;
        engine.evaluate("delete Promise.prototype.finally");
        QmlPromise::installPolyfills(&engine);
        const auto setup = engine.evaluate(R"js(
            var outcome = 'pending', constructions = 0;
            function Species(executor) { ++constructions; return new Promise(executor); }
            Species.resolve = function() { throw 'species resolve must not run'; };
            var constructor = {};
            constructor[Symbol.species] = Species;
            // A generic receiver isolates finally's species handling from Qt's native then.
            var receiver = { constructor: constructor, then: function(resolve) { return resolve(42); } };
            Promise.prototype.finally.call(receiver, () => ({ then: resolve => resolve('cleanup') }))
                .then(value => outcome = String(value), reason => outcome = String(reason));
        )js");
        QVERIFY2(!setup.isError(), qPrintable(setup.toString()));
        QTRY_COMPARE(engine.globalObject().property("outcome").toString(), QStringLiteral("42"));
        QCOMPARE(engine.globalObject().property("constructions").toInt(), 1);
        const auto invalid = engine.evaluate(R"js(
            (() => {
                constructor[Symbol.species] = () => {};
                try { Promise.prototype.finally.call(receiver, null); }
                catch (error) { return error instanceof TypeError; }
                return false;
            })()
        )js");
        QVERIFY2(!invalid.isError(), qPrintable(invalid.toString()));
        QVERIFY(invalid.toBool());
    }

    void testPromiseFinallyResolved()
    {
        QJSEngine engine;
        QObject context;

        QFuture<QString> future = QtConcurrent::run([]() {
            QThread::msleep(20);
            return QString("FinallySuccess");
        });

        QJSValue promise = QmlPromise::fromFuture(&context, future, &engine);
        engine.globalObject().setProperty("myPromise", promise);
        engine.globalObject().setProperty("finallyCalled", false);
        engine.globalObject().setProperty("passedThroughValue", "");

        engine.evaluate(
            "myPromise"
            ".finally(function() {"
            "    finallyCalled = true;"
            "})"
            ".then(function(val) {"
            "    passedThroughValue = val;"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("finallyCalled").toBool() == true, 2000);
        QCOMPARE(engine.globalObject().property("passedThroughValue").toString(), QString("FinallySuccess"));
    }

    void testPromiseFinallyRejected()
    {
        QJSEngine engine;
        QObject context;

        QFuture<QString> future = QtConcurrent::run([]() -> QString {
            QThread::msleep(20);
            throw std::runtime_error("Simulated Failure For Finally");
        });

        QJSValue promise = QmlPromise::fromFuture(&context, future, &engine);
        engine.globalObject().setProperty("myPromise", promise);
        engine.globalObject().setProperty("finallyCalled", false);
        engine.globalObject().setProperty("caughtError", "");

        engine.evaluate(
            "myPromise"
            ".finally(function() {"
            "    finallyCalled = true;"
            "})"
            ".catch(function(err) {"
            "    caughtError = String(err);"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("finallyCalled").toBool() == true, 2000);
        const QString errStr = engine.globalObject().property("caughtError").toString();
        QVERIFY(!errStr.isEmpty());
        QVERIFY(errStr.contains("std::exception") || errStr.contains("Simulated Failure For Finally"));
    }

    void testPromiseChainedThenCatchFinally()
    {
        QJSEngine engine;
        QObject context;

        QFuture<int> future = QtConcurrent::run([]() {
            QThread::msleep(20);
            return 42;
        });

        QJSValue promise = QmlPromise::fromFuture(&context, future, &engine);
        engine.globalObject().setProperty("myPromise", promise);
        engine.globalObject().setProperty("thenExecuted", false);
        engine.globalObject().setProperty("catchExecuted", false);
        engine.globalObject().setProperty("finallyExecuted", false);

        engine.evaluate(
            "myPromise"
            ".then(function(res) {"
            "    thenExecuted = (res === 42);"
            "})"
            ".catch(function(err) {"
            "    catchExecuted = true;"
            "})"
            ".finally(function() {"
            "    finallyExecuted = true;"
            "});"
        );

        QTRY_VERIFY_WITH_TIMEOUT(engine.globalObject().property("finallyExecuted").toBool() == true, 2000);
        QVERIFY(engine.globalObject().property("thenExecuted").toBool());
        QVERIFY(!engine.globalObject().property("catchExecuted").toBool());
    }

    void testPromiseFinallyInQml()
    {
        QQmlEngine engine;
        engine.rootContext()->setContextProperty(QStringLiteral("backend"), this);

        QQmlComponent component(&engine);
        component.setData(
            "import QtQuick\n"
            "QtObject {\n"
            "    property bool finallyDone: false\n"
            "    property string result: ''\n"
            "    Component.onCompleted: {\n"
            "        backend.fetchAsyncGreeting()\n"
            "            .then(function(res) { result = res; })\n"
            "            .catch(function(err) {})\n"
            "            .finally(function() { finallyDone = true; });\n"
            "    }\n"
            "}\n",
            QUrl()
        );

        QScopedPointer<QObject> obj(component.create());
        QVERIFY(!obj.isNull());
        QTRY_VERIFY_WITH_TIMEOUT(obj->property("finallyDone").toBool() == true, 2000);
        QCOMPARE(obj->property("result").toString(), QString("QmlSuccess"));
    }
};

QTEST_GUILESS_MAIN(TestQmlPromise)
#include "test_qml_promise.moc"
