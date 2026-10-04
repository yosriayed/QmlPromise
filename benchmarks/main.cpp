#include <QCoreApplication>
#include <QElapsedTimer>
#include <QEvent>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QThreadPool>
#include <QtConcurrentRun>
#include <QmlPromise/QmlPromise>
#include <algorithm>
#include <array>
#include <cstdio>
#include <memory>
#include <random>

class Backend : public QObject
{
    Q_OBJECT
public:
    explicit Backend(QJSEngine *engine) : engine(engine) { pool.setMaxThreadCount(4); }
    ~Backend() override { pool.waitForDone(); }

    Q_INVOKABLE void queuedSignal(int value, int workload)
    {
        auto deliver = [this, value] {
            QMetaObject::invokeMethod(this, [this, value] { emit done(value); }, Qt::QueuedConnection);
        };
        if (workload == 2)
            (void)QtConcurrent::run(&pool, deliver);
        else
            deliver();
    }

    Q_INVOKABLE void watcherSignal(int value, int workload)
    {
        auto *watcher = new QFutureWatcher<int>(this);
        connect(watcher, &QFutureWatcher<int>::finished, watcher, [this, watcher] {
            emit done(watcher->result());
            watcher->deleteLater();
        });
        watcher->setFuture(makeFuture(value, workload));
    }

    Q_INVOKABLE void watcherCallback(int value, int workload, QJSValue callback)
    {
        auto *watcher = new QFutureWatcher<int>(this);
        connect(watcher, &QFutureWatcher<int>::finished, watcher, [watcher, callback]() mutable {
            callback.call({watcher->result()});
            watcher->deleteLater();
        });
        watcher->setFuture(makeFuture(value, workload));
    }

    Q_INVOKABLE void continuationSignal(int value, int workload)
    {
        (void)makeFuture(value, workload).then(this, [this](int result) { emit done(result); });
    }

    Q_INVOKABLE QJSValue promiseResult(int value, int workload)
    {
        return QmlPromise::fromFuture(this, makeFuture(value, workload), engine);
    }

    void waitForWorkers() { pool.waitForDone(); }

signals:
    void done(int value);

private:
    QFuture<int> makeFuture(int value, int workload)
    {
        if (workload == 2)
            return QtConcurrent::run(&pool, [value] { return value; });
        if (workload == 0)
            return QtFuture::makeReadyValueFuture(value);
        auto producer = std::make_shared<QPromise<int>>();
        producer->start();
        auto future = producer->future();
        QMetaObject::invokeMethod(this, [producer, value] {
            producer->addResult(value);
            producer->finish();
        }, Qt::QueuedConnection);
        return future;
    }

    QJSEngine *engine;
    QThreadPool pool;
};

static constexpr auto qml = R"qml(
import QtQml
QtObject {
    property int completed: 0
    property double sum: 0
    property var seen: ({})
    property bool valid: true
    function accept(value) {
        // Validate every delivery, including duplicate/missing values.
        if (seen[value]) valid = false
        seen[value] = true
        sum += value
        completed++
    }
    Component.onCompleted: backend.done.connect(accept)
    function start(mode, count, workload) {
        completed = 0
        sum = 0
        seen = ({})
        valid = true
        switch (mode) {
        case 0:
            for (let i = 1; i <= count; ++i) backend.queuedSignal(i, workload)
            break
        case 1:
            for (let i = 1; i <= count; ++i) backend.watcherSignal(i, workload)
            break
        case 2:
            for (let i = 1; i <= count; ++i) backend.watcherCallback(i, workload, accept)
            break
        case 3:
            for (let i = 1; i <= count; ++i) backend.continuationSignal(i, workload)
            break
        case 4:
            for (let i = 1; i <= count; ++i) backend.promiseResult(i, workload).then(accept)
            break
        }
    }
}
)qml";

struct Sample { double setupUs; double totalUs; };

