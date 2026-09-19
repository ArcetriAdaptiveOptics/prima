/**
 * @author Thomas Davies
 * @date 26/06/2025
 * @brief Dao latency GUI (DLG)
**/

/* ===== INCLUDES ===== */

#include "CLI11.hpp"
#include <string>
#include <daoLog.hpp>
#include <daoShmIfce.hpp>
#include <yaml-cpp/yaml.h>

#include <QFont>
#include <QChar>
#include <QAreaSeries>
#include <QLineSeries>
#include <QChartView>
#include <QPainter>
#include <QGraphicsView>
#include <QValueAxis>
#include <QChart>
#include <QMetaType>
#include <QApplication>
#include <QWidget>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QObject>
#include <QThread>
#include <QString>
#include <QPen>

/* ===== CODE ===== */

struct context_t {
    float series_yclip = 1000.0f;
    size_t ptsize = 12;
    size_t refresh_rate = 5;
    size_t hist_density = 100;
    size_t buffer_capacity = 1000;
    std::string latency_shm = "/tmp/dlt-latency.im.shm";
    std::string plot_colour = "#b41bcc";
    bool display = false;

    void print() {
        if (display) {
            printf("GUI Refresh Rate    : %zu hz\n", refresh_rate);
            printf("Histogram Buckets   : %zu\n", hist_density);
            printf("Buffer Capacity     : %zu samples\n", buffer_capacity);
            printf("Latency SHM         : %s\n", latency_shm.c_str());
            printf("Series Y-Clip       : %f\n", series_yclip);
            printf("Plotting Colour     : %s\n", plot_colour.c_str());
            printf("Font Size           : %zu\n", ptsize);
        }
    }
};

struct draw_context {
    QVector<double> latencies;    // Buffer of latencies
    QVector<uint64_t> frame_ids; // Corresponding latency RTC frame ids.
    size_t accumulated = 0;      // Number of total latencies read.
    size_t missed = 0;           // Number of latency shm frames missed.
    int i = 0;                // buffer write position
};
Q_DECLARE_METATYPE(draw_context)

class accumulator_t : public QObject {
    Q_OBJECT
public:
    accumulator_t(const context_t &acxt) :
        m_log("accumulator", Dao::Log::Logger::DESTINATION::SCREEN),
        m_acxt(acxt), m_shmi(nullptr) {
        m_shmi = new Dao::ShmIfce<double>(m_log);
        m_shmi->OpenShm(acxt.latency_shm, &m_shm);
        m_gcxt.frame_ids.resize(acxt.buffer_capacity);
        m_gcxt.latencies.resize(acxt.buffer_capacity);
    }

public slots:
    void run() {
        auto &i = m_gcxt.i;
        const size_t redraw_delay = 1000 / m_acxt.refresh_rate;
        auto t0 = std::chrono::steady_clock::now();
        auto cnt0 = m_shmi->GetFrameCounter();
        auto &fids = m_gcxt.frame_ids;
        auto &lats = m_gcxt.latencies;

        while (true) {
            /* ---- await new frame ---- */
            const volatile uint64_t *pcnt0_ = (const volatile uint64_t *)(&m_shm.md->cnt0);
            const volatile uint64_t cnt0_ = *pcnt0_;
            const auto dcnt0 = cnt0_ - cnt0;
            cnt0 = cnt0_;
            if (!dcnt0) {
                continue; // frame not ready.
            }

            /* ---- accumulate frame into ring buffer ---- */
            const double lat = *m_shmi->GetPtr() * 1e6; // sec -> us.
            fids[i] = m_gcxt.accumulated;
            lats[i] = lat; 
            m_gcxt.missed += dcnt0 - 1;
            i = (i + 1) % m_acxt.buffer_capacity;
            ++m_gcxt.accumulated;

            /* ---- issue redraw ---- */
            const auto t1 = std::chrono::steady_clock::now();
            const size_t elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();
            if (elapsed > redraw_delay) {
                emit redraw(m_gcxt);
                t0 = std::chrono::steady_clock::now();
            }
        }
    }

signals:
    void redraw(const draw_context gcxt);

private:
    Dao::Log::Logger m_log;
    const context_t &m_acxt;
    Dao::ShmIfce<double> *m_shmi;
    draw_context m_gcxt;
    IMAGE m_shm;
};

