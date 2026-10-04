#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QmlPromise/QmlPromise>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    app.setApplicationName("QmlPromiseDemo");
    app.setOrganizationName("QtDemo");

    QQuickStyle::setStyle("Basic");

    QQmlApplicationEngine engine;
    QmlPromise::installFinallyPolyfill(&engine);

    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreationFailed,
        &app,
        []() { QCoreApplication::exit(-1); },
        Qt::QueuedConnection);

    engine.loadFromModule("QmlPromiseDemo", "Main");

    return app.exec();
}
