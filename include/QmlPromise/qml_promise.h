#pragma once

#include <QFuture>
#include <QFutureWatcher>
#include <QPromise>
#include <QJSEngine>
#include <QJSValue>
#include <QPointer>
#include <exception>
#include <type_traits>

namespace QmlPromise {


/**
 * @brief Installs ECMAScript polyfills (e.g. Promise.prototype.finally) on the given engine.
 * Automatically invoked by toPromise/fromFuture, but can also be called explicitly during engine setup.
 */
inline void installPolyfills(QJSEngine *engine)
{
    if (!engine) {
        return;
    }

    engine->evaluate(
        QStringLiteral(
            R"js(
                (() => {
                    if (typeof Promise === 'undefined' || typeof Promise.prototype.finally === 'function') {
                        return;
                    }
                    const NativePromise = Promise;
                    const promiseResolve = NativePromise.resolve;
                    Object.defineProperty(NativePromise.prototype, 'finally', {
                        configurable: true,
                        writable: true,
                        enumerable: false,
                        value: function(callback) {
                            'use strict';
                            if (this === null || (typeof this !== 'object' && typeof this !== 'function')) {
                                throw new TypeError('Promise.finally requires an object');
                            }
                            // SpeciesConstructor: the constructor's static resolve is not consulted.
                            let C = NativePromise;
                            const constructor = this.constructor;
                            if (constructor !== undefined) {
                                if (constructor === null ||
                                    (typeof constructor !== 'object' && typeof constructor !== 'function')) {
                                    throw new TypeError('Invalid promise constructor');
                                }
                                const species = constructor[Symbol.species];
                                if (species !== undefined && species !== null) {
                                    // Validate constructibility even for a non-callable callback.
                                    Reflect.construct(function() {}, [], species);
                                    C = species;
                                }
                            }
                            if (typeof callback !== 'function') {
                                return this.then(callback, callback);
                            }
                            // The captured intrinsic implements PromiseResolve(C, result), including
                            // thenable assimilation, without invoking a custom C.resolve method.
                            return this.then(
                                value => promiseResolve.call(C, callback()).then(() => value),
                                reason => promiseResolve.call(C, callback()).then(() => { throw reason; })
                            );
                        }
                    });
                })();
            )js"
        )
    );
}

namespace detail {

inline bool createPromiseResolvers(QJSEngine *engine, QJSValue &promiseOut, QJSValue &resolveOut, QJSValue &rejectOut)
{
    if (!engine) {
        return false;
    }

    installPolyfills(engine);

    // Standard deferred/promise-with-resolvers pattern
    QJSValue helper = engine->evaluate(
        QStringLiteral(
            R"js(
                (() => {
                    let resolve, reject;
                    const promise = new Promise((res, rej) => {
                        resolve = res;
                        reject = rej;
                    });
                    return { promise, resolve, reject };
                })()
            )js"
        )
    );

    if (helper.isError() || !helper.isObject()) {
        return false;
    }

    promiseOut = helper.property(QStringLiteral("promise"));
    resolveOut = helper.property(QStringLiteral("resolve"));
    rejectOut = helper.property(QStringLiteral("reject"));

    return promiseOut.isObject() && resolveOut.isCallable() && rejectOut.isCallable();
}

} // namespace detail

/**
 * @brief Converts a QFuture<T> to a native JavaScript Promise (QJSValue) in QML.
 * 
 * @tparam T The result type of the QFuture.
 * @param context The QObject context (must live in the GUI/QML thread, typically 'this').
 * @param future The QFuture to observe (passed by value as QFuture is lightweight).
 * @param engine Optional explicit QJSEngine pointer. If null, qjsEngine(context) is used.
 * @return QJSValue A JavaScript Promise that resolves when the future finishes or rejects on error.
 */
template <typename T>
QJSValue toPromise(QObject *context, QFuture<T> future, QJSEngine *engine = nullptr)
{
    if (!context) {
        qWarning("QmlPromise::toPromise: A context object is required.");
        return QJSValue();
    }
    if (!engine) {
        engine = qjsEngine(context);
    }
    if (!engine) {
        qWarning("QmlPromise::toPromise: Unable to locate QJSEngine from context.");
        return QJSValue();
    }

    QJSValue promise, resolve, reject;
    if (!detail::createPromiseResolvers(engine, promise, resolve, reject)) {
        qWarning("QmlPromise::toPromise: Failed to initialize JavaScript Promise.");
        return QJSValue();
    }

    // Each bridge observes independently, leaving the future's continuation slot free.
    // Parenting to the engine prevents callbacks from outliving the JS runtime.
    auto *watcher = new QFutureWatcher<T>(engine);
    const QPointer<QObject> guardedContext(context);
    if (context) {
        QObject::connect(context, &QObject::destroyed, watcher, &QObject::deleteLater);
    }
    QObject::connect(watcher, &QFutureWatcher<T>::finished, watcher,
                     [watcher, guardedContext, engine, resolve, reject]() mutable {
        watcher->deleteLater();
        if (!guardedContext) {
            return;
        }

        auto completed = watcher->future();
        try {
            // Exceptions also mark a future canceled; rethrow them before testing cancellation.
            completed.waitForFinished();
            if (completed.isCanceled()) {
                reject.call({ QStringLiteral("Operation was canceled.") });
            } else if constexpr (std::is_void_v<T>) {
                resolve.call();
            } else {
                if (completed.resultCount() == 0) {
                    reject.call({ QStringLiteral("Operation finished without a result.") });
                    return;
                }
                resolve.call({ engine->toScriptValue(completed.result()) });
            }
        } catch (const std::exception &e) {
            reject.call({ QString::fromUtf8(e.what()) });
        } catch (...) {
            reject.call({ QStringLiteral("An unknown error occurred in the background task.") });
        }
    });
    watcher->setFuture(future);

    return promise;
}

/**
 * @brief Overload accepting a QPromise<T> directly.
 */
template <typename T>
QJSValue toPromise(QObject *context, const QPromise<T> &promise, QJSEngine *engine = nullptr)
{
    return toPromise(context, promise.future(), engine);
}

/**
 * @brief Alias for toPromise (reads naturally as QmlPromise::fromFuture(this, future)).
 */
template <typename T>
inline QJSValue fromFuture(QObject *context, QFuture<T> future, QJSEngine *engine = nullptr)
{
    return toPromise(context, future, engine);
}

template <typename T>
inline QJSValue fromPromise(QObject *context, const QPromise<T> &promise, QJSEngine *engine = nullptr)
{
    return toPromise(context, promise.future(), engine);
}

} // namespace QmlPromise