class gui_t : public QObject {
    Q_OBJECT
public:
    gui_t(const context_t &acxt) :
        m_acxt(acxt), m_inspecting(false), m_unit(0x03bc) {
        m_metrics_tmpl =
            "Accumulated frames: %2<br>"
            "Missed frames: %3<br>"
            "Mean: %4 %1s<br>"
            "Min: %5 %1s<br>"
            "Max: %6 %1s<br>"
            "Stdev: %7 %1s";

        m_fnt.setPointSize(acxt.ptsize);
    }

    void create() {
        QVBoxLayout *info_l = create_info_panel();
        QVBoxLayout *charts_l = create_charts_panel();

        QHBoxLayout *layout = new QHBoxLayout();
        layout->addLayout(info_l);
        layout->addLayout(charts_l);
        m_gui.setLayout(layout);
        m_gui.setMinimumSize(960, 600);
        m_gui.show();
    }

public slots:
    void redraw(const draw_context gcxt) {
        if (m_inspecting) return;
        update_info_panel(gcxt);
        update_series_chart(m_acxt, gcxt);
        update_hist_chart(gcxt);
    }

private:
    void update_info_panel(const draw_context &gcxt) {
        auto &lats = gcxt.latencies;
        const auto &[lmin, lmax] = std::minmax_element(lats.begin(), lats.end());

        // calc mean..
        float mean = 0.0f;
        for (int i = 0; i < lats.size(); ++i) mean += lats[i];
        mean /= lats.size();

        // calc stdev..
        float stdev = 0.0f;
        for (int i = 0; i < lats.size(); ++i) {
            float x = lats[i] - mean;
            stdev += x * x;
        }
        stdev /= lats.size();

        // update label..
        m_metrics_lbl->setText(
            m_metrics_tmpl
            .arg(m_unit)
            .arg(gcxt.accumulated)
            .arg(gcxt.missed)
            .arg(mean)
            .arg(*lmin)
            .arg(*lmax)
            .arg(stdev)
        );
    }

    void update_series_chart(const context_t &cxt, const draw_context &gcxt) {
        QVector<QPointF> d0, d1;
        auto &fids = gcxt.frame_ids;
        auto &lats = gcxt.latencies;

        const auto &[fmin, fmax] = std::minmax_element(fids.begin(), fids.end());
        const auto &[lmin, lmax] = std::minmax_element(lats.begin(), lats.end());

        for (int j = 0; j < gcxt.i; ++j) d0.push_back(QPointF(fids[j], lats[j]));
        for (int j = gcxt.i; j < fids.size(); ++j) d1.push_back(QPointF(fids[j], lats[j]));
        if (d0.size() && d1.size()) d1.append(d0.front()); // stitch plots togther.

        m_asx->setRange(*fmin, *fmax);
        m_asy->setRange(
            *lmin, 
            std::min<double>(*lmax, cxt.series_yclip)
        );

        m_s0->replace(d0);
        m_s1->replace(d1);
    }

    void update_hist_chart(const draw_context &gcxt) {
        // calc histogram..
        size_t &n_buckets = m_acxt.hist_density;
        auto data = gcxt.latencies; // copy for sort.
        QVector<double> centres;
        QVector<size_t> counts;

        // calc buckets..
        std::sort(data.begin(), data.end());
        auto d_min = data.front();
        auto d_max = data.back();
        auto b_width = (d_max - d_min) / n_buckets;
        centres.reserve(n_buckets);
        counts.reserve(n_buckets);

        // determine counts..
        int n = 0;
        auto b_min = d_min;
        for (size_t i = 0; i < n_buckets; ++i) {
            float b_max = b_min + b_width;

            size_t bin_cnt = 0;
            for (int j = 0; j < data.size(); ++j) {
                const auto &val = data[j];
                if (i == (n_buckets - 1) && val == d_max) ++bin_cnt; // includes (repeated) max vals in final bucket. 
                else if ((val >= b_min && val < b_max)) ++bin_cnt;
            }

            centres.push_back(b_min + b_width / 2.0f);
            counts.push_back(bin_cnt);
            b_min = b_max;
            n += bin_cnt;
        }
        // assert(n == data.size()); // todo why does this keep going off?

        // update hist plot..
        QVector<QPointF> hist_d(centres.size());
        QVector<QPointF> zero_d(centres.size());
        for (int i = 0; i < hist_d.size(); ++i) {
            hist_d[i] = QPointF(centres[i], counts[i]);
            zero_d[i] = QPointF(centres[i], 0.0f);
        }

        const auto &[cnmin, cnmax] = std::minmax_element(centres.begin(), centres.end());
        const auto &[ctmin, ctmax] = std::minmax_element(counts.begin(), counts.end());

        m_ahx->setRange(*cnmin, *cnmax);
        m_ahy->setRange(0, *ctmax);

        m_h0->replace(zero_d);
        m_h1->replace(hist_d);
    }

