QT += core gui widgets charts
SOURCES += src/daoMonitorGUI.cpp
CONFIG += release
CONFIG += c++17

QMAKE_CXXFLAGS_DEBUG += -O0
QMAKE_CXXFLAGS_RELEASE += -O3

INCLUDEPATH += \
    include/ \
    /usr/include/qt5/QtWidgets \
    /usr/include/qt5 \
    /usr/include/qt5/QtCore \
    /usr/include/qt5/QtGui \
    /usr/include/qt5/QtCharts \
    /home/daouser/DAOROOT/include

LIBS += \
    -L/home/daouser/DAOROOT/lib \
    -lrt \
    -lQt5Charts \
    -lQt5Widgets \
    -lQt5Gui \
    -lQt5Core \
    -lyaml-cpp \
    -ldao \
    -ldaoProto \
    -ldaoNuma \
    -lnuma \
    -lprotobuf \
    -lpthread \
    -lzmq
