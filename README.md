# QmlPromise

A lightweight, **header-only C++ library** that bridges Qt's `QFuture<T>` and `QPromise<T>` to native ECMAScript **JavaScript Promises (`QJSValue`)** in QML for **Qt 6.5+**.

---

## Why QmlPromise?

In Qt Quick / QML:
- Heavy operations on the GUI thread freeze animations and drop frames.
- `QFuture` and `QtConcurrent` offer great multithreading in C++, but Qt does **not** natively expose `QFuture` to QML as a JavaScript `Promise`.
- QML's JavaScript engine (V4) implements ES6 `Promise` (`.then()`, `.catch()`, `Promise.all()`), but lacks native ES2018 `.finally()` support and a clean, zero-boilerplate bridge from `QFuture`.

**`QmlPromise`** bridges `QFuture` directly to QML and automatically installs the ECMAScript-compliant `Promise.prototype.finally` polyfill so all standard promise chain methods work seamlessly.


### C++ Backend
```cpp
#include <QmlPromise/QmlPromise>

class Backend : public QObject
{
    Q_OBJECT
    QML_ELEMENT

public:
    Q_INVOKABLE QJSValue fetchData(const QString &query)
    {
        QFuture<QString> future = QtConcurrent::run([query]() {
            // Expensive computation or I/O in worker thread
            return QString("Result for " + query);
        });

        // Convert QFuture into a native JavaScript Promise
        return QmlPromise::fromFuture(this, future);
    }
};
```

### QML Consumption
```qml
// In your QML component
backend.fetchData("Qt 6")
    .then(function(result) {
        console.log("Success:", result);
    })
    .catch(function(error) {
        console.error("Failed:", error);
    })
    .finally(function() {
        busyIndicator.running = false;
    });

// Parallel composition with Promise.all
Promise.all([backend.fetchData("A"), backend.fetchData("B")])
    .then(function(results) {
        console.log("Both done:", results[0], results[1]);
    });
```

---

## Features

- **Header-only**: Just copy `include/QmlPromise/` into your project and `#include <QmlPromise/QmlPromise>`.
- **Zero Dependencies**: Pure Qt 6 (Core, Qml, Concurrent). No third-party dependencies, no external QML plugins to install.
- **Type-safe**: Works automatically with any type `T` supported by `QJSEngine::toScriptValue()` (primitives, `QString`, `QList`, custom structs registered with Qt's meta-type system).
- **Void Support**: Fully supports `QFuture<void>` tasks.
- **Guaranteed Thread Safety**: Schedules Promise resolution/rejection onto the QML GUI thread using independent `QFutureWatcher` observers owned by the JavaScript engine.
- **Automatic Error Propagation**: C++ exceptions and task cancellations are automatically forwarded to JavaScript's `.catch()` / rejection handlers.

---

## API Reference

All functions reside in the `QmlPromise` namespace:

```cpp
namespace QmlPromise {

// Converts a QFuture<T> into a JavaScript Promise
template <typename T>
QJSValue fromFuture(QObject *context, QFuture<T> future, QJSEngine *engine = nullptr);

// Converts a QFuture<void> into a JavaScript Promise
QJSValue fromFuture(QObject *context, QFuture<void> future, QJSEngine *engine = nullptr);

// Converts a QPromise<T> into a JavaScript Promise
template <typename T>
QJSValue fromPromise(QObject *context, const QPromise<T> &promise, QJSEngine *engine = nullptr);

// Alternative synonym
template <typename T>
QJSValue toPromise(QObject *context, QFuture<T> future, QJSEngine *engine = nullptr);

// Installs ECMAScript polyfills (e.g. Promise.prototype.finally) on the engine
// (Automatically called by toPromise/fromFuture, or can be called explicitly during engine startup)
void installPolyfills(QJSEngine *engine);

}

```

---

## Integration with CMake (FetchContent)

You can easily integrate **`QmlPromise`** into any CMake project via `FetchContent`:

```cmake
include(FetchContent)

FetchContent_Declare(
    QmlPromise
    GIT_REPOSITORY https://github.com/your-username/QmlPromise.git
    GIT_TAG        v1.0.0 # or main
)
FetchContent_MakeAvailable(QmlPromise)

# Link your application or QML module:
target_link_libraries(my_qml_app PRIVATE
    QmlPromise::QmlPromise
)
```

When consumed via `FetchContent`, example apps and tests are automatically disabled, leaving only the lightweight `INTERFACE` library.

---

## Requirements

- **C++20**
- **Qt 6.5+** (Core, Qml, Concurrent)
- CMake 3.20+

---

## Project Structure

```
.
├── CMakeLists.txt
├── include/
│   └── QmlPromise/
│       ├── QmlPromise          <-- Extensionless convenience header
│       └── qml_promise.h       <-- Header-only implementation
├── demo/
│   ├── CMakeLists.txt
│   ├── src/               <-- C++ backend and application loader
│   └── qml/
│       └── Main.qml       <-- Interactive QML demo UI
└── tests/
    └── test_qml_promise.cpp    <-- Automated unit test suite
```

---

## Building and Running

### 1. Build
```bash
cmake -B build -G Ninja
cmake --build build
```

### 2. Run the Interactive Demo
```bash
./build/examples/demo/appQmlPromiseDemo
```

### 3. Run Automated Tests
```bash
ctest --test-dir build --output-on-failure
```