    QWidget *create_series_chart() {
        using namespace QtCharts;

        /* ---- series plots  ---- */
        m_asx = new QValueAxis();
        m_asx->setTitleText("RTC Frame");
        m_asx->setTitleFont(m_fnt);
        m_asx->setLabelsFont(m_fnt);

        m_asy = new QValueAxis();
        m_asy->setTitleText(
            QString("Latency (%1s)").arg(m_unit)
        );
        m_asy->setTitleFont(m_fnt);
        m_asy->setLabelsFont(m_fnt);

        m_s0 = new QLineSeries();
        m_s1 = new QLineSeries();
        QPen pen(m_acxt.plot_colour.c_str());
        m_s0->setPen(pen);
        m_s1->setPen(pen);

        /* ---- chart ---- */
        QChart *chart = new QChart();
        chart->legend()->hide();
        chart->addSeries(m_s0);
        chart->addSeries(m_s1);
        chart->addAxis(m_asx, Qt::AlignBottom);
        chart->addAxis(m_asy, Qt::AlignLeft);
        m_s0->attachAxis(m_asx);
        m_s0->attachAxis(m_asy);
        m_s1->attachAxis(m_asx);
        m_s1->attachAxis(m_asy);

        /* ---- view ---- */
        QChartView *view = new QChartView(chart);
        view->setRenderHint(QPainter::Antialiasing);
        view->setRubberBand(QChartView::RectangleRubberBand);
        view->setDragMode(QGraphicsView::ScrollHandDrag);
        return view;
    }

    QWidget *create_hist_chart() {
        using namespace QtCharts;

        /* ---- area plot  ---- */
        QBrush brush(m_acxt.plot_colour.c_str());

        m_ahx = new QValueAxis();
        m_ahx->setTitleText(
            QString("Latency (%1s)").arg(m_unit)
        );
        m_ahx->setTitleFont(m_fnt);
        m_ahx->setLabelsFont(m_fnt);


        m_ahy = new QValueAxis();
        m_ahy->setTitleText("Counts");
        m_ahy->setTitleFont(m_fnt);
        m_ahy->setLabelsFont(m_fnt);

        m_h0 = new QLineSeries();
        m_h1 = new QLineSeries();
        QAreaSeries *areaSeries = new QAreaSeries(m_h1, m_h0);
        areaSeries->setBrush(brush);

        /* ---- chart ---- */
        QChart *chart = new QChart();
        chart->legend()->hide();
        chart->addSeries(areaSeries);
        chart->addAxis(m_ahx, Qt::AlignBottom);
        chart->addAxis(m_ahy, Qt::AlignLeft);
        areaSeries->attachAxis(m_ahx);
        areaSeries->attachAxis(m_ahy);

        /* ---- view ---- */
        QChartView *view = new QChartView(chart);
        view->setRenderHint(QPainter::Antialiasing);
        view->setRubberBand(QChartView::RectangleRubberBand);
        view->setDragMode(QGraphicsView::ScrollHandDrag);
        return view;
    }

    QVBoxLayout *create_charts_panel() {
        QVBoxLayout *layout = new QVBoxLayout();
        layout->addWidget(
            create_series_chart()
        );
        layout->addWidget(
            create_hist_chart()
        );
        return layout;
    }

