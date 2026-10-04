#pragma once

#include <QFuture>
#include <QFutureWatcher>
#include <QPromise>
#include <QJSEngine>
#include <QJSValue>
#include <QPointer>
#include <QVariant>
#include <QException>
#include <exception>
#include <type_traits>

namespace QmlPromise {


/**
 * @brief Installs Promise.prototype.finally on the given engine if it is missing.
 * Call explicitly on the engine thread before using .finally(); conversion does not install it.
 */
inline void installFinallyPolyfill(QJSEngine *engine)
{
    if (!engine) {
        return;
    }

    // Inspect the existing method without parsing/evaluating the polyfill again.
    // Keep explicit installation useful if application code removes the method.
    if (engine->globalObject().property(QStringLiteral("Promise"))
            .property(QStringLiteral("prototype"))
            .property(QStringLiteral("finally")).isCallable()) {
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

    // An engine-owned QJSValue keeps the compiled function alive across GC and
    // cannot outlive its engine or be reused accidentally by a different engine.
    // Use a QObject dynamic property, not a property of the JavaScript global object.
    constexpr auto cacheKey = "_qmlpromise_v1_resolverFactory";
    QJSValue factory = engine->property(cacheKey).value<QJSValue>();
    if (!factory.isCallable()) {
        factory = engine->evaluate(
            QStringLiteral(
                R"js(
                    (() => {
                        let resolve, reject;
                        const promise = new Promise((res, rej) => {
                            resolve = res;
                            reject = rej;
                        });
                        return [promise, resolve, reject];
                    })
                )js"
            )
        );
        if (!factory.isCallable()) {
            return false;
        }
        engine->setProperty(cacheKey, QVariant::fromValue(factory));
    }

    // Each call creates a fresh promise and independent resolve/reject functions.
    QJSValue helper = factory.call();

    if (helper.isError() || !helper.isObject()) {
        return false;
    }

    if (helper.isArray()) {
        promiseOut = helper.property(0);
        resolveOut = helper.property(1);
        rejectOut = helper.property(2);
    } else {
        promiseOut = helper.property(QStringLiteral("promise"));
        resolveOut = helper.property(QStringLiteral("resolve"));
        rejectOut = helper.property(QStringLiteral("reject"));
    }

    return promiseOut.isObject() && resolveOut.isCallable() && rejectOut.isCallable();
}

template <typename Val>
inline QJSValue toScriptValueHelper(QJSEngine *engine, Val &&val)
{
    using Decayed = std::decay_t<Val>;
    if constexpr (std::is_same_v<Decayed, QJSValue>) {
        return std::forward<Val>(val);
    } else if constexpr (std::is_same_v<Decayed, int> ||
                          std::is_same_v<Decayed, uint> ||
                          std::is_same_v<Decayed, double> ||
                          std::is_same_v<Decayed, bool> ||
                          std::is_same_v<Decayed, QString>) {
        return QJSValue(std::forward<Val>(val));
    } else {
        return engine->toScriptValue(std::forward<Val>(val));
    }
}

template <typename T>
inline void settlePromise(QJSEngine *engine, QFuture<T> future, const QJSValue &resolve, const QJSValue &reject)
{
    try {
        // Exceptions also mark a future canceled; rethrow them before testing cancellation.
        future.waitForFinished();
        if (future.isCanceled()) {
            reject.call({ QStringLiteral("Operation was canceled.") });
        } else if constexpr (std::is_void_v<T>) {
            resolve.call();
        } else {
            if (future.resultCount() == 0) {
                reject.call({ QStringLiteral("Operation finished without a result.") });
                return;
            }
            resolve.call({ toScriptValueHelper(engine, future.result()) });
        }
    } catch (const QUnhandledException &ue) {
        if (ue.exception()) {
            try {
                std::rethrow_exception(ue.exception());
            } catch (const std::exception &inner) {
                reject.call({ QString::fromUtf8(inner.what()) });
            } catch (...) {
                reject.call({ QStringLiteral("An unknown error occurred in the background task.") });
            }
        } else {
            reject.call({ QString::fromUtf8(ue.what()) });
        }
    } catch (const std::exception &e) {
        reject.call({ QString::fromUtf8(e.what()) });
    } catch (...) {
        reject.call({ QStringLiteral("An unknown error occurred in the background task.") });
    }
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

    // Fast-path: if the future is already completed, settle the Promise immediately
    // without allocating a QFutureWatcher, setting up signal-slot connections, or
    // posting deferred deletion events to the event loop.
    if (future.isFinished()) {
        detail::settlePromise(engine, future, resolve, reject);
        return promise;
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

        detail::settlePromise(engine, watcher->future(), resolve, reject);
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