static Sample run(QObject *root, Backend &backend, QQmlEngine &engine, int mode, int workload, int batch, int operations)
{
    qint64 setupNs = 0;
    QElapsedTimer total;
    total.start();
    for (int offset = 0; offset < operations; offset += batch) {
        QElapsedTimer setup;
        setup.start();
        if (!QMetaObject::invokeMethod(root, "start", Q_ARG(QVariant, mode),
                                      Q_ARG(QVariant, batch), Q_ARG(QVariant, workload)))
            qFatal("Cannot invoke QML workload");
        setupNs += setup.nsecsElapsed();
        QElapsedTimer timeout;
        timeout.start();
        while (root->property("completed").toInt() < batch) {
            QCoreApplication::processEvents(QEventLoop::AllEvents);
            if (timeout.elapsed() > 10000)
                qFatal("Timed out waiting for results");
        }
        if (root->property("completed").toInt() != batch ||
            root->property("sum").toDouble() != batch * (batch + 1) / 2.0 ||
            !root->property("valid").toBool())
            qFatal("Wrong results");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    }
    backend.waitForWorkers();
    engine.collectGarbage();
    return {setupNs / (1000.0 * operations), total.nsecsElapsed() / (1000.0 * operations)};
}

static void microbench(QQmlEngine &engine)
{
    QmlPromise::installFinallyPolyfill(&engine);
    auto factory = engine.evaluate(R"js(
        (function() {
            let resolve, reject;
            const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
            return {promise, resolve, reject};
        })
    )js");
    const char *names[] = {"polyfill_check", "current_resolver_factory", "cached_factory_call"};
    std::puts("component,repeat,operations,loop_us_per_op,total_us_per_op");
    for (int repeat = -1; repeat < 7; ++repeat) {
        for (int mode = 0; mode < 3; ++mode) {
            engine.collectGarbage();
            QElapsedTimer timer;
            timer.start();
            constexpr int count = 2048;
            for (int i = 0; i < count; ++i) {
                if (mode == 0) {
                    QmlPromise::installFinallyPolyfill(&engine);
                } else if (mode == 1) {
                    QJSValue promise, resolve, reject;
                    if (!QmlPromise::detail::createPromiseResolvers(&engine, promise, resolve, reject))
                        qFatal("Cannot create promise");
                } else {
                    auto result = factory.call();
                    if (!result.property("promise").isObject() ||
                        !result.property("resolve").isCallable() ||
                        !result.property("reject").isCallable())
                        qFatal("Cannot call cached factory");
                }
                if ((i + 1) % 64 == 0) {
                    QCoreApplication::processEvents(QEventLoop::AllEvents);
                    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
                }
            }
            const double loopUs = timer.nsecsElapsed() / (1000.0 * count);
            engine.collectGarbage();
            if (repeat >= 0)
                std::printf("%s,%d,%d,%.6f,%.6f\n", names[mode], repeat, count, loopUs,
                            timer.nsecsElapsed() / (1000.0 * count));
        }
    }
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    std::fprintf(stderr, "Qt %s; compiler %s; pool=4; Release build recommended\n", qVersion(), __VERSION__);
    QQmlEngine engine;
    if (app.arguments().contains("--micro")) {
        microbench(engine);
        return 0;
    }
    Backend backend(&engine);
    engine.rootContext()->setContextProperty("backend", &backend);
    QQmlComponent component(&engine);
    component.setData(qml, QUrl("benchmark.qml"));
    std::unique_ptr<QObject> root(component.create());
    if (!root) qFatal("QML error: %s", qPrintable(component.errorString()));

    const char *names[] = {"queued_signal", "watcher_signal", "watcher_callback", "continuation_signal", "qmlpromise"};
    const char *workloads[] = {"ready", "pending", "worker"};
    std::mt19937 random(20261004);
    std::puts("workload,batch,method,repeat,operations,setup_us_per_op,total_us_per_op,ops_per_second");
    for (int workload = 0; workload < 3; ++workload) {
        for (int batch : {1, 64}) {
            for (int repeat = -1; repeat < 7; ++repeat) {
                std::array<int, 5> order{0, 1, 2, 3, 4};
                std::shuffle(order.begin(), order.end(), random);
                for (int mode : order) {
                    engine.collectGarbage();
                    const int operations = repeat < 0 ? 128 : (batch == 1 ? 256 : 2048);
                    const auto sample = run(root.get(), backend, engine, mode, workload, batch, operations);
                    if (repeat >= 0)
                        std::printf("%s,%d,%s,%d,%d,%.6f,%.6f,%.1f\n", workloads[workload], batch,
                                    names[mode], repeat, operations, sample.setupUs, sample.totalUs,
                                    1e6 / sample.totalUs);
                }
            }
        }
    }
}

#include "main.moc"