    QVBoxLayout *create_info_panel() {
        /*  === COMPONENTS === */

        /* ---- config ---- */
        QLabel *cfg_ttl = new QLabel(QString("<b>Capture Configuration</b>"));
        cfg_ttl->setFont(m_fnt);

        QLabel *cfg_lbl = new QLabel(
            QString("Latency shm: %1").arg(m_acxt.latency_shm.c_str())
        );
        cfg_lbl->setFont(m_fnt);

        /* ---- metrics ---- */
        QLabel *metrics_ttl = new QLabel(QString("<b>Capture Statistics</b>"));
        metrics_ttl->setFont(m_fnt);

        m_metrics_lbl = new QLabel(
            m_metrics_tmpl
            .arg(m_unit)
            .arg(0)
            .arg(0)
            .arg(0)
            .arg(0)
            .arg(0)
            .arg(0)
        );
        m_metrics_lbl->setFont(m_fnt);

        /* ---- inspect ---- */
        QPushButton *inspect_btn = new QPushButton("Inspect");
        inspect_btn->setFont(m_fnt);
        QObject::connect(inspect_btn, &QPushButton::clicked, [inspect_btn, this]() {
            this->m_inspecting = !this->m_inspecting;
            QString btn_txt = this->m_inspecting ? "Resume" : "Inspect";
            inspect_btn->setText(btn_txt);
            });

        /*  === LAYOUT === */
        QVBoxLayout *layout = new QVBoxLayout();
        layout->addWidget(cfg_ttl);
        layout->addWidget(cfg_lbl);
        layout->addWidget(metrics_ttl);
        layout->addWidget(m_metrics_lbl);
        layout->addWidget(inspect_btn);
        layout->addStretch();
        return layout;
    }

    QString get_cfg_string() {
        std::string str;
        try {
            YAML::Node config = YAML::LoadFile("config.yaml");

            std::string ifce = config["Session"]["Interface"].as<std::string>();
            std::string cmd_pr = config["Network"]["Command"]["Protocol"].as<std::string>();
            std::string cam_pr = config["Network"]["Camera"]["Protocol"].as<std::string>();
            size_t cam_po = config["Network"]["Camera"]["Port"].as<size_t>();
            size_t cmd_po = config["Network"]["Command"]["Port"].as<size_t>();

            std::string dur = "inf";
            if (!config["Session"]["Duration"].IsNull()) {
                dur = std::to_string(config["Session"]["Duration"].as<size_t>());
                dur += "s";
            }

            str += "Interface: " + ifce + " (" + dur + ")<br>";
            str += "Camera: port " + std::to_string(cam_po) + " (" + cam_pr + ")<br>";
            str += "Command: port " + std::to_string(cmd_po) + " (" + cmd_pr + ")<br>";
        }
        catch (const std::exception &e) {
            str += "Failed to load configuration: ";
            str += e.what();
            str += "\n";
        }

        return QString(str.c_str());
    }

private:
    QtCharts::QLineSeries *m_s0, *m_s1;
    QtCharts::QLineSeries *m_h0, *m_h1;
    QtCharts::QValueAxis *m_asx, *m_asy;
    QtCharts::QValueAxis *m_ahx, *m_ahy;
    QString m_metrics_tmpl;
    QLabel *m_metrics_lbl;
    context_t m_acxt;
    bool m_inspecting;
    QChar m_unit;
    QWidget m_gui;
    QFont m_fnt;
};

/* ===== MAIN ===== */

int main(int argc, char *argv[]) {
    /* ---- cli ---- */
    context_t acxt;
    CLI::App args("Dao Latency GUI - DLG");
    args.add_option("-r,--refresh-rate", acxt.refresh_rate, "GUI Refresh Rate (Hz)");
    args.add_option("-d,--hist-density", acxt.hist_density, "Histogram Bucket Count");
    args.add_option("-b,--buffer-capacity", acxt.buffer_capacity, "Accumulation Buffer Capacity (Samples)");
    args.add_option("-l,--latency-shm", acxt.latency_shm, "DLT Latency Shared Memory");
    args.add_option("-p,--plot-colour", acxt.plot_colour, "GUI Plotting Colour (#RRGGBB Hex-Code)");
    args.add_option("-y,--series-yclip", acxt.series_yclip, "Series Y-Axis Maximum Value");
    args.add_option("-f,--font-size", acxt.ptsize, "Font Size");
    args.add_flag("-c,--context-details", acxt.display, "Print Context Details");
    CLI11_PARSE(args, argc, argv);
    acxt.print();

    /* ---- gui ---- */
    QApplication app(argc, argv);
    qRegisterMetaType<draw_context>();
    gui_t *gui = new gui_t(acxt);

    /* ---- accumulator ---- */
    accumulator_t *acc = new accumulator_t(acxt);
    QThread *worker_t = new QThread();
    acc->moveToThread(worker_t);
    QObject::connect(worker_t, &QThread::started, acc, &accumulator_t::run);
    QObject::connect(acc, &accumulator_t::redraw, gui, &gui_t::redraw);

    /* ---- launch ---- */
    worker_t->start();
    gui->create();
    return app.exec();
}

#include "daoLatencyGUI.moc"